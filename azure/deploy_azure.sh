#!/usr/bin/env bash
# Provisiona ACR + ACI (região mexicocentral) para a API RAG do repositório
# DisruptiveArchitectures-CPz-o5 (FastAPI em api/python).
#
# Uso (na raiz do repositório):
#   export GEMINI_API_KEY="..."          # ou será pedida de forma oculta
#   bash azure/deploy-azure.sh           # provisiona, builda, envia e sobe o ACI
#   bash azure/deploy-azure.sh destroy   # apaga o resource group inteiro
#
# Variáveis opcionais: RM, RG, ACR_NAME, DNS_LABEL, TAG, USE_ACR_BUILD=1
set -euo pipefail

# ---------- Configuração ----------
LOCATION="mexicocentral"
RM="${RM:-565592}"
RG="${RG:-rg-disruptive-api}"
ACR_NAME="${ACR_NAME:-acrdisruptive${RM}}"        # globalmente único, só minúsculas/números
IMAGE_NAME="disruptive-rag-api"
TAG="${TAG:-v1}"
ACI_NAME="${ACI_NAME:-aci-disruptive-api}"
DNS_LABEL="${DNS_LABEL:-disruptive-api-rm${RM}}"  # -> <label>.mexicocentral.azurecontainer.io
PORT=8000
USE_ACR_BUILD="${USE_ACR_BUILD:-0}"               # 1 = build na nuvem (ACR Tasks); pode ser bloqueado em Azure for Students

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKERFILE="$REPO_ROOT/azure/Dockerfile"

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

# ---------- Destroy ----------
if [[ "${1:-}" == "destroy" ]]; then
  log "Excluindo resource group $RG"
  az group delete --name "$RG" --yes --no-wait
  echo "Exclusão iniciada. Confira com: az group list -o table"
  exit 0
fi

# ---------- Pré-requisitos ----------
command -v az >/dev/null     || { echo "az CLI não encontrado"; exit 1; }
[[ "$USE_ACR_BUILD" == "1" ]] || command -v docker >/dev/null || { echo "docker não encontrado (ou use USE_ACR_BUILD=1)"; exit 1; }
az account show >/dev/null 2>&1 || { echo "Faça login antes: az login"; exit 1; }
[[ -f "$REPO_ROOT/scripts/chunks_gemini_embedded.json" ]] || { echo "Índice RAG não encontrado em scripts/"; exit 1; }

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  read -rsp "GEMINI_API_KEY: " GEMINI_API_KEY; echo
  [[ -n "$GEMINI_API_KEY" ]] || { echo "GEMINI_API_KEY vazia"; exit 1; }
fi

# ---------- 1. Providers ----------
log "Registrando providers (pode demorar na primeira vez)"
az provider register --namespace Microsoft.ContainerRegistry --wait
az provider register --namespace Microsoft.ContainerInstance --wait

# ---------- 2. Resource group ----------
log "Resource group $RG em $LOCATION"
az group create --name "$RG" --location "$LOCATION" -o none

# ---------- 3. ACR ----------
log "Azure Container Registry $ACR_NAME"
az acr create --resource-group "$RG" --name "$ACR_NAME" \
  --sku Basic --admin-enabled true --location "$LOCATION" -o none
LOGIN_SERVER="$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)"
FULL_IMAGE="$LOGIN_SERVER/$IMAGE_NAME:$TAG"

# ---------- 4. Build + push ----------
if [[ "$USE_ACR_BUILD" == "1" ]]; then
  log "Build na nuvem (az acr build)"
  az acr build --registry "$ACR_NAME" --image "$IMAGE_NAME:$TAG" \
    --file azure/Dockerfile "$REPO_ROOT"
else
  log "Build local e push de $FULL_IMAGE"
  az acr login --name "$ACR_NAME"
  docker build --platform linux/amd64 -f "$DOCKERFILE" -t "$FULL_IMAGE" "$REPO_ROOT"
  docker push "$FULL_IMAGE"
fi

# ---------- 5. ACI ----------
log "Container Instance $ACI_NAME"
ACR_USER="$(az acr credential show --name "$ACR_NAME" --query username -o tsv)"
ACR_PASS="$(az acr credential show --name "$ACR_NAME" --query 'passwords[0].value' -o tsv)"

az container create \
  --resource-group "$RG" \
  --name "$ACI_NAME" \
  --location "$LOCATION" \
  --image "$FULL_IMAGE" \
  --registry-login-server "$LOGIN_SERVER" \
  --registry-username "$ACR_USER" \
  --registry-password "$ACR_PASS" \
  --os-type Linux \
  --cpu 1 --memory 1.5 \
  --ports "$PORT" \
  --ip-address Public \
  --dns-name-label "$DNS_LABEL" \
  --restart-policy OnFailure \
  --secure-environment-variables GEMINI_API_KEY="$GEMINI_API_KEY" \
  -o none

FQDN="$(az container show -g "$RG" -n "$ACI_NAME" --query ipAddress.fqdn -o tsv)"
URL="http://$FQDN:$PORT"

# ---------- 6. Smoke test ----------
log "Aguardando a API subir em $URL"
for i in $(seq 1 20); do
  if curl -fsS -o /dev/null "$URL/openapi.json"; then echo "API respondendo."; break; fi
  [[ $i -eq 20 ]] && { echo "Sem resposta. Veja: az container logs -g $RG -n $ACI_NAME"; exit 1; }
  sleep 6
done

cat <<MSG

Pronto!
  Docs (Swagger):  $URL/docs
  Endpoint:        POST $URL/chat

Teste:
  curl -X POST $URL/chat -H 'Content-Type: application/json' \\
       -d '{"mensagem":"O que é RAG?"}'

Logs:     az container logs -g $RG -n $ACI_NAME
Limpar:   bash azure/deploy-azure.sh destroy
MSG
