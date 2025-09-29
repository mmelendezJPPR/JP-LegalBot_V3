import os, json, numpy as np, faiss
from typing import List, Dict
from openai import AzureOpenAI, OpenAI
from .config import (
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT, DB_PATH, FAISS_PATH
)
from .db import get_conn, fts_search

class HybridRetriever:
    def __init__(self, db_path=DB_PATH, faiss_path=FAISS_PATH):
        # Validar configuración Azure OpenAI antes de crear cliente
        if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_ENDPOINT.startswith('http'):
            raise ValueError(f"AZURE_OPENAI_ENDPOINT inválido: '{AZURE_OPENAI_ENDPOINT}'. Debe comenzar con https://")
            
        if not AZURE_OPENAI_KEY or len(AZURE_OPENAI_KEY) < 10:
            raise ValueError(f"AZURE_OPENAI_KEY inválido o faltante (longitud: {len(AZURE_OPENAI_KEY)})")
        
        print(f"🔧 Configurando HybridRetriever Azure OpenAI:")
        print(f"   📡 Endpoint: {AZURE_OPENAI_ENDPOINT}")
        print(f"   🔑 API Key: {'*' * max(0, len(AZURE_OPENAI_KEY) - 8) + AZURE_OPENAI_KEY[-8:]}")
        
        # Configurar Azure OpenAI para chat
        self.azure_client = AzureOpenAI(
            api_key=AZURE_OPENAI_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT
        )
        
        # Configuración simplificada: SOLO Azure OpenAI
        # Verificar si tenemos un deployment válido de embeddings en Azure
        if (AZURE_OPENAI_EMBEDDING_DEPLOYMENT and 
            AZURE_OPENAI_EMBEDDING_DEPLOYMENT not in ["text-embedding-3-small", "gpt-4.1"] and
            AZURE_OPENAI_KEY):
            # Usar Azure OpenAI si tenemos deployment válido de embeddings
            self.embedding_client = self.azure_client
            self.embedding_model = AZURE_OPENAI_EMBEDDING_DEPLOYMENT
            print(f"🔧 Usando Azure OpenAI para embeddings: {self.embedding_model}")
        else:
            # Sin embeddings disponibles - usar búsqueda solo textual (más común)
            self.embedding_client = None
            self.embedding_model = None
            print("⚠️ Sin servicio de embeddings disponible - usando solo búsqueda textual")
        self.db_path = db_path
        self.faiss_path = faiss_path
        self.index = faiss.read_index(self.faiss_path)
        metas_path = os.path.join(os.path.dirname(self.faiss_path), "metas.jsonl")
        try:
            self.metas = [json.loads(l) for l in open(metas_path, "r", encoding="utf-8")]
        except FileNotFoundError:
            # Si no existe metas.jsonl, crear lista vacía y advertir
            print(f"⚠️ Advertencia: {metas_path} no encontrado, usando metadatos vacíos")
            self.metas = []

    def embed(self, text: str) -> np.ndarray:
        if self.embedding_client is None:
            # Sin embeddings disponibles, retornar vector vacío
            return np.array([[0.0]], dtype="float32")
        
        e = self.embedding_client.embeddings.create(model=self.embedding_model, input=[text]).data[0].embedding
        v = np.array([e], dtype="float32")
        faiss.normalize_L2(v)
        return v

    def search_vectors(self, query: str, k=12) -> List[Dict]:
        if self.embedding_client is None:
            # Sin embeddings, retornar lista vacía
            print("⚠️ Búsqueda vectorial no disponible, usando solo búsqueda textual")
            return []
        
        qv = self.embed(query)
        D, I = self.index.search(qv, k)
        out = []
        for score, i in zip(D[0], I[0]):
            if i == -1: continue
            if i < len(self.metas):  # Verificar que el índice es válido
                m = self.metas[i]
                out.append({"score": float(score), **m})
        return out

    def search_lexical(self, query: str, k=12) -> List[Dict]:
        # Usa FTS5 con query literal; permite "permiso NEAR/3 construcción"
        with get_conn(self.db_path) as con:
            rows = fts_search(con, query, limit=k)
        # Adaptado para nueva estructura de BD
        return [{"score": 0.0, 
                "chunk_id": r.get("rowid", "unknown"), 
                "doc_id": r["doc_id"], 
                "heading_path": r["heading_path"], 
                "page_start": r.get("page_start"), 
                "page_end": r.get("page_end"), 
                "text": r.get("text", ""), 
                "snippet": r["snip"]} for r in rows]

    def fetch_texts(self, chunk_ids: List[str]) -> Dict[str, str]:
        # Recupera texto desde FTS por rowid (adaptado para nueva estructura)
        with get_conn(self.db_path) as con:
            qmarks = ",".join("?"*len(chunk_ids))
            cur = con.execute(f"SELECT rowid, content FROM fts_chunks WHERE rowid IN ({qmarks})", chunk_ids)
            return {str(r[0]): r[1] for r in cur.fetchall()}

    def hybrid(self, query: str, k_vec=12, k_lex=12, final_k=6) -> List[Dict]:
        vec = self.search_vectors(query, k=k_vec)
        lex = self.search_lexical(query, k=k_lex)
        # Fusión simple: favorece diversidad por chunk_id
        seen, fused = set(), []
        for cand in vec + lex:
            cid = cand["chunk_id"]
            if cid in seen: continue
            seen.add(cid)
            fused.append(cand)
            if len(fused) >= (k_vec//2 + k_lex//2):
                break
        # Traer textos
        texts = self.fetch_texts([c["chunk_id"] for c in fused[:final_k]])
        for c in fused:
            c["text"] = texts.get(c["chunk_id"], "")
        return fused[:final_k]
