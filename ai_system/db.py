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
        cur = con.execute("""SELECT rowid, content, tomo, capitulo, articulo, tipo_seccion, fuente,
                               snippet(fts_chunks, 0, '«', '»', ' … ', 10) AS snip
                            FROM fts_chunks WHERE fts_chunks MATCH ? LIMIT ?""", (query, limit))
        results = []
        for row in cur.fetchall():
            # Convertir a formato esperado por el sistema
            result = {
                'rowid': row[0],
                'text': row[1],  # content -> text
                'doc_id': f"{row[2]}_{row[3]}_{row[4]}",  # tomo_capitulo_articulo
                'heading_path': f"Tomo {row[2]} - {row[3]} - {row[4]}",
                'page_start': None,
                'page_end': None,
                'snip': row[7] if len(row) > 7 else row[1][:200]
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
