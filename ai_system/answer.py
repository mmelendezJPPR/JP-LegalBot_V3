from typing import Dict, List
from openai import AzureOpenAI
from .config import (
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, AZURE_OPENAI_API_VERSION, 
    AZURE_OPENAI_DEPLOYMENT_NAME
)
from .prompts import SYSTEM_RAG, USER_TEMPLATE
from .retrieve import HybridRetriever

class AnswerEngine:
    def __init__(self, retriever: HybridRetriever):
        self.retriever = retriever
        
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

    def answer(self, query: str, k=6) -> Dict:
        ctx = self.retriever.hybrid(query, final_k=k)
        context_text = self.format_context(ctx)
        user_msg = USER_TEMPLATE.format(query=query, context=context_text)

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
