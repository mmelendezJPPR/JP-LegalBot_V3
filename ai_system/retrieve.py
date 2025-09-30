import os, json, numpy as np, faiss
from typing import List, Dict
from openai import AzureOpenAI, OpenAI
from .config import (
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT, DB_PATH, FAISS_PATH,
    OPENAI_API_KEY, MODEL_EMBED
)
from .local_embeddings import LocalEmbeddings
from .db import get_conn, fts_search
import uuid

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
        
        # Configuración de embeddings con prioridades:
        # 1. Azure OpenAI (si tiene deployment específico)
        # 2. OpenAI directo (si tiene API key)
        # 3. LocalEmbeddings (siempre disponible)
        self.embedding_client = None
        self.embedding_model = None
        self.local_embedder = None
        
        # Intentar Azure OpenAI primero (si tiene deployment específico)
        azure_success = False
        if AZURE_OPENAI_EMBEDDING_DEPLOYMENT and AZURE_OPENAI_KEY:
            try:
                test_response = self.azure_client.embeddings.create(
                    model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT, 
                    input=["test"]
                )
                self.embedding_client = self.azure_client
                self.embedding_model = AZURE_OPENAI_EMBEDDING_DEPLOYMENT
                azure_success = True
                print(f"✅ Usando Azure OpenAI para embeddings: {self.embedding_model}")
            except Exception as e:
                print(f"⚠️ Azure embeddings no disponible ({str(e)[:100]}...)")
        
        # Si Azure falló, intentar OpenAI directo (solo si tiene clave real)
        if not azure_success and OPENAI_API_KEY and OPENAI_API_KEY not in ["tu_clave_openai_aqui", ""]:
            try:
                from openai import OpenAI
                self.embedding_client = OpenAI(api_key=OPENAI_API_KEY)
                self.embedding_model = MODEL_EMBED
                print(f"✅ Usando OpenAI directo para embeddings: {self.embedding_model}")
            except Exception as e2:
                print(f"❌ OpenAI fallback falló: {str(e2)[:100]}...")
        elif OPENAI_API_KEY in ["tu_clave_openai_aqui", ""]:
            print("⚠️ OPENAI_API_KEY es placeholder - usando embeddings locales")
        
        # Si ninguna API externa funciona, usar embeddings locales
        if self.embedding_client is None:
            try:
                self.local_embedder = LocalEmbeddings()
                print(f"✅ Usando embeddings locales: {self.local_embedder.model_name}")
            except Exception as e3:
                print(f"❌ Embeddings locales también fallaron: {str(e3)[:100]}...")
                print("⚠️ Sistema funcionando solo con búsqueda textual")
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
        # Prioridad: API externa > LocalEmbeddings > Vector vacío
        if self.embedding_client is not None:
            # Usar API externa (Azure u OpenAI)
            e = self.embedding_client.embeddings.create(model=self.embedding_model, input=[text]).data[0].embedding
            v = np.array([e], dtype="float32")
            faiss.normalize_L2(v)
            return v
        elif self.local_embedder is not None:
            # Usar embeddings locales
            return self.local_embedder.encode_query(text)
        else:
            # Sin embeddings disponibles, retornar vector vacío
            print("⚠️ Embeddings no disponibles, usando vector vacío")
            return np.array([[0.0]], dtype="float32")

    def search_vectors(self, query: str, k=12, similarity_threshold=0.7) -> List[Dict]:
        # Verificar si tenemos algún tipo de embeddings disponible
        has_embeddings = self.embedding_client is not None or self.local_embedder is not None

        if not has_embeddings:
            # Sin embeddings, retornar lista vacía
            print("⚠️ Búsqueda vectorial no disponible, usando solo búsqueda textual")
            return []

        # Si usamos embeddings locales pero el índice FAISS es incompatible (diferente dimensión)
        # por ahora retornamos vacío hasta que se regenere el índice
        if self.local_embedder and self.index:
            # Verificar si las dimensiones son compatibles
            index_dim = self.index.d
            local_dim = self.local_embedder.dimension
            if index_dim != local_dim:
                print(f"⚠️ Índice FAISS incompatible: {index_dim} dims vs {local_dim} dims (embeddings locales)")
                print("💡 Solución: Regenerar índice con embeddings locales usando build_index.py")
                return []

        qv = self.embed(query)

        # Verificar que el índice existe y tiene vectores
        if self.index is None or self.index.ntotal == 0:
            print("⚠️ No hay índice FAISS disponible")
            return []

        # Buscar más resultados para luego filtrar y rerankear
        search_k = min(k * 3, self.index.ntotal)
        D, I = self.index.search(qv, search_k)

        candidates = []
        for score, i in zip(D[0], I[0]):
            if i == -1:
                continue
            if i < len(self.metas):  # Verificar que el índice es válido
                m = self.metas[i]
                # Filtrar por umbral de similitud
                if score >= similarity_threshold:
                    candidates.append({"score": float(score), **m})

        # Rerankear por diversidad y relevancia
        candidates = self._rerank_candidates(candidates, query, k)
        return candidates[:k]

    def _rerank_candidates(self, candidates: List[Dict], query: str, top_k: int) -> List[Dict]:
        """Rerankear candidatos por diversidad y relevancia"""
        if not candidates:
            return candidates

        # Puntaje compuesto: similitud + diversidad + recencia (si hay metadata de tiempo)
        scored_candidates = []
        seen_docs = set()

        for cand in candidates:
            score = cand.get("score", 0.0)

            # Bonus por diversidad de documentos
            doc_id = cand.get("doc_id", "")
            if doc_id not in seen_docs:
                score += 0.1  # Bonus por documento nuevo
                seen_docs.add(doc_id)

            # Bonus por relevancia de encabezado
            heading = cand.get("heading_path", "").lower()
            query_lower = query.lower()
            if any(word in heading for word in query_lower.split()):
                score += 0.05

            cand["reranked_score"] = score
            scored_candidates.append(cand)

        # Ordenar por puntaje rerankeado
        scored_candidates.sort(key=lambda x: x.get("reranked_score", 0), reverse=True)
        return scored_candidates

    def search_lexical(self, query: str, k=12) -> List[Dict]:
        # Usa FTS5 con query literal; permite "permiso NEAR/3 construcción"
        with get_conn(self.db_path) as con:
            rows = fts_search(con, query, limit=k)
        # Adaptado para nueva estructura de BD
        return [{"score": 0.0, 
                "chunk_id": str(r.get("chunk_id", r.get("rowid", "unknown"))),  # Asegurar que sea string
                "doc_id": r["doc_id"], 
                "heading_path": r["heading_path"], 
                "page_start": r.get("page_start"), 
                "page_end": r.get("page_end"), 
                "text": r.get("text", ""), 
                "snippet": r["snip"]} for r in rows]

    def fetch_texts(self, chunk_ids: List[str]) -> Dict[str, str]:
        # Recupera texto desde FTS por rowid (adaptado para estructura actual)
        if not chunk_ids:
            return {}
        
        with get_conn(self.db_path) as con:
            # Convertir chunk_ids a enteros para la consulta SQL (rowid es entero)
            try:
                int_chunk_ids = [int(cid) for cid in chunk_ids if cid and cid != "unknown"]
            except (ValueError, TypeError) as e:
                print(f"⚠️ Error convirtiendo chunk_ids a enteros: {e}")
                return {}
            
            if not int_chunk_ids:
                return {}
                
            qmarks = ",".join("?"*len(int_chunk_ids))
            # La columna de texto se llama `content` en la tabla FTS actual
            cur = con.execute(f"SELECT rowid, content FROM fts_chunks WHERE rowid IN ({qmarks})", int_chunk_ids)
            # Retornar con chunk_id como string (clave del dict)
            return {str(r[0]): r[1] for r in cur.fetchall()}

    def hybrid(self, query: str, k_vec=12, k_lex=12, final_k=6, similarity_threshold=0.7) -> List[Dict]:
        vec = self.search_vectors(query, k=k_vec, similarity_threshold=similarity_threshold)
        lex = self.search_lexical(query, k=k_lex)
        # Fusión inteligente: combina resultados vectoriales y léxicos con diversidad
        seen, fused = set(), []

        # Priorizar resultados vectoriales (semánticos) primero
        for cand in vec:
            cid = cand["chunk_id"]
            if cid in seen:
                continue
            seen.add(cid)
            # Marcar como resultado semántico
            cand["search_type"] = "semantic"
            fused.append(cand)

        # Agregar resultados léxicos si no hay suficientes
        for cand in lex:
            cid = cand["chunk_id"]
            if cid in seen:
                continue
            seen.add(cid)
            # Marcar como resultado léxico
            cand["search_type"] = "lexical"
            fused.append(cand)
            if len(fused) >= final_k * 2:  # Buscar más para luego filtrar
                break

        # Ordenar por relevancia combinada
        for cand in fused:
            base_score = cand.get("score", 0.0)
            # Bonus por tipo de búsqueda
            if cand.get("search_type") == "semantic":
                base_score += 0.1
            # Bonus por reranked_score si existe
            reranked = cand.get("reranked_score")
            if reranked:
                base_score = reranked
            cand["combined_score"] = base_score

        fused.sort(key=lambda x: x.get("combined_score", 0), reverse=True)

        # Traer textos para los mejores resultados
        texts = self.fetch_texts([c["chunk_id"] for c in fused[:final_k]])
        for c in fused:
            c["text"] = texts.get(c["chunk_id"], "")
        return fused[:final_k]

    def add_to_index(self, texts: List[str], metadata: List[Dict], batch_size: int = 64):
        """Agregar nuevos textos al índice FAISS incrementalmente"""
        if self.embedding_client is None:
            print("⚠️ No se pueden agregar embeddings - cliente no disponible")
            return

        print(f"🔄 Agregando {len(texts)} nuevos textos al índice...")

        # Generar embeddings en lotes
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i+batch_size]
            try:
                response = self.embedding_client.embeddings.create(
                    model=self.embedding_model,
                    input=batch_texts
                )
                batch_embeddings = [np.array(data.embedding, dtype=np.float32)
                                  for data in response.data]
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                print(f"⚠️ Error generando embeddings para lote {i//batch_size}: {e}")
                continue

        if not all_embeddings:
            return

        # Normalizar y agregar al índice
        embeddings_array = np.array(all_embeddings)
        faiss.normalize_L2(embeddings_array)

        # Agregar al índice FAISS
        self.index.add(embeddings_array)

        # Agregar metadatos
        for meta in metadata:
            meta["chunk_id"] = meta.get("chunk_id", str(uuid.uuid4()))
            self.metas.append(meta)

        # Guardar índice actualizado
        self._save_index()
        print(f"✅ Agregados {len(all_embeddings)} vectores al índice. Total: {len(self.metas)}")

    def _save_index(self):
        """Guardar índice y metadatos"""
        try:
            faiss.write_index(self.index, self.faiss_path)
            metas_path = os.path.join(os.path.dirname(self.faiss_path), "metas.jsonl")
            with open(metas_path, "w", encoding="utf-8") as out:
                for m in self.metas:
                    out.write(json.dumps(m, ensure_ascii=False) + "\n")
            print("💾 Índice guardado exitosamente")
        except Exception as e:
            print(f"⚠️ Error guardando índice: {e}")

    def rebuild_index(self, data_dir: str):
        """Reconstruir índice completo desde cero"""
        print(f"🔄 Reconstruyendo índice desde {data_dir}...")
        from .build_index import main as build_main
        build_main(data_dir)
        # Recargar índice
        self.index = faiss.read_index(self.faiss_path)
        metas_path = os.path.join(os.path.dirname(self.faiss_path), "metas.jsonl")
        with open(metas_path, "r", encoding="utf-8") as f:
            self.metas = [json.loads(l) for l in f]
        print("✅ Índice reconstruido y recargado")
