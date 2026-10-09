# Bem vindo disciplina de Disruptive Architectures: IA e IoT

Olá pessoal, bem vindos!! Neste repositório você irá encontrar os conteúdos ministrados em sala de aula assim como dicas, exemplos e laboratórios. 

## Para acompanhar os roteiros práticos 

Acesse o site:

- [website: https://arnaldojr.github.io/DisruptiveArchitectures/](https://arnaldojr.github.io/DisruptiveArchitectures/)


## Como clonar o repositório

``` bash
$ # no terminal digite
$ git clone https://github.com/arnaldojr/DisruptiveArchitectures/

```

---

## API do assistente RAG no Azure (ACR + ACI)

A API do chatbot (FastAPI, em `api/python`) pode ser publicada no Azure com um único script, que cria o
Azure Container Registry (ACR), envia a imagem Docker e sobe o container no Azure Container Instances (ACI),
tudo na região **mexicocentral**.

### Estrutura usada no deploy

```
.
├── .dockerignore              # na raiz: define o que entra no contexto do build
├── api/python/                # chatbot.py, rag.py, pyproject.toml, uv.lock
├── scripts/
│   └── chunks_gemini_embedded.json   # índice RAG carregado pela API
└── azure/
    ├── Dockerfile
    └── deploy-azure.sh
```

### Pré-requisitos

- Docker instalado e com o daemon rodando (`docker version`)
- Azure CLI instalado (`az version`)
- Uma assinatura Azure com acesso à região `mexicocentral`
- Uma chave da API do Gemini

### Passo a passo

**1. Login no Azure**

```bash
az login
az account show      # confirme que é a assinatura correta
```

**2. Defina a chave do Gemini (`GEMINI_API_KEY`)**

A chave é lida da variável de ambiente `GEMINI_API_KEY` e enviada ao container como variável segura
(`--secure-environment-variables`), ou seja, ela não fica visível na configuração do ACI.

```bash
export GEMINI_API_KEY="cole-sua-chave-aqui"
```

Se preferir não deixar a chave no histórico do terminal, use a leitura oculta:

```bash
read -rsp "GEMINI_API_KEY: " GEMINI_API_KEY && export GEMINI_API_KEY && echo
```

Se a variável **não** estiver definida, o próprio script pede a chave de forma oculta. Para conferir se ela
já existe na sua sessão (sem imprimir o valor):

```bash
[ -n "$GEMINI_API_KEY" ] && echo "definida (${#GEMINI_API_KEY} caracteres)" || echo "vazia"
```

> Nunca faça commit da chave. O `.gitignore` já ignora o arquivo `.env`.

**3. Rode o provisionamento** (a partir da raiz do repositório)

```bash
bash azure/deploy-azure.sh
```

O script executa, nesta ordem:

1. Registra os providers `Microsoft.ContainerRegistry` e `Microsoft.ContainerInstance`
2. Cria o resource group `rg-disruptive-api` em `mexicocentral`
3. Cria o ACR `acrdisruptive565592` (SKU Basic, admin habilitado)
4. Faz o build da imagem (`linux/amd64`) e o push para o ACR
5. Cria o ACI com IP público, DNS `disruptive-api-rm565592` e a `GEMINI_API_KEY` como variável segura
6. Espera a API responder e imprime as URLs

### Testando

Ao final, o script mostra a URL. Com os valores padrão:

```bash
URL=http://disruptive-api-rm565592.mexicocentral.azurecontainer.io:8000

# Swagger no navegador
echo "$URL/docs"

# Chamada ao chat
curl -X POST "$URL/chat" \
  -H 'Content-Type: application/json' \
  -d '{"mensagem":"O que é RAG?"}'
```

A resposta deve conter os campos `resposta`, `interaction_id` e `fontes`.

### Variáveis opcionais

| Variável | Padrão | Para que serve |
|---|---|---|
| `RM` | `-` | Sufixo usado nos nomes do ACR e do DNS |
| `RG` | `rg-disruptive-api` | Nome do resource group |
| `ACR_NAME` | `acrdisruptive${RM}` | Nome do ACR (único globalmente, só minúsculas e números) |
| `DNS_LABEL` | `disruptive-api-rm${RM}` | Prefixo do endereço público do ACI |
| `TAG` | `v1` | Tag da imagem |
| `USE_ACR_BUILD` | `0` | `1` faz o build na nuvem (`az acr build`) em vez de local |

Exemplo:

```bash
ACR_NAME=acrdisruptivemeunome DNS_LABEL=minha-api-rag bash azure/deploy-azure.sh
```

### Diagnóstico

```bash
az container logs -g rg-disruptive-api -n aci-disruptive-api
az container show -g rg-disruptive-api -n aci-disruptive-api --query instanceView.state
```

| Sintoma | Causa provável |
|---|---|
| `RequestDisallowedByAzure` | A política da assinatura bloqueia a região ou o recurso |
| `The registry name is already in use` | Nome do ACR já existe; use outro em `ACR_NAME` |
| `Internal Server Error` no `/chat` | `GEMINI_API_KEY` inválida ou sem cota (veja os logs) |
| Widget do site não conecta | O ACI serve apenas HTTP e o site é HTTPS (mixed content); veja a observação abaixo |

Para trocar a chave depois do deploy, exporte a nova e recrie tudo:

```bash
export GEMINI_API_KEY="nova-chave"
bash azure/deploy-azure.sh destroy   # aguarde o grupo ser removido
bash azure/deploy-azure.sh
```

### Observações

- **HTTPS:** o ACI expõe apenas HTTP. Para usar a API a partir de uma página HTTPS (como o GitHub Pages), é
  necessário colocar HTTPS na frente (Application Gateway, Front Door etc.).
- **CORS:** o `api/python/chatbot.py` só aceita requisições de `localhost` e de `https://arnaldojr.github.io`.
  Se o site estiver em outro domínio, ajuste a lista `allow_origins`.

### Limpeza (importante para não consumir crédito)

```bash
bash azure/deploy-azure.sh destroy
az group list -o table    # confirme que rg-disruptive-api foi removido
```
