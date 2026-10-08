import json
import os
import re
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(Path(__file__).with_name(".env"))

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHUNKS_PATH = Path(
    os.getenv(
        "RAG_INDEX_PATH", PROJECT_ROOT / "scripts" / "chunks_gemini_embedded.json"
    )
)
EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2")


_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def preparar_pergunta(pergunta: str) -> str:
    return pergunta


def preparar_documento(titulo: str, texto: str) -> str:
    return f"title: {titulo} | text: {texto}"


def gerar_embedding(texto: str) -> np.ndarray:
    resultado = _client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texto,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=384,
        ),
    )
    return np.array(resultado.embeddings[0].values, dtype=float)


def carregar_indice() -> list[dict]:
    if not CHUNKS_PATH.exists():
        raise RuntimeError(
            f"Índice RAG não encontrado em {CHUNKS_PATH}. "
            "Execute scripts/build_gemini_rag_index.py antes de iniciar a API."
        )

    indice = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    if not indice:
        raise RuntimeError(f"Índice RAG vazio: {CHUNKS_PATH}")

    return indice


INDICE: list[dict] | None = None


def similaridade_cosseno(vetor_a: np.ndarray, vetor_b: np.ndarray) -> float:
    denominador = np.linalg.norm(vetor_a) * np.linalg.norm(vetor_b)
    if denominador == 0:
        return 0.0
    return float(np.dot(vetor_a, vetor_b) / denominador)


STOPWORDS = {
    "a",
    "ao",
    "as",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "é",
    "essa",
    "esse",
    "eu",
    "o",
    "os",
    "para",
    "por",
    "que",
    "um",
    "uma",
    "sobre",
}


def similaridade_termos(pergunta: str, texto: str) -> float:
    pergunta_tokens = {
        token
        for token in re.findall(r"[\wÀ-ÿ]+", pergunta.lower())
        if token not in STOPWORDS and len(token) > 2
    }
    texto_tokens = set(re.findall(r"[\wÀ-ÿ]+", texto.lower()))
    if not pergunta_tokens:
        return 0.0
    return len(pergunta_tokens & texto_tokens) / len(pergunta_tokens)


def buscar_trechos(pergunta: str, k: int = 4) -> list[dict]:
    global INDICE
    if INDICE is None:
        INDICE = carregar_indice()

    vetor_pergunta = gerar_embedding(preparar_pergunta(pergunta))
    resultados = []

    for item in INDICE:
        vetor_documento = np.array(item["embedding"], dtype=float)
        score_vetorial = similaridade_cosseno(vetor_pergunta, vetor_documento)
        score_termos = similaridade_termos(
            pergunta,
            f"{item['titulo']} {item['texto']}",
        )
        resultados.append(
            {
                "titulo": item["titulo"],
                "url": item["url"],
                "texto": item["texto"],
                "similaridade": (max(score_vetorial, 0.0) * 0.65 + score_termos * 0.35),
            }
        )

    resultados.sort(key=lambda item: item["similaridade"], reverse=True)
    return resultados[:k]


def montar_contexto(trechos: list[dict]) -> str:
    blocos = []
    for trecho in trechos:
        blocos.append(
            f"FONTE: {trecho['url']}\n"
            f"TÍTULO: {trecho['titulo']}\n"
            f"CONTEÚDO: {trecho['texto']}"
        )
    return "\n\n---\n\n".join(blocos)
