from typing import Dict, List
from openai import AzureOpenAI
from .config import (
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, AZURE_OPENAI_API_VERSION, 
    AZURE_OPENAI_DEPLOYMENT_NAME
)
from .prompts import SYSTEM_RAG, USER_TEMPLATE
from .retrieve import HybridRetriever
from .semantic_memory import SemanticMemory
from .db import get_conn

class AnswerEngine:
    def __init__(self, retriever: HybridRetriever, use_semantic_memory: bool = True):
        self.retriever = retriever
        self.use_semantic_memory = use_semantic_memory
        
        # Inicializar memoria semántica
        if use_semantic_memory:
            try:
                self.semantic_memory = SemanticMemory()
                print("✅ Memoria semántica inicializada")
            except Exception as e:
                print(f"⚠️ Error inicializando memoria semántica: {e}")
                self.semantic_memory = None
        else:
            self.semantic_memory = None
        
        # Validar configuración antes de crear cliente
        if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_ENDPOINT.startswith('http'):
            raise ValueError(f"AZURE_OPENAI_ENDPOINT inválido: '{AZURE_OPENAI_ENDPOINT}'. Debe comenzar con https://")
            
        if not AZURE_OPENAI_KEY or len(AZURE_OPENAI_KEY) < 10:
            raise ValueError(f"AZURE_OPENAI_KEY inválido o faltante (longitud: {len(AZURE_OPENAI_KEY)})")
        
        print(f"🔧 Configurando cliente Azure OpenAI:")
        print(f"   📡 Endpoint: {AZURE_OPENAI_ENDPOINT}")
        print(f"   🔑 API Key: {'*' * (len(AZURE_OPENAI_KEY) - 8) + AZURE_OPENAI_KEY[-8:]}")
        print(f"   🚀 Deployment: {AZURE_OPENAI_DEPLOYMENT_NAME}")
        print(f"   📅 API Version: {AZURE_OPENAI_API_VERSION}")
        
        self.client = AzureOpenAI(
            api_key=AZURE_OPENAI_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT
        )

    def format_context(self, items: List[Dict]) -> str:
        lines = []
        for i, it in enumerate(items, 1):
            cite = it.get("heading_path") or it.get("doc_id", "")
            pg = ""
            ps, pe = it.get("page_start"), it.get("page_end")
            if ps or pe:
                pg = f", págs. {ps or ''}-{pe or ''}"
            lines.append(f"[{i}] ({cite}{pg})\n{it.get('text','')[:1800]}")
        return "\n\n".join(lines)

    def answer(self, query: str, k=6, conversation_id: str = None) -> Dict:
        # Obtener contexto de documentos relevantes
        ctx = self.retriever.hybrid(query, final_k=k)
        context_text = self.format_context(ctx)
        
        # Obtener contexto conversacional si está disponible
        conversation_context = ""
        if self.semantic_memory and conversation_id:
            try:
                conversation_context = self.semantic_memory.get_conversation_context(conversation_id, query)
                if conversation_context:
                    conversation_context = f"\n\nCONTEXTO CONVERSACIONAL PREVIO:\n{conversation_context}\n"
                    print(f"🧠 Contexto conversacional recuperado: {len(conversation_context)} chars")
            except Exception as e:
                print(f"⚠️ Error obteniendo contexto conversacional: {e}")
        
        # Construir mensaje del usuario con contexto completo
        full_context = f"{conversation_context}\nCONTEXTO DOCUMENTAL:\n{context_text}"
        user_msg = USER_TEMPLATE.format(query=query, context=full_context)

        resp = self.client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_RAG},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.2
        )
        text = resp.choices[0].message.content

        citations = []
        for it in ctx:
            cite = it.get("heading_path") or it.get("doc_id","")
            ps, pe = it.get("page_start"), it.get("page_end")
            pg = f", págs. {ps or ''}-{pe or ''}" if (ps or pe) else ""
            citations.append(f"[{cite}{pg}]")

        return {"text": text, "citations": citations, "context_items": ctx}

    def store_conversation_memory(self, conversation_id: str, query: str, response: str, importance: float = 1.0):
        """Almacenar interacción en memoria semántica"""
        if self.semantic_memory:
            try:
                self.semantic_memory.add_conversation_memory(
                    conversation_id=conversation_id,
                    user_query=query,
                    assistant_response=response,
                    importance=importance
                )
            except Exception as e:
                print(f"⚠️ Error almacenando memoria conversacional: {e}")

    def answer_with_memory(self, query: str, conversation_id: str, k=6, store_memory: bool = True) -> Dict:
        """Método conveniente que incluye almacenamiento de memoria"""
        result = self.answer(query, k=k, conversation_id=conversation_id)
        
        if store_memory and self.semantic_memory:
            self.store_conversation_memory(
                conversation_id=conversation_id,
                query=query,
                response=result["text"]
            )
            
            # Consolidar memorias periódicamente (cada 10 interacciones)
            try:
                with get_conn(self.semantic_memory.memory_db_path) as conn:
                    cursor = conn.execute("SELECT COUNT(*) FROM conversation_memories")
                    count = cursor.fetchone()[0]
                    if count % 10 == 0:  # Cada 10 memorias
                        self.semantic_memory.consolidate_memories(conversation_id)
                        print(f"🧠 Consolidadas memorias para conversación {conversation_id}")
            except Exception as e:
                print(f"⚠️ Error en consolidación de memoria: {e}")
        
        return result
