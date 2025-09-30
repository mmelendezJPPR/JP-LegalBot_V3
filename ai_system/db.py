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
    # Adaptado para la estructura real de la base de datos
    try:
        # La tabla fts_chunks en init_db.sql usa la columna `chunk_text` y columnas
        # adicionales como `chunk_id`, `doc_id`, `heading_path`, `page_start`, `page_end`.
        cur = con.execute("""
            SELECT rowid, chunk_text, chunk_id, doc_id, heading_path, page_start, page_end,
                   snippet(fts_chunks, 0, '«', '»', ' … ', 10) AS snip
            FROM fts_chunks WHERE fts_chunks MATCH ? LIMIT ?
        """, (query, limit))

        results = []
        for row in cur.fetchall():
            # row es sqlite3.Row: acceder por nombre es más claro
            text = row['chunk_text'] if 'chunk_text' in row.keys() else row[1]
            doc_id = row['doc_id'] if 'doc_id' in row.keys() else (row['chunk_id'] if 'chunk_id' in row.keys() else None)
            heading = row['heading_path'] if 'heading_path' in row.keys() else None
            page_start = row['page_start'] if 'page_start' in row.keys() else None
            page_end = row['page_end'] if 'page_end' in row.keys() else None
            snip = row['snip'] if 'snip' in row.keys() else (text[:200] if text else '')

            result = {
                'rowid': row['rowid'] if 'rowid' in row.keys() else row[0],
                'text': text,
                'doc_id': doc_id or '',
                'heading_path': heading or '',
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
