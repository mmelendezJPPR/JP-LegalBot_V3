import os, glob, uuid, json, argparse, numpy as np
from tqdm import tqdm
from openai import AzureOpenAI
import faiss
from .config import (
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT, DB_PATH, FAISS_PATH
)
from .db import get_conn, upsert_chunk
from chunker import split_into_blocks, guess_metadata_from_text

os.makedirs(os.path.dirname(FAISS_PATH), exist_ok=True)

# Usar Azure OpenAI para embeddings
client = AzureOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_OPENAI_API_VERSION
) if AZURE_OPENAI_KEY else None

def embed_texts(texts):
    # Llamada batcheada
    embs = []
    B = 64
    for i in tqdm(range(0, len(texts), B), desc="Embeddings"):
        batch = texts[i:i+B]
        resp = client.embeddings.create(model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT, input=batch)
        embs.extend([d.embedding for d in resp.data])
    return np.array(embs, dtype="float32")

def main(data_dir):
    txt_files = sorted(glob.glob(os.path.join(data_dir, "*.txt")))
    all_texts, metas = [], []
    for path in txt_files:
        doc_id = os.path.basename(path)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
        blocks = split_into_blocks(raw, max_chars=4000, overlap=600)
        for b in blocks:
            md = guess_metadata_from_text(b)
            metas.append({
                "chunk_id": str(uuid.uuid4()),
                "doc_id": doc_id,
                "page_start": None,
                "page_end": None,
                "heading_path": md.get("heading_path", "")
            })
            all_texts.append(b)

    # Embeddings
    X = embed_texts(all_texts)
    faiss.normalize_L2(X)
    index = faiss.IndexFlatIP(X.shape[1])
    index.add(X)
    faiss.write_index(index, FAISS_PATH)

    # SQLite FTS + metadatos
    with get_conn(DB_PATH) as con:
        for t, m in tqdm(zip(all_texts, metas), total=len(all_texts), desc="Upsert SQLite"):
            upsert_chunk(con, m["chunk_id"], m["doc_id"], m["page_start"], m["page_end"], m["heading_path"], t)

    # Guarda espejo de metadatos para mapear FAISS -> chunk_id
    with open(os.path.join(os.path.dirname(FAISS_PATH), "metas.jsonl"), "w", encoding="utf-8") as out:
        for m in metas:
            out.write(json.dumps(m, ensure_ascii=False) + "\n")

    print("✅ Índice construido:", FAISS_PATH)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_dir", required=True)
    ap.add_argument("--out_index", default=FAISS_PATH)
    ap.add_argument("--db", default=DB_PATH)
    args = ap.parse_args()
    main(args.data_dir)
