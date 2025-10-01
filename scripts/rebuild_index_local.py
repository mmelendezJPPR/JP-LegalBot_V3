#!/usr/bin/env python3
"""
REBUILD_INDEX_LOCAL.PY - Reconstruye el índice FAISS con embeddings locales
===========================================================================

🎯 FUNCIÓN PRINCIPAL:
   Reconstruir el índice FAISS usando embeddings locales en lugar de OpenAI.
   Esto es necesario porque el índice existente fue creado con embeddings
   de OpenAI (1536 dims) pero ahora usamos embeddings locales (384 dims).

🏗️ PROCESO:
   1. Leer documentos desde la base de datos SQLite
   2. Generar embeddings locales para cada documento
   3. Crear nuevo índice FAISS con embeddings locales
   4. Guardar índice y metadata actualizados

📋 REQUISITOS:
   - Base de datos SQLite con documentos (database/hybrid_knowledge.db)
   - Modelo de embeddings locales disponible
   - Espacio suficiente para el nuevo índice (~2-3x tamaño original)

⚠️ ATENCIÓN:
   - Este proceso puede tomar tiempo dependiendo del número de documentos
   - El índice anterior será sobrescrito
   - Asegúrate de tener backup antes de ejecutar

=======================================================================
"""

import os
import sys
import json
import sqlite3
import numpy as np
from typing import List, Dict
from tqdm import tqdm

# Agregar directorio padre al path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from ai_system.local_embeddings import LocalEmbeddings
from ai_system.config import DB_PATH, FAISS_PATH

def get_documents_from_db(db_path: str) -> List[Dict]:
    """
    Extraer documentos desde la base de datos SQLite

    Args:
        db_path: Ruta a la base de datos

    Returns:
        Lista de documentos con metadata
    """
    documents = []

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Obtener todos los documentos con su metadata
        cursor.execute("""
            SELECT rowid, content, tomo, capitulo, articulo, tipo_seccion, fuente
            FROM fts_chunks
            ORDER BY rowid
        """)

        rows = cursor.fetchall()
        print(f"📄 Encontrados {len(rows)} documentos en fts_chunks")

        for row in rows:
            rowid, content, tomo, capitulo, articulo, tipo_seccion, fuente = row

            # Crear metadata completa
            metadata = {
                "id": rowid,  # Usar rowid como id
                "chunk_id": str(rowid),  # Agregar chunk_id como string
                "content": content,
                "tomo": tomo or "Desconocido",
                "capitulo": capitulo or "Desconocido",
                "articulo": articulo or "Desconocido",
                "tipo_seccion": tipo_seccion or "Desconocido",
                "fuente": fuente or "Desconocido"
            }
            documents.append(metadata)

        conn.close()
        return documents

    except Exception as e:
        print(f"❌ Error al leer base de datos: {e}")
        return []

def rebuild_index_with_local_embeddings():
    """
    Reconstruir índice FAISS usando embeddings locales
    """
    print("🔄 RECONSTRUYENDO ÍNDICE FAISS CON EMBEDDINGS LOCALES")
    print("=" * 60)

    # 1. Verificar archivos existentes
    print("\n1. Verificando archivos existentes...")
    if not os.path.exists(DB_PATH):
        print(f"❌ Base de datos no encontrada: {DB_PATH}")
        return False

    backup_index = FAISS_PATH + ".backup"
    if os.path.exists(FAISS_PATH):
        print(f"📋 Creando backup del índice existente: {backup_index}")
        import shutil
        shutil.copy2(FAISS_PATH, backup_index)

    # 2. Inicializar embeddings locales
    print("\n2. Inicializando embeddings locales...")
    try:
        embedder = LocalEmbeddings()
        print(f"✅ Embeddings locales inicializados: {embedder.model_name}")
    except Exception as e:
        print(f"❌ Error inicializando embeddings: {e}")
        return False

    # 3. Leer documentos desde la base de datos
    print("\n3. Leyendo documentos desde la base de datos...")
    documents = get_documents_from_db(DB_PATH)
    if not documents:
        print("❌ No se encontraron documentos en la base de datos")
        return False

    print(f"📄 Procesando {len(documents)} documentos...")

    # 4. Generar embeddings para todos los documentos
    print("\n4. Generando embeddings (esto puede tomar tiempo)...")
    texts = [doc["content"] for doc in documents]

    try:
        embeddings = embedder.encode_texts(texts)
        print(f"✅ Embeddings generados: shape {embeddings.shape}")
    except Exception as e:
        print(f"❌ Error generando embeddings: {e}")
        return False

    # 5. Crear nuevo índice FAISS
    print("\n5. Creando nuevo índice FAISS...")
    try:
        embedder.create_index(embeddings, documents)
        print(f"✅ Índice creado con {embedder.index.ntotal} vectores")
    except Exception as e:
        print(f"❌ Error creando índice: {e}")
        return False

    # 6. Guardar índice y metadata
    print("\n6. Guardando índice y metadata...")
    try:
        # Crear directorio si no existe
        os.makedirs(os.path.dirname(FAISS_PATH), exist_ok=True)

        # Guardar índice FAISS
        embedder.save_index(FAISS_PATH)

        # Guardar metadata en el formato esperado por HybridRetriever (metas.jsonl)
        metas_path = os.path.join(os.path.dirname(FAISS_PATH), "metas.jsonl")
        with open(metas_path, 'w', encoding='utf-8') as f:
            # HybridRetriever espera una lista de objetos JSON, uno por línea
            for meta in embedder.metadata:
                json.dump(meta, f, ensure_ascii=False)
                f.write('\n')

        print("✅ Índice reconstruido exitosamente!")
        print(f"   📁 Índice: {FAISS_PATH}")
        print(f"   📋 Metadata: {metas_path}")
        print(f"   📊 Vectores: {embedder.index.ntotal}")
        print(f"   📏 Dimensión: {embedder.dimension}")

        # Mostrar estadísticas
        stats = embedder.get_stats()
        print("\n📈 Estadísticas finales:")
        for key, value in stats.items():
            print(f"   {key}: {value}")

        return True

    except Exception as e:
        print(f"❌ Error guardando índice: {e}")
        return False

def test_rebuilt_index():
    """
    Probar que el índice reconstruido funciona correctamente
    """
    print("\n🧪 Probando índice reconstruido...")

    try:
        from ai_system.retrieve import HybridRetriever

        retriever = HybridRetriever()
        print("✅ HybridRetriever inicializado con nuevo índice")

        # Probar búsqueda
        query = "¿Qué regula la Junta de Planificación?"
        results = retriever.search_vectors(query, k=3)

        print(f"🔍 Consulta de prueba: '{query}'")
        print(f"📊 Resultados encontrados: {len(results)}")

        for i, result in enumerate(results, 1):
            score = result.get('score', 0)
            content = result.get('content', '')[:100]
            print(f"   {i}. Score={score:.3f} | {content}...")

        return len(results) > 0

    except Exception as e:
        print(f"❌ Error probando índice: {e}")
        return False

    except Exception as e:
        print(f"❌ Error probando índice: {e}")
        return False

def main():
    """Función principal"""
    print("🚀 JP-LegalBot - Reconstrucción de Índice con Embeddings Locales")
    print("=" * 70)

    # Confirmar antes de proceder
    response = input("\n⚠️  Esto sobrescribirá el índice FAISS existente. ¿Continuar? (y/N): ")
    if response.lower() not in ['y', 'yes', 's', 'si']:
        print("❌ Operación cancelada por el usuario")
        return

    # Ejecutar reconstrucción
    success = rebuild_index_with_local_embeddings()

    if success:
        print("\n🎉 ¡Índice reconstruido exitosamente!")

        # Probar el índice
        if test_rebuilt_index():
            print("✅ Índice probado y funcionando correctamente")
        else:
            print("⚠️ Índice creado pero hay problemas con las búsquedas")

        print("\n💡 El sistema ahora usa embeddings locales para búsquedas semánticas")
        print("   No se requieren APIs externas para embeddings")

    else:
        print("\n❌ Error en la reconstrucción del índice")
        print("   Revisa los logs de error arriba")

if __name__ == "__main__":
    main()