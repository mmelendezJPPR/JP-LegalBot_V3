#!/usr/bin/env python3
"""
LOCAL_EMBEDDINGS.PY - Sistema de Embeddings Locales para JP-LegalBot
=======================================================================

🎯 FUNCIÓN PRINCIPAL:
   Este módulo implementa embeddings locales usando SentenceTransformer
   y FAISS para búsqueda semántica sin depender de APIs externas.

🏗️ ARQUITECTURA:
   - Modelo: intfloat/multilingual-e5-small (multilingüe español/inglés)
   - Vectorización: SentenceTransformer con normalización coseno
   - Indexación: FAISS IndexFlatIP para búsqueda eficiente
   - Persistencia: Guardado/carga de índices en disco

📋 COMPONENTES PRINCIPALES:
   1. LocalEmbeddings: Clase principal para generar embeddings
   2. Modelo multilingüe optimizado para texto legal
   3. Indexación FAISS con Inner Product (coseno normalizado)
   4. Métodos para búsqueda semántica y gestión de índices

🔧 CONFIGURACIÓN:
   - Modelo: intfloat/multilingual-e5-small (~24MB)
   - Dimensión: 384 (reducida para velocidad)
   - Normalización: True (coseno similarity)
   - Device: CPU (compatible con cualquier sistema)

⚡ VENTAJAS:
   - Sin costos de API
   - Funciona offline
   - Privacidad total de datos
   - Velocidad razonable para datasets medianos

=======================================================================
"""

import os
import json
import numpy as np
import faiss
from typing import List, Dict, Optional, Tuple
from sentence_transformers import SentenceTransformer
import logging

logger = logging.getLogger(__name__)

class LocalEmbeddings:
    """
    Sistema de embeddings locales usando SentenceTransformer + FAISS
    """

    def __init__(self, model_name: str = "intfloat/multilingual-e5-small",
                 cache_dir: str = None):
        """
        Inicializar el sistema de embeddings locales

        Args:
            model_name: Nombre del modelo SentenceTransformer
            cache_dir: Directorio para cache de modelos (opcional)
        """
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.model = None
        self.index = None
        self.metadata = []
        self.dimension = 384  # Dimensión del modelo multilingual-e5-small

        logger.info(f"🔧 Inicializando LocalEmbeddings con modelo: {model_name}")

        try:
            # Cargar modelo con configuración optimizada
            self.model = SentenceTransformer(
                model_name,
                cache_folder=cache_dir,
                device='cpu'  # Siempre CPU para compatibilidad
            )
            logger.info("✅ Modelo de embeddings cargado exitosamente")

        except Exception as e:
            logger.error(f"❌ Error cargando modelo {model_name}: {e}")
            raise

    def encode_texts(self, texts: List[str],
                    normalize_embeddings: bool = True) -> np.ndarray:
        """
        Generar embeddings para una lista de textos

        Args:
            texts: Lista de textos a vectorizar
            normalize_embeddings: Normalizar para similitud coseno

        Returns:
            Array numpy con embeddings (shape: n_texts x dimension)
        """
        if self.model is None:
            raise ValueError("Modelo no inicializado")

        try:
            embeddings = self.model.encode(
                texts,
                normalize_embeddings=normalize_embeddings,
                show_progress_bar=False
            )

            # Convertir a float32 para FAISS
            embeddings = np.array(embeddings, dtype=np.float32)

            logger.debug(f"📊 Generados {len(embeddings)} embeddings de dimensión {embeddings.shape[1]}")
            return embeddings

        except Exception as e:
            logger.error(f"❌ Error generando embeddings: {e}")
            raise

    def encode_query(self, query: str) -> np.ndarray:
        """
        Generar embedding para una consulta (siempre normalizado)

        Args:
            query: Texto de consulta

        Returns:
            Vector de embedding (shape: 1 x dimension)
        """
        return self.encode_texts([query], normalize_embeddings=True)

    def create_index(self, embeddings: np.ndarray,
                    metadata: List[Dict] = None) -> faiss.Index:
        """
        Crear índice FAISS desde embeddings

        Args:
            embeddings: Array de embeddings
            metadata: Lista de metadatos correspondiente

        Returns:
            Índice FAISS creado
        """
        if embeddings.shape[1] != self.dimension:
            raise ValueError(f"Dimensión de embeddings {embeddings.shape[1]} no coincide con modelo {self.dimension}")

        # Crear índice FAISS con Inner Product (coseno si normalizamos)
        self.index = faiss.IndexFlatIP(self.dimension)
        self.index.add(embeddings)

        # Guardar metadata si se proporciona
        if metadata:
            self.metadata = metadata
        else:
            self.metadata = [{"id": i} for i in range(len(embeddings))]

        logger.info(f"✅ Índice FAISS creado con {self.index.ntotal} vectores")
        return self.index

    def search(self, query_embedding: np.ndarray, k: int = 5,
              threshold: float = 0.0) -> Tuple[np.ndarray, np.ndarray, List[Dict]]:
        """
        Buscar los k vectores más similares

        Args:
            query_embedding: Embedding de la consulta
            k: Número de resultados a retornar
            threshold: Umbral mínimo de similitud

        Returns:
            Tuple de (scores, indices, metadata)
        """
        if self.index is None:
            raise ValueError("Índice no creado. Use create_index() primero")

        # Ajustar k al tamaño del índice
        k = min(k, self.index.ntotal)

        # Buscar
        scores, indices = self.index.search(query_embedding, k)

        # Filtrar por threshold y preparar resultados
        results = []
        filtered_scores = []
        filtered_indices = []

        for score, idx in zip(scores[0], indices[0]):
            if idx != -1 and score >= threshold:
                filtered_scores.append(score)
                filtered_indices.append(idx)
                results.append(self.metadata[idx])

        # Convertir a arrays numpy
        filtered_scores = np.array(filtered_scores)
        filtered_indices = np.array(filtered_indices)

        logger.debug(f"🔍 Búsqueda completada: {len(results)} resultados encontrados")
        return filtered_scores, filtered_indices, results

    def search_text(self, query: str, k: int = 5,
                   threshold: float = 0.0) -> List[Dict]:
        """
        Buscar texto similar usando consulta en texto plano

        Args:
            query: Consulta en texto
            k: Número de resultados
            threshold: Umbral de similitud

        Returns:
            Lista de resultados con scores y metadata
        """
        query_embedding = self.encode_query(query)
        scores, indices, metadata = self.search(query_embedding, k, threshold)

        # Combinar resultados
        results = []
        for score, meta in zip(scores, metadata):
            result = {
                "score": float(score),
                **meta
            }
            results.append(result)

        return results

    def save_index(self, index_path: str, metadata_path: str = None):
        """
        Guardar índice FAISS y metadata en disco

        Args:
            index_path: Ruta para guardar el índice
            metadata_path: Ruta para guardar metadata (opcional)
        """
        if self.index is None:
            raise ValueError("No hay índice para guardar")

        # Crear directorio si no existe
        os.makedirs(os.path.dirname(index_path), exist_ok=True)

        # Guardar índice FAISS
        faiss.write_index(self.index, index_path)
        logger.info(f"💾 Índice guardado en: {index_path}")

        # Guardar metadata si se especifica ruta
        if metadata_path:
            os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
            logger.info(f"💾 Metadata guardada en: {metadata_path}")

    def load_index(self, index_path: str, metadata_path: str = None):
        """
        Cargar índice FAISS y metadata desde disco

        Args:
            index_path: Ruta del índice guardado
            metadata_path: Ruta de la metadata (opcional)
        """
        if not os.path.exists(index_path):
            raise FileNotFoundError(f"Índice no encontrado: {index_path}")

        # Cargar índice FAISS
        self.index = faiss.read_index(index_path)
        logger.info(f"📂 Índice cargado desde: {index_path}")

        # Cargar metadata si existe
        if metadata_path and os.path.exists(metadata_path):
            with open(metadata_path, 'r', encoding='utf-8') as f:
                self.metadata = json.load(f)
            logger.info(f"📂 Metadata cargada desde: {metadata_path}")
        else:
            # Crear metadata dummy si no existe
            self.metadata = [{"id": i} for i in range(self.index.ntotal)]
            logger.warning("⚠️ Metadata no encontrada, usando IDs dummy")

    def get_stats(self) -> Dict:
        """
        Obtener estadísticas del sistema de embeddings

        Returns:
            Diccionario con estadísticas
        """
        stats = {
            "model_name": self.model_name,
            "dimension": self.dimension,
            "model_loaded": self.model is not None,
            "index_created": self.index is not None,
            "vectors_count": self.index.ntotal if self.index else 0,
            "metadata_count": len(self.metadata)
        }
        return stats

    def __repr__(self) -> str:
        """Representación string del objeto"""
        stats = self.get_stats()
        return (f"LocalEmbeddings(model='{stats['model_name']}', "
                f"vectors={stats['vectors_count']}, "
                f"dimension={stats['dimension']})")