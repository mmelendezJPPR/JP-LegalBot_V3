from typing import List, Dict, Tuple
import re

def split_into_blocks(text: str, max_chars: int = 4000, overlap: int = 600) -> List[str]:
    # Split por dobles saltos + párrafos; si muy largos, corta por oraciones.
    parts = re.split(r"\n\s*\n+", text)
    blocks = []
    buf = ''
    for p in parts:
        if len(buf) + len(p) + 2 <= max_chars:
            buf += (('\n\n' if buf else '') + p)
        else:
            if buf:
                blocks.append(buf)
            buf = p
    if buf:
        blocks.append(buf)

    # Aplica solapamiento simple
    out = []
    for b in blocks:
        if len(b) <= max_chars:
            out.append(b)
        else:
            i = 0
            while i < len(b):
                out.append(b[i:i+max_chars])
                i += max(1, max_chars - overlap)
    return out

def guess_metadata_from_text(block: str) -> Dict:
    # Heurística básica: buscar TOMO/CAP/ART y números de páginas si aparecen
    heading = None
    m = re.search(r"(TOMO\s*\d+.*)?(CAP[ÍI]TULO\s*[^\n]+)?(ART[ÍI]CULO\s*\d+)?", block, re.IGNORECASE)
    if m:
        heading = ' > '.join([x.strip() for x in m.groups() if x])
    return {
        "heading_path": heading or ""
    }
