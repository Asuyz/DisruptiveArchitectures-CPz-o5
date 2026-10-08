import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv(Path(__file__).with_name(".env"))

from rag import buscar_trechos, montar_contexto

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
        "https://arnaldojr.github.io",
    ],
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

MODEL = "gemini-3-flash-preview"
SYSTEM_PROMPT = """
# PERSONA E CONTEXTO
Você é a assistente virtual do site da disciplina **Disruptive Architectures: IA e IoT**.
O site apoia estudantes do curso de Tecnologia em Desenvolvimento de Sistemas, nas turmas de 2026, e reúne aulas, laboratórios, desafios, checkpoints, materiais de apoio, dicas e referências.

Os principais temas da base são:
- fundamentos de Inteligência Artificial, Machine Learning, Deep Learning e IA Generativa;
- engenharia de prompts, assistentes conversacionais, ferramentas, saídas estruturadas e RAG;
- Python aplicado a aplicações de IA, notebooks, Google Colab e bibliotecas do curso;
- Internet das Coisas, sensores, atuadores, Arduino e ESP32;
- HTTP, WebServer, APIs REST, JSON, MQTT, Node-RED, fluxos e dashboards;
- agenda, orientações de atividades, checkpoints e objetivos de aprendizagem da disciplina.

Seu objetivo é ajudar o estudante a localizar, compreender e aplicar os conteúdos disponíveis no site.

# ESCOPO
Responda dúvidas conceituais e práticas relacionadas aos conteúdos da disciplina.
Quando a pergunta envolver código, explique o funcionamento de forma didática e baseie a resposta nos trechos recuperados do site.
Você pode organizar uma explicação, resumir um laboratório, comparar conceitos e indicar materiais relacionados.

Se o usuário perguntar algo que não esteja sustentado pelo conteúdo recuperado ou fugir do escopo da disciplina:
1. Informe claramente que não encontrou essa informação na base do site.
2. Não invente uma resposta para preencher a lacuna.
3. Sugira que o usuário faça uma pergunta relacionada a IA, IoT ou aos materiais da disciplina.

"""

SYSTEM_PROMPT_RAG = f"""
{SYSTEM_PROMPT}
REGRAS OBRIGATÓRIAS DO RAG:
- Responda usando apenas o CONTEXTO fornecido pela aplicação.
- Não use conhecimento próprio para completar informações ausentes.
- Se o contexto não sustentar a resposta, diga: "Não encontrei essa informação no conteúdo do site."
- Não invente informações, nomes, datas, links ou procedimentos.
- Cite as fontes usando o formato [Fonte: URL] quando fizer afirmações baseadas no contexto.
- Responda em português, de forma clara e objetiva.
"""


class ChatRequest(BaseModel):
    mensagem: str
    previous_interaction_id: str | None = None


class Fonte(BaseModel):
    titulo: str
    url: str


class ChatResponse(BaseModel):
    resposta: str
    interaction_id: str
    fontes: list[Fonte]


def processar_mensagem(
    mensagem: str,
    previous_interaction_id: str | None = None,
) -> ChatResponse:
    trechos = buscar_trechos(mensagem)
    contexto = montar_contexto(trechos)

    argumentos = {
        "model": MODEL,
        "system_instruction": SYSTEM_PROMPT_RAG,
        "input": f"CONTEXTO:\n{contexto}\n\nPERGUNTA:\n{mensagem}",
    }

    if previous_interaction_id:
        argumentos["previous_interaction_id"] = previous_interaction_id

    interaction = client.interactions.create(**argumentos)

    return ChatResponse(
        resposta=interaction.output_text,
        interaction_id=interaction.id,
        fontes=[
            Fonte(titulo=trecho["titulo"], url=trecho["url"])
            for trecho in trechos
            if trecho["url"]
        ],
    )


@app.post("/chat", response_model=ChatResponse)
def conversar(request: ChatRequest) -> ChatResponse:
    return processar_mensagem(
        request.mensagem,
        request.previous_interaction_id,
    )
