import sqlite3, json
from contextlib import contextmanager

@contextmanager
def get_conn(db_path: str):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()

def upsert_chunk(con, chunk_id, doc_id, page_start, page_end, heading_path, text):
    con.execute("""INSERT OR REPLACE INTO chunks_meta(chunk_id, doc_id, page_start, page_end, heading_path, hash)
                 VALUES(?, ?, ?, ?, ?, HEX(RANDOMBLOB(8)))""", 
                 (chunk_id, doc_id, page_start, page_end, heading_path))
    con.execute("""INSERT INTO fts_chunks(chunk_text, chunk_id, doc_id, heading_path, page_start, page_end)
                 VALUES(?,?,?,?,?,?)""", 
                 (text, chunk_id, doc_id, heading_path, page_start, page_end))

def fts_search(con, query: str, limit: int = 24):
    # Adaptado para la estructura real de la base de datos existente
    try:
        # Sanitizar la consulta para FTS5 - remover caracteres problemáticos
        import re
        # Mantener solo letras, números, espacios y operadores FTS básicos
        sanitized_query = re.sub(r'[^\w\s]', ' ', query)
        # Normalizar espacios múltiples
        sanitized_query = ' '.join(sanitized_query.split())
        # Si la consulta queda vacía, usar la original
        if not sanitized_query.strip():
            sanitized_query = query

        print(f"🔍 Consulta FTS: '{sanitized_query}' (original: '{query}')")

        # La tabla fts_chunks actual tiene columnas: content, tomo, capitulo, articulo, tipo_seccion, fuente
        cur = con.execute("""
            SELECT rowid, content, tomo, capitulo, articulo, tipo_seccion, fuente,
                   snippet(fts_chunks, 0, '«', '»', ' … ', 10) AS snip
            FROM fts_chunks WHERE fts_chunks MATCH ? LIMIT ?
        """, (sanitized_query, limit))

        results = []
        for row in cur.fetchall():
            # Adaptar nombres de columnas a la estructura esperada
            text = row['content'] if 'content' in row.keys() else row[1]
            doc_id = row['fuente'] if 'fuente' in row.keys() else (row['tomo'] if 'tomo' in row.keys() else None)
            heading = f"TOMO {row['tomo']}" if row['tomo'] else ""
            if row['capitulo']:
                heading += f" > CAPÍTULO {row['capitulo']}"
            if row['articulo']:
                heading += f" > ARTÍCULO {row['articulo']}"
            page_start = None  # No disponible en estructura actual
            page_end = None    # No disponible en estructura actual
            snip = row['snip'] if 'snip' in row.keys() else (text[:200] if text else '')

            result = {
                'rowid': row['rowid'] if 'rowid' in row.keys() else row[0],
                'chunk_id': str(row['rowid'] if 'rowid' in row.keys() else row[0]),  # Agregar chunk_id como rowid
                'text': text,
                'doc_id': doc_id or '',
                'heading_path': heading,
                'page_start': page_start,
                'page_end': page_end,
                'snip': snip
            }
            results.append(result)
        return results
    except Exception as e:
        print(f"Error en fts_search: {e}")
        return []

def insert_knowledge_fact(con, fact_id, content, citation, type_, tags=None):
    con.execute("""INSERT OR REPLACE INTO knowledge_facts(id, content, citation, type, tags)
                 VALUES(?,?,?,?,?)""", (fact_id, content, citation, type_, json.dumps(tags or {})))

def upsert_faq(con, faq_id, query_normalized, answer, citations):
    con.execute("""INSERT INTO faqs(id, query_normalized, answer, citations, usage_count)
                 VALUES(?,?,?,?,0)
                 ON CONFLICT(query_normalized) DO UPDATE SET
                   answer=excluded.answer,
                   citations=excluded.citations,
                   usage_count=faqs.usage_count+1,
                   updated_at=CURRENT_TIMESTAMP
                 """, (faq_id, query_normalized, answer, json.dumps(citations)))
