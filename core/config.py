import os
from dotenv import load_dotenv

load_dotenv()

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")

# Fallback OpenAI (legacy)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL_EMBED = os.getenv("MODEL_EMBED", "text-embedding-3-small")
MODEL_CHAT = os.getenv("MODEL_CHAT", "gpt-4o-mini")

DB_PATH = os.getenv("DB_PATH", "hybrid_knowledge.db")
FAISS_PATH = os.getenv("FAISS_PATH", "faiss_index.bin")

# Chunking
CHUNK_TOKENS = int(os.getenv("CHUNK_TOKENS", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
