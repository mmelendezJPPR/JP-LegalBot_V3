"""
Sistema de Memoria Semántica para JP-LegalBot V3
Implementa memoria conversacional y a largo plazo usando embeddings
"""

import os
import json
import numpy as np
import faiss
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from openai import AzureOpenAI
from .config import (
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT, DB_PATH
)
from .db import get_conn

class SemanticMemory:
    """
    Sistema de memoria semántica que mantiene contexto conversacional
    y conocimiento a largo plazo usando embeddings vectoriales
    """

    def __init__(self, memory_db_path: str = "database/semantic_memory.db"):
        self.memory_db_path = memory_db_path
        self.embedding_client = None
        self.embedding_model = None

        # Inicializar cliente de embeddings
        if AZURE_OPENAI_KEY and AZURE_OPENAI_EMBEDDING_DEPLOYMENT:
            try:
                self.embedding_client = AzureOpenAI(
                    api_key=AZURE_OPENAI_KEY,
                    api_version=AZURE_OPENAI_API_VERSION,
                    azure_endpoint=AZURE_OPENAI_ENDPOINT
                )
                self.embedding_model = AZURE_OPENAI_EMBEDDING_DEPLOYMENT
                print("✅ Cliente de embeddings inicializado para memoria semántica")
            except Exception as e:
                print(f"⚠️ Error inicializando embeddings para memoria: {e}")
                self.embedding_client = None

        # Inicializar base de datos de memoria
        self._init_memory_db()

        # Índice FAISS para memoria semántica
        self.memory_index_path = "database/memory_faiss_index.bin"
        self.memory_metas_path = "database/memory_metas.jsonl"
        self._load_or_create_memory_index()

    def _init_memory_db(self):
        """Inicializar base de datos para memoria semántica"""
        os.makedirs(os.path.dirname(self.memory_db_path), exist_ok=True)

        with get_conn(self.memory_db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    user_query TEXT NOT NULL,
                    assistant_response TEXT NOT NULL,
                    embedding_vector BLOB,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    importance_score REAL DEFAULT 1.0,
                    access_count INTEGER DEFAULT 0,
                    last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS long_term_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_type TEXT NOT NULL, -- 'fact', 'pattern', 'context'
                    content TEXT NOT NULL,
                    embedding_vector BLOB,
                    confidence REAL DEFAULT 1.0,
                    source TEXT, -- conversation_id or 'learned'
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                    access_count INTEGER DEFAULT 0
                )
            """)

            # Índices para búsqueda eficiente
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_id ON conversation_memories(conversation_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON conversation_memories(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_type ON long_term_memories(memory_type)")

    def _load_or_create_memory_index(self):
        """Cargar o crear índice FAISS para memoria"""
        try:
            self.memory_index = faiss.read_index(self.memory_index_path)
            with open(self.memory_metas_path, 'r', encoding='utf-8') as f:
                self.memory_metas = [json.loads(line) for line in f]
            print(f"✅ Índice de memoria cargado: {len(self.memory_metas)} memorias")
        except:
            # Crear índice vacío
            self.memory_index = faiss.IndexFlatIP(1536)  # Dimensión de text-embedding-3-small
            self.memory_metas = []
            print("🆕 Índice de memoria semántica creado")

    def _embed_text(self, text: str) -> Optional[np.ndarray]:
        """Generar embedding para un texto"""
        if not self.embedding_client:
            return None

        try:
            response = self.embedding_client.embeddings.create(
                model=self.embedding_model,
                input=[text]
            )
            embedding = np.array(response.data[0].embedding, dtype=np.float32)
            faiss.normalize_L2(embedding.reshape(1, -1))
            return embedding.flatten()
        except Exception as e:
            print(f"⚠️ Error generando embedding: {e}")
            return None

    def add_conversation_memory(self, conversation_id: str, user_query: str,
                               assistant_response: str, importance: float = 1.0):
        """Agregar memoria de conversación con embedding"""
        # Crear texto combinado para embedding
        combined_text = f"Pregunta: {user_query}\nRespuesta: {assistant_response}"

        embedding = self._embed_text(combined_text)
        embedding_blob = embedding.tobytes() if embedding is not None else None

        with get_conn(self.memory_db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO conversation_memories
                (conversation_id, user_query, assistant_response, embedding_vector, importance_score)
                VALUES (?, ?, ?, ?, ?)
            """, (conversation_id, user_query, assistant_response, embedding_blob, importance))

            memory_id = cursor.lastrowid

        # Agregar al índice FAISS si tenemos embedding
        if embedding is not None:
            self.memory_index.add(embedding.reshape(1, -1))
            meta = {
                "id": memory_id,
                "conversation_id": conversation_id,
                "type": "conversation",
                "text": combined_text[:500],  # Truncar para metadata
                "importance": importance
            }
            self.memory_metas.append(meta)

            # Guardar índice actualizado
            self._save_memory_index()

        print(f"✅ Memoria conversacional agregada: {conversation_id}")

    def retrieve_relevant_memories(self, query: str, conversation_id: str = None,
                                  limit: int = 5, days_back: int = 30) -> List[Dict]:
        """Recuperar memorias relevantes usando búsqueda semántica"""
        if not self.embedding_client:
            return self._retrieve_lexical_memories(query, conversation_id, limit, days_back)

        query_embedding = self._embed_text(query)
        if query_embedding is None:
            return self._retrieve_lexical_memories(query, conversation_id, limit, days_back)

        # Búsqueda semántica en FAISS
        D, I = self.memory_index.search(query_embedding.reshape(1, -1), limit * 2)

        relevant_memories = []
        for score, idx in zip(D[0], I[0]):
            if idx == -1 or idx >= len(self.memory_metas):
                continue

            meta = self.memory_metas[idx]
            if meta["type"] == "conversation":
                # Obtener detalles completos de la base de datos
                memory_details = self._get_memory_details(meta["id"])
                if memory_details:
                    memory_details["similarity_score"] = float(score)
                    relevant_memories.append(memory_details)

        # Filtrar por conversación si especificada y ordenar por relevancia
        if conversation_id:
            relevant_memories = [m for m in relevant_memories
                               if m.get("conversation_id") == conversation_id]

        # Ordenar por puntuación de similitud y limitar
        relevant_memories.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
        return relevant_memories[:limit]

    def _retrieve_lexical_memories(self, query: str, conversation_id: str = None,
                                  limit: int = 5, days_back: int = 30) -> List[Dict]:
        """Búsqueda léxica como fallback cuando no hay embeddings"""
        cutoff_date = datetime.now() - timedelta(days=days_back)

        with get_conn(self.memory_db_path) as conn:
            if conversation_id:
                cursor = conn.execute("""
                    SELECT id, conversation_id, user_query, assistant_response,
                           importance_score, timestamp
                    FROM conversation_memories
                    WHERE conversation_id = ? AND timestamp > ?
                    ORDER BY importance_score DESC, timestamp DESC
                    LIMIT ?
                """, (conversation_id, cutoff_date.isoformat(), limit))
            else:
                cursor = conn.execute("""
                    SELECT id, conversation_id, user_query, assistant_response,
                           importance_score, timestamp
                    FROM conversation_memories
                    WHERE timestamp > ?
                    ORDER BY importance_score DESC, timestamp DESC
                    LIMIT ?
                """, (cutoff_date.isoformat(), limit))

            memories = []
            for row in cursor.fetchall():
                memories.append({
                    "id": row[0],
                    "conversation_id": row[1],
                    "user_query": row[2],
                    "assistant_response": row[3],
                    "importance_score": row[4],
                    "timestamp": row[5],
                    "similarity_score": 0.5  # Puntaje neutral para búsqueda léxica
                })

            return memories

    def _get_memory_details(self, memory_id: int) -> Optional[Dict]:
        """Obtener detalles completos de una memoria"""
        with get_conn(self.memory_db_path) as conn:
            cursor = conn.execute("""
                SELECT id, conversation_id, user_query, assistant_response,
                       importance_score, timestamp, access_count
                FROM conversation_memories
                WHERE id = ?
            """, (memory_id,))

            row = cursor.fetchone()
            if row:
                # Actualizar contador de acceso
                conn.execute("""
                    UPDATE conversation_memories
                    SET access_count = access_count + 1, last_accessed = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (memory_id,))

                return {
                    "id": row[0],
                    "conversation_id": row[1],
                    "user_query": row[2],
                    "assistant_response": row[3],
                    "importance_score": row[4],
                    "timestamp": row[5],
                    "access_count": row[6]
                }
        return None

    def _save_memory_index(self):
        """Guardar índice FAISS y metadatos"""
        try:
            faiss.write_index(self.memory_index, self.memory_index_path)
            with open(self.memory_metas_path, 'w', encoding='utf-8') as f:
                for meta in self.memory_metas:
                    f.write(json.dumps(meta, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"⚠️ Error guardando índice de memoria: {e}")

    def consolidate_memories(self, conversation_id: str = None):
        """Consolidar memorias importantes en conocimiento a largo plazo"""
        # Obtener memorias con alta importancia y frecuencia de acceso
        with get_conn(self.memory_db_path) as conn:
            if conversation_id:
                cursor = conn.execute("""
                    SELECT user_query, assistant_response, importance_score, access_count
                    FROM conversation_memories
                    WHERE conversation_id = ? AND access_count > 2
                    ORDER BY importance_score DESC, access_count DESC
                    LIMIT 10
                """, (conversation_id,))
            else:
                cursor = conn.execute("""
                    SELECT user_query, assistant_response, importance_score, access_count
                    FROM conversation_memories
                    WHERE access_count > 3
                    ORDER BY importance_score DESC, access_count DESC
                    LIMIT 20
                """)

            candidates = cursor.fetchall()

        # Crear memorias consolidadas
        for user_query, response, importance, access_count in candidates:
            # Generar resumen o patrón
            summary = self._generate_memory_summary(user_query, response)

            if summary:
                self._add_long_term_memory("pattern", summary, importance * 0.8)

    def _generate_memory_summary(self, query: str, response: str) -> str:
        """Generar resumen de una interacción para memoria a largo plazo"""
        if not self.embedding_client:
            return f"Patrón: {query[:100]} -> {response[:200]}"

        try:
            prompt = f"""
            Resume esta interacción de manera concisa para memoria a largo plazo:

            Pregunta del usuario: {query}

            Respuesta del asistente: {response}

            Resumen (máximo 150 caracteres):
            """

            response = self.embedding_client.chat.completions.create(
                model="gpt-4.1",  # Usar modelo de chat para resumen
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0.3
            )

            summary = response.choices[0].message.content.strip()
            return summary if len(summary) <= 150 else summary[:147] + "..."

        except Exception as e:
            print(f"⚠️ Error generando resumen: {e}")
            return f"Interacción: {query[:50]}..."

    def _add_long_term_memory(self, memory_type: str, content: str, confidence: float = 1.0):
        """Agregar memoria a largo plazo"""
        embedding = self._embed_text(content)
        embedding_blob = embedding.tobytes() if embedding is not None else None

        with get_conn(self.memory_db_path) as conn:
            conn.execute("""
                INSERT INTO long_term_memories
                (memory_type, content, embedding_vector, confidence)
                VALUES (?, ?, ?, ?)
            """, (memory_type, content, embedding_blob, confidence))

        print(f"✅ Memoria a largo plazo agregada: {memory_type}")

    def get_long_term_memories(self, query: str, limit: int = 5) -> List[Dict]:
        """Recuperar memorias a largo plazo relevantes"""
        if not self.embedding_client:
            return []

        query_embedding = self._embed_text(query)
        if query_embedding is None:
            return []

        # Obtener todas las memorias a largo plazo con embeddings
        with get_conn(self.memory_db_path) as conn:
            cursor = conn.execute("""
                SELECT id, memory_type, content, confidence
                FROM long_term_memories
                WHERE embedding_vector IS NOT NULL
                ORDER BY confidence DESC
            """)

            memories = []
            embeddings = []
            for row in cursor.fetchall():
                # Aquí necesitaríamos deserializar el embedding, pero por simplicidad
                # usaremos búsqueda léxica por ahora
                memories.append({
                    "id": row[0],
                    "type": row[1],
                    "content": row[2],
                    "confidence": row[3]
                })

        # Para una implementación completa, necesitaríamos un índice FAISS separado
        # Por ahora, devolver las más relevantes por confianza
        return memories[:limit]

    def get_conversation_context(self, conversation_id: str, current_query: str = None) -> str:
        """Obtener contexto conversacional relevante"""
        if current_query:
            memories = self.retrieve_relevant_memories(current_query, conversation_id, limit=3)
        else:
            memories = self._retrieve_lexical_memories(None, conversation_id, limit=3)

        if not memories:
            return ""

        context_parts = []
        for memory in memories:
            context_parts.append(f"Usuario: {memory['user_query']}")
            context_parts.append(f"Asistente: {memory['assistant_response'][:300]}...")

        return "\n".join(context_parts)

    def cleanup_old_memories(self, days_to_keep: int = 90):
        """Limpiar memorias antiguas menos importantes"""
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)

        with get_conn(self.memory_db_path) as conn:
            # Eliminar memorias antiguas con baja importancia
            conn.execute("""
                DELETE FROM conversation_memories
                WHERE timestamp < ? AND importance_score < 1.5 AND access_count < 3
            """, (cutoff_date.isoformat(),))

            deleted_count = conn.total_changes
            print(f"🧹 Limpieza completada: {deleted_count} memorias antiguas eliminadas")