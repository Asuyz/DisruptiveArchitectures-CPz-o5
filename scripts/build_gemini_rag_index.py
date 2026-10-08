import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / "api" / "python" / ".env")

EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2")
BATCH_SIZE = 20


def preparar_documento(titulo: str, texto: str) -> str:
    return f"title: {titulo} | text: {texto}"


def gerar_embeddings(client: genai.Client, textos: list[str]) -> list[list[float]]:
    resultado = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=textos,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=384,
        ),
    )
    return [
        np.array(embedding.values, dtype=float).tolist()
        for embedding in resultado.embeddings
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gera um índice RAG Gemini a partir de chunks.json."
    )
    parser.add_argument(
        "--input",
        default="chunks.json",
        help="Arquivo com chunks sem embeddings.",
    )
    parser.add_argument(
        "--output",
        default="chunks_gemini_embedded.json",
        help="Arquivo de saída com embeddings Gemini.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help="Quantidade de chunks por chamada de embedding.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Ignora embeddings existentes e reconstrói o índice inteiro.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    chunks = json.loads(input_path.read_text(encoding="utf-8"))

    if output_path.exists() and not args.rebuild:
        progresso = json.loads(output_path.read_text(encoding="utf-8"))
        embeddings_salvos = {
            item["id"]: item["embedding"] for item in progresso if item.get("embedding")
        }
        for chunk in chunks:
            if chunk["id"] in embeddings_salvos:
                chunk["embedding"] = embeddings_salvos[chunk["id"]]
        print(f"Embeddings reaproveitados: {len(embeddings_salvos)}")

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    print(f"Carregados {len(chunks)} chunks de {args.input}")

    pendentes = [chunk for chunk in chunks if not chunk.get("embedding")]
    for inicio in range(0, len(pendentes), args.batch_size):
        lote = pendentes[inicio : inicio + args.batch_size]
        textos = [preparar_documento(chunk["titulo"], chunk["texto"]) for chunk in lote]
        embeddings = gerar_embeddings(client, textos)
        if len(embeddings) != len(lote):
            raise RuntimeError(
                f"A API retornou {len(embeddings)} embeddings para {len(lote)} chunks."
            )

        for chunk, embedding in zip(lote, embeddings):
            chunk["embedding"] = embedding

        output_path.write_text(
            json.dumps(chunks, ensure_ascii=False),
            encoding="utf-8",
        )
        processados = len(chunks) - len(
            [item for item in chunks if not item.get("embedding")]
        )
        print(f"Embeddings gerados: {processados}/{len(chunks)}")
        if inicio + args.batch_size < len(pendentes):
            time.sleep(1)

    output_path.write_text(
        json.dumps(chunks, ensure_ascii=False),
        encoding="utf-8",
    )
    dimensao = len(chunks[0]["embedding"]) if chunks else 0
    print(f"Índice salvo em {args.output} com dimensão {dimensao}")


if __name__ == "__main__":
    main()
