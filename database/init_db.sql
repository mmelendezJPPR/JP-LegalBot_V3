-- Base de datos mínima para conocimiento y FAQs
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS knowledge_facts(
  id TEXT PRIMARY KEY,
  content TEXT NOT NULL,
  citation TEXT NOT NULL,     -- Ej: "Tomo 2 > Cap. III > Art. 12, págs. 120–121"
  type TEXT,                  -- 'definicion','procedimiento','parametro','excepcion','faq'
  tags TEXT,                  -- JSON opcional
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS faqs(
  id TEXT PRIMARY KEY,
  query_normalized TEXT UNIQUE,
  answer TEXT NOT NULL,
  citations TEXT,             -- JSON array de citas
  usage_count INTEGER DEFAULT 0,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chunks_meta(
  chunk_id TEXT PRIMARY KEY,
  doc_id TEXT,
  page_start INTEGER,
  page_end INTEGER,
  heading_path TEXT,
  hash TEXT
);

-- Full-text search para chunks (búsqueda léxica)
CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5(
  chunk_text,
  chunk_id UNINDEXED,
  doc_id UNINDEXED,
  heading_path UNINDEXED,
  page_start UNINDEXED,
  page_end UNINDEXED
);

-- Logs mínimos
CREATE TABLE IF NOT EXISTS query_logs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  query TEXT,
  retrieved_ids TEXT,         -- JSON de chunk_ids/facts/faqs
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
