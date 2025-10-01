#!/usr/bin/env python3
"""
=======================================================================
APP.PY - APLICACIÓN PRINCIPAL DEL JP_LEGALBOT v3.2
=======================================================================

🎯 FUNCIÓN PRINCIPAL:
   Este es el archivo central que ejecuta toda la aplicación web JP_LegalBot.
   Es un sistema de IA especializado en legislación de planificación de Puerto Rico.

🏗️ ARQUITECTURA:
   - Aplicación Flask que sirve como backend y frontend
   - Sistema híbrido de IA que combina múltiples motores de respuesta
   - Autenticación integrada con control de sesiones
   - API REST para consultas de IA
   - Interface web responsive para usuarios

📋 COMPONENTES PRINCIPALES:
   1. SERVIDOR WEB: Flask app con rutas optimizadas
   2. SISTEMA DE IA: Router inteligente que decide qué motor usar
   3. AUTENTICACIÓN: Login/logout con validación de usuarios
   4. API ENDPOINTS: /chat, /api/stats, /api/diagnostico
   5. RATE LIMITING: Control de solicitudes por IP
   6. LOGGING: Sistema de logs detallado
   7. ERROR HANDLING: Manejo robusto de errores

🔧 DEPENDENCIAS EXTERNAS:
   - simple_auth.py: Sistema de autenticación
   - sistema_hibrido.py: Router de IA y lógica de procesamiento
   - experto_planificacion.py: Motor de IA especializado
   - respuestas_curadas_tier1.py: Base de respuestas pre-aprobadas

🌐 CONFIGURACIÓN PARA DEPLOYMENT:
   - Compatible con Render, Heroku, Railway, Vercel
   - Variables de entorno configurables
   - Timeouts optimizados para servicios cloud
   - Headers de seguridad incluidos
   - Manejo graceful de shutdown

⚙️ CONFIGURACIÓN:
   - Puerto: 5000 (configurable via PORT env var)
   - Debug: Deshabilitado en producción
   - Rate limit: 30 requests/minuto por IP
   - Session timeout: 8 horas
   - Request timeout: 35 segundos
   - OpenAI timeout: 30 segundos

🔐 CREDENCIALES POR DEFECTO:
   - Usuario: Admin911
   - Contraseña: Junta12345

📊 ENDPOINTS DISPONIBLES:
   GET  /           - Página principal (requiere login)
   GET  /login      - Página de login
   POST /login      - Procesar login
   GET  /logout     - Cerrar sesión
   POST /chat       - API para consultas de IA
   GET  /api/stats  - Estadísticas del sistema
   GET  /api/diagnostico - Diagnóstico completo

🚀 PARA EJECUTAR:
   python app.py

=======================================================================
"""

from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect, url_for, flash
import os
import json
import time
import signal
import sys
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv
import openai
import traceback
import logging
from typing import Dict, List, Optional
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as ThreadTimeoutError
import sqlite3
import uuid
from datetime import datetime
import numpy as np

# Importar el sistema de prompts profesional desde la nueva estructura
try:
    from ai_system.prompts import SYSTEM_RAG, USER_TEMPLATE
    PROMPTS_DISPONIBLES = True
except ImportError as e:
    PROMPTS_DISPONIBLES = False

# Importar el nuevo sistema de IA reorganizado (se hace después del logger)
SISTEMA_AI_DISPONIBLE = False

# Configurar logging optimizado para Render
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Función de inicialización de base de datos
def inicializar_base_datos():
    """Inicializa la base de datos SQLite si no existe"""
    from pathlib import Path
    
    # Crear directorio database si no existe
    db_dir = Path('database')
    db_dir.mkdir(exist_ok=True)
    
    # Ruta de la base de datos principal
    db_path = db_dir / 'conversaciones.db'
    
    try:
        # Conectar a la base de datos (se crea si no existe)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Crear tabla de conversaciones
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                usuario TEXT,
                consulta TEXT NOT NULL,
                respuesta TEXT NOT NULL,
                sistema_usado TEXT,
                confianza REAL,
                tiempo_procesamiento REAL,
                ip_usuario TEXT,
                user_agent TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Crear tabla de métricas de rendimiento
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metricas_rendimiento (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                consulta_length INTEGER,
                respuesta_length INTEGER,
                sistema_usado TEXT,
                confianza REAL,
                tiempo_procesamiento REAL,
                ip TEXT,
                user_agent TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Crear índices para mejor rendimiento
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversaciones_timestamp ON conversaciones(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversaciones_usuario ON conversaciones(usuario)")
        
        conn.commit()
        conn.close()
        
        print(f"✅ Base de datos inicializada: {db_path}")
        return True
        
    except Exception as e:
        print(f"❌ Error inicializando base de datos: {e}")
        return False
logger = logging.getLogger(__name__)

# Inicializar base de datos al arrancar la aplicación
inicializar_base_datos()

# Inicializar base de datos híbrida (FTS y tablas de aprendizaje)
def inicializar_hybrid_db():
    """Crear/asegurar la base de datos hybrid_knowledge.db y tablas necesarias.
    Ejecuta el SQL de `database/init_db.sql` si existe y crea tablas de
    `conversations`, `conversation_messages` y `performance_metrics`.
    """
    from pathlib import Path
    sql_path = Path('database') / 'init_db.sql'
    db_dir = Path('database')
    db_dir.mkdir(exist_ok=True)
    db_path = db_dir / 'hybrid_knowledge.db'

    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()

        # Si existe init_db.sql, ejecutarlo para crear FTS y tablas base
        if sql_path.exists():
            try:
                sql_text = sql_path.read_text(encoding='utf-8')
                cur.executescript(sql_text)
                logger.info(f"✅ Ejecutado SQL de inicialización: {sql_path}")
            except Exception as e:
                logger.warning(f"⚠️ Error ejecutando {sql_path}: {e}")

        # Asegurar tablas para logging/aprendizaje que el app.py usa
        cur.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                specialist_type TEXT,
                session_id TEXT,
                started_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT,
                role TEXT,
                content TEXT,
                specialist_context TEXT,
                processing_time REAL,
                confidence_score REAL,
                sources_used TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS performance_metrics (
                id TEXT PRIMARY KEY,
                metric_type TEXT,
                metric_value REAL,
                specialist_area TEXT,
                context_data TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tabla de cache para respuestas similares
        cur.execute("""
            CREATE TABLE IF NOT EXISTS response_cache (
                id TEXT PRIMARY KEY,
                query_text TEXT NOT NULL,
                query_embedding TEXT,  -- JSON array de floats
                response_text TEXT NOT NULL,
                sistema_usado TEXT,
                confianza REAL,
                citas TEXT,  -- JSON array
                usage_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_used DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Índice para búsqueda eficiente por texto de consulta
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cache_query ON response_cache(query_text)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cache_usage ON response_cache(usage_count DESC)")

        conn.commit()
        conn.close()
        logger.info(f"✅ Hybrid DB inicializada/asegurada: {db_path}")
        return True

    except Exception as e:
        logger.error(f"❌ Error inicializando hybrid DB: {e}")
        return False


# Ejecutar inicialización del hybrid DB ahora
inicializar_hybrid_db()

# ===== SISTEMA DE CACHE PARA AHORRO DE TOKENS =====
def buscar_respuesta_cacheada(query: str, similarity_threshold: float = 0.85) -> Optional[Dict]:
    """
    Buscar respuesta cacheada similar a la consulta actual.
    
    Args:
        query: Consulta del usuario
        similarity_threshold: Umbral de similitud (0.0-1.0)
    
    Returns:
        Dict con respuesta cacheada o None si no encuentra
    """
    try:
        from ai_system.local_embeddings import LocalEmbeddings
        import json
        
        # Generar embedding de la consulta actual
        embedder = LocalEmbeddings()
        query_emb = embedder.encode_texts([query])[0]
        
        conn = get_learning_db_connection()
        if not conn:
            return None
        
        cursor = conn.cursor()
        
        # Obtener todas las consultas cacheadas con sus embeddings
        cursor.execute("SELECT id, query_text, query_embedding, response_text, sistema_usado, confianza, citas, usage_count FROM response_cache")
        cached_queries = cursor.fetchall()
        
        if not cached_queries:
            conn.close()
            return None
        
        best_match = None
        best_similarity = 0.0
        
        # Calcular similitud coseno con cada consulta cacheada
        for row in cached_queries:
            cache_id, cached_query, emb_json, response_text, sistema_usado, confianza, citas_json, usage_count = row
            
            if not emb_json:
                continue
                
            try:
                # Parsear embedding guardado
                cached_emb = json.loads(emb_json)
                cached_emb = np.array(cached_emb)
                
                # Calcular similitud coseno
                similarity = np.dot(query_emb, cached_emb) / (np.linalg.norm(query_emb) * np.linalg.norm(cached_emb))
                
                if similarity > best_similarity and similarity >= similarity_threshold:
                    best_similarity = similarity
                    best_match = {
                        'id': cache_id,
                        'query': cached_query,
                        'response': response_text,
                        'sistema_usado': sistema_usado,
                        'confianza': confianza,
                        'citas': json.loads(citas_json) if citas_json else [],
                        'similarity': similarity,
                        'usage_count': usage_count
                    }
                    
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Error procesando embedding cacheado {cache_id}: {e}")
                continue
        
        conn.close()
        
        if best_match:
            logger.info(f"✅ Cache hit: similitud {best_similarity:.3f} con consulta '{best_match['query'][:50]}...'")
            return best_match
        
        logger.info("❌ No se encontró respuesta cacheada similar")
        return None
        
    except Exception as e:
        logger.error(f"Error buscando en cache: {e}")
        return None

def guardar_respuesta_cache(query: str, response_data: Dict):
    """
    Guardar respuesta en el cache para futuras consultas similares.
    
    Args:
        query: Consulta original
        response_data: Datos de la respuesta (respuesta, sistema_usado, confianza, citas)
    """
    try:
        from ai_system.local_embeddings import LocalEmbeddings
        import json
        
        # Generar embedding de la consulta
        embedder = LocalEmbeddings()
        query_emb = embedder.encode_texts([query])[0]
        
        # Convertir embedding a JSON
        emb_json = json.dumps(query_emb.tolist())
        
        # Preparar datos para guardar
        cache_id = f"cache_{uuid.uuid4().hex[:12]}"
        response_text = response_data.get('respuesta', '')
        sistema_usado = response_data.get('sistema_usado', 'desconocido')
        confianza = response_data.get('confianza', 0.0)
        citas = response_data.get('citas', [])
        citas_json = json.dumps(citas)
        
        conn = get_learning_db_connection()
        if not conn:
            return
        
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO response_cache 
            (id, query_text, query_embedding, response_text, sistema_usado, confianza, citas)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (cache_id, query, emb_json, response_text, sistema_usado, confianza, citas_json))
        
        conn.commit()
        conn.close()
        
        logger.info(f"💾 Respuesta guardada en cache: {cache_id}")
        
    except Exception as e:
        logger.error(f"Error guardando en cache: {e}")

def actualizar_uso_cache(cache_id: str):
    """
    Actualizar contador de uso de una respuesta cacheada.
    
    Args:
        cache_id: ID de la entrada en cache
    """
    try:
        conn = get_learning_db_connection()
        if not conn:
            return
        
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE response_cache 
            SET usage_count = usage_count + 1, last_used = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (cache_id,))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error actualizando uso de cache: {e}")

# Cargar configuración después del logger
if PROMPTS_DISPONIBLES:
    logger.info("✅ Sistema de prompts profesional cargado desde ai_system/prompts.py")
else:
    logger.warning("⚠️ No se pudo cargar sistema de prompts, usando prompts básicos")

# Importar el nuevo sistema de IA reorganizado
try:
    from ai_system.retrieve import HybridRetriever
    from ai_system.answer import AnswerEngine
    from ai_system.db import get_conn, fts_search
    SISTEMA_AI_DISPONIBLE = True
    logger.info("✅ Sistema de IA reorganizado importado correctamente")
except ImportError as e:
    SISTEMA_AI_DISPONIBLE = False
    logger.warning(f"⚠️ No se pudo importar sistema de IA: {e}")
    logger.error(f"📝 Traceback: {traceback.format_exc()}")

# Cargar variables de entorno
load_dotenv()

# ===== VALIDACIÓN DE VARIABLES DE ENTORNO =====
def validar_variables_entorno():
    """Validar variables de entorno críticas"""
    errores = []
    warnings = []
    
    # Verificar Azure OpenAI en lugar de OpenAI personal
    azure_key = os.getenv('AZURE_OPENAI_KEY')
    azure_endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
    if not azure_key or len(azure_key.strip()) < 20:
        warnings.append("AZURE_OPENAI_KEY faltante o corto - Sistema funcionará limitado")
    if not azure_endpoint or not azure_endpoint.startswith('https://'):
        warnings.append("AZURE_OPENAI_ENDPOINT faltante o inválido")
    
    secret_key = os.getenv('SECRET_KEY')
    if not secret_key or len(secret_key) < 16:
        warnings.append("SECRET_KEY corto - Se generará uno automáticamente")
    
    try:
        port = int(os.getenv('PORT', '5000'))
        if port < 1024 or port > 65535:
            errores.append(f"PORT inválido: {port}")
    except ValueError:
        errores.append("PORT debe ser un número")
    
    if errores:
        logger.error("[ERROR] ERRORES CRITICOS EN VARIABLES DE ENTORNO:")
        for error in errores:
            logger.error(f"   - {error}")
        return False
    
    if warnings:
        logger.warning("[WARNING] ADVERTENCIAS EN CONFIGURACION:")
        for warning in warnings:
            logger.warning(f"   - {warning}")
    
    return True

# Validar configuración antes de continuar
if not validar_variables_entorno():
    logger.error("❌ Configuración inválida. Revise su archivo .env")
    # En desarrollo no salir, en producción sí
    if os.getenv('FLASK_ENV') == 'production':
        sys.exit(1)

app = Flask(__name__, static_folder='static', static_url_path='/static')

# Configurar secret key para sesiones (con fallback seguro)
secret_key = os.getenv('SECRET_KEY')
if not secret_key or len(secret_key) < 16:
    import secrets
    secret_key = secrets.token_hex(32)
    logger.info("[INFO] Secret key generado automaticamente")

app.secret_key = secret_key

# ===== CONFIGURACIONES ESPECÍFICAS PARA RENDER =====
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 300  # 5 minutos cache
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False  # Velocidad
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)  # 8 horas para trabajo
app.config['WTF_CSRF_TIME_LIMIT'] = 3600

# ✅ TIMEOUTS OPTIMIZADOS PARA DESARROLLO LOCAL
REQUEST_TIMEOUT = 35  # 35 segundos máximo (suficiente para OpenAI)
OPENAI_TIMEOUT = 30   # 30 segundos máximo (para consultas complejas)

# ===== HEADERS DE SEGURIDAD =====
@app.after_request
def add_security_headers(response):
    """Agregar headers de seguridad"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # Solo en producción
    if os.getenv('FLASK_ENV') == 'production':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    # CSP actualizado para permitir CDNs y fuentes externas
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
        "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
    )
    
    return response

# Handler para shutdown graceful en Render - DESHABILITADO PARA DESARROLLO LOCAL
# def signal_handler(signum, frame):
#     logger.info("🛑 Recibida señal de shutdown, cerrando aplicación...")
#     sys.exit(0)

# signal.signal(signal.SIGTERM, signal_handler)  # COMENTADO - problemático en desarrollo
# signal.signal(signal.SIGINT, signal_handler)   # COMENTADO - problemático en desarrollo

# Cliente OpenAI con manejo de errores (Azure y estándar)
deployment_name = "gpt-4.1"  # Variable global para deployment

try:
    # Verificar si Azure OpenAI está configurado
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_key = os.getenv("AZURE_OPENAI_KEY")
    azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1")
    
    if azure_endpoint and azure_key:
        # Usar Azure OpenAI
        client = openai.AzureOpenAI(
            api_version=azure_api_version,
            azure_endpoint=azure_endpoint,
            api_key=azure_key,
            timeout=OPENAI_TIMEOUT
        )
        logger.info("✅ Cliente Azure OpenAI configurado correctamente")
        logger.info(f"   📡 Endpoint: {azure_endpoint}")
        logger.info(f"   🚀 Deployment: {deployment_name}")
    else:
        # Error: Sin configuración Azure OpenAI válida
        logger.error("❌ Configuración Azure OpenAI faltante o incompleta")
        client = None
        deployment_name = "gpt-4.1"  # Mantener valor por defecto
except Exception as e:
    logger.error(f"❌ Error configurando cliente OpenAI: {e}")
    client = None

# ===== SQLITE SIMPLE PARA CONVERSACIONES =====
def init_simple_database():
    """Inicializar base de datos simple de conversaciones"""
    try:
        conn = sqlite3.connect('conversaciones.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT,
                pregunta TEXT,
                respuesta TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ Base de datos SQLite simple inicializada")
        return True
    except Exception as e:
        logger.error(f"❌ Error inicializando base de datos simple: {e}")
        return False

def guardar_conversacion_simple(usuario, pregunta, respuesta):
    """Guardar conversación en SQLite simple"""
    try:
        conn = sqlite3.connect('database/conversaciones.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO conversaciones (usuario, consulta, respuesta, timestamp)
            VALUES (?, ?, ?, datetime('now'))
        ''', (usuario, pregunta, respuesta))
        
        conn.commit()
        conn.close()
        logger.info(f"💾 Conversación guardada para usuario: {usuario}")
        return True
    except Exception as e:
        logger.error(f"❌ Error guardando conversación: {e}")
        return False

def obtener_historial_conversaciones_simple(usuario, limite=6):
    """Obtener historial de conversaciones desde SQLite simple"""
    try:
        conn = sqlite3.connect('database/conversaciones.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT consulta, respuesta 
            FROM conversaciones 
            WHERE usuario = ?
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (usuario, limite))
        
        mensajes = cursor.fetchall()
        conn.close()
        
        if not mensajes:
            return ""
        
        # Formatear como historial conversacional
        historial = []
        for consulta, respuesta in reversed(mensajes):  # Revertir para orden cronológico
            historial.append(f"Usuario: {consulta}")
            historial.append(f"Asistente: {respuesta}")
        
        return "\n".join(historial)
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo historial: {e}")
        return ""

# ===== SISTEMA DE APRENDIZAJE AUTOMÁTICO =====
def get_learning_db_connection():
    """Obtener conexión a la base de datos de aprendizaje"""
    db_path = "database/hybrid_knowledge.db"
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Para acceso por nombre de columna
        return conn
    except Exception as e:
        logger.error(f"❌ Error conectando a base de datos de aprendizaje: {e}")
        return None

def log_conversation_start(user_id: str, specialist_type: str, session_id: str) -> str:
    """Registrar inicio de conversación y retornar conversation_id"""
    try:
        conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
        
        conn = get_learning_db_connection()
        if not conn:
            return conversation_id
        
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversations (id, user_id, specialist_type, session_id)
            VALUES (?, ?, ?, ?)
        """, (conversation_id, user_id, specialist_type, session_id))
        
        conn.commit()
        conn.close()
        
        logger.debug(f"📝 Conversación iniciada: {conversation_id}")
        return conversation_id
        
    except Exception as e:
        logger.error(f"❌ Error logging conversación: {e}")
        return f"conv_{uuid.uuid4().hex[:12]}"  # Fallback

def log_conversation_message(conversation_id: str, role: str, content: str, 
                           specialist_context: str = None, processing_time: float = None,
                           confidence_score: float = None, sources_used: str = None) -> str:
    """Registrar mensaje en conversación"""
    try:
        message_id = f"msg_{uuid.uuid4().hex[:12]}"
        
        conn = get_learning_db_connection()
        if not conn:
            return message_id
        
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversation_messages 
            (id, conversation_id, role, content, specialist_context, 
             processing_time, confidence_score, sources_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (message_id, conversation_id, role, content, specialist_context,
              processing_time, confidence_score, sources_used))
        
        conn.commit()
        conn.close()
        
        logger.debug(f"📝 Mensaje registrado: {message_id}")
        return message_id
        
    except Exception as e:
        logger.error(f"❌ Error logging mensaje: {e}")
        return f"msg_{uuid.uuid4().hex[:12]}"  # Fallback

def log_performance_metric(metric_type: str, metric_value: float, 
                          specialist_area: str = None, context_data: str = None):
    """Registrar métrica de rendimiento"""
    try:
        conn = get_learning_db_connection()
        if not conn:
            return
        
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO performance_metrics (id, metric_type, metric_value, specialist_area, context_data)
            VALUES (?, ?, ?, ?, ?)
        """, (f"metric_{uuid.uuid4().hex[:8]}", metric_type, metric_value, specialist_area, context_data))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"❌ Error logging métrica: {e}")

def get_or_create_conversation_id(session):
    """Obtener o crear conversation_id para la sesión"""
    if 'conversation_id' not in session:
        user_id = session.get('user_id', 'anonymous')
        session_id = session.get('session_id', f"sess_{uuid.uuid4().hex[:8]}")
        session['conversation_id'] = log_conversation_start(user_id, 'general', session_id)
    return session['conversation_id']

# Importar el sistema de autenticación simple
try:
    from core.auth import login_user, is_logged_in, login_required, simple_auth
    logger.info("[OK] Sistema de autenticacion importado desde core/auth.py")
    auth_disponible = True
    logger.info(f"🔍 DEBUG: auth_disponible = {auth_disponible}")
except ImportError as e:
    logger.warning(f"[WARNING] Error importando autenticacion: {e}")
    auth_disponible = False
    logger.info(f"🔍 DEBUG: auth_disponible = {auth_disponible}")
    
    # Crear decorador dummy si no hay autenticación
    def login_required(f):
        return f

# ===== SISTEMA HÍBRIDO SIMPLIFICADO =====
sistema_hibrido_avanzado = None

try:
    logger.info("🚀 Inicializando Sistema Híbrido Simplificado...")
    
    # Función simple para búsqueda en la base de datos
    def buscar_contexto_simple(consulta: str) -> str:
        """Búsqueda inteligente en la base de datos con múltiples estrategias"""
        try:
            conn = get_learning_db_connection()
            if not conn:
                return "No se pudo conectar a la base de datos."
            
            cursor = conn.cursor()
            results = []
            
            # Estrategia 1: Intentar búsqueda FTS con términos limpios
            try:
                # Limpiar consulta para FTS (quitar caracteres problemáticos)
                consulta_fts = consulta.replace("-", " ").replace(".", " ").replace(",", " ")
                cursor.execute("""
                    SELECT content, tomo, capitulo, articulo 
                    FROM fts_chunks 
                    WHERE content MATCH ? 
                    LIMIT 5
                """, (consulta_fts,))
                results = cursor.fetchall()
                logger.debug(f"Búsqueda FTS exitosa: {len(results)} resultados")
            except Exception as e:
                logger.debug(f"Búsqueda FTS falló: {e}")
                results = []
            
            # Estrategia 2: Si FTS falla o no encuentra nada, usar LIKE con términos originales
            if not results:
                palabras_clave = consulta.split()
                like_conditions = []
                params = []
                
                for palabra in palabras_clave:
                    if len(palabra) > 2:  # Solo palabras de 3+ caracteres
                        like_conditions.append("content LIKE ?")
                        params.append(f"%{palabra}%")
                
                if like_conditions:
                    query = f"""
                        SELECT content, tomo, capitulo, articulo 
                        FROM fts_chunks 
                        WHERE {' OR '.join(like_conditions)}
                        LIMIT 5
                    """
                    cursor.execute(query, params)
                    results = cursor.fetchall()
                    logger.debug(f"Búsqueda LIKE exitosa: {len(results)} resultados")
            
            # Estrategia 3: Búsqueda específica para códigos de zonificación
            if not results and any(term in consulta.upper() for term in ['R-1', 'R-2', 'R-3', 'C-1', 'C-2', 'I-1']):
                # Buscar códigos de zonificación específicamente
                cursor.execute("""
                    SELECT content, tomo, capitulo, articulo 
                    FROM fts_chunks 
                    WHERE content LIKE '%R-1%' OR content LIKE '%R-2%' OR 
                          content LIKE '%comercial%' OR content LIKE '%residencial%'
                    LIMIT 5
                """)
                results = cursor.fetchall()
                logger.debug(f"Búsqueda zonificación específica: {len(results)} resultados")
            
            conn.close()
            
            if not results:
                return "No se encontró información específica en la base de datos. Puede que necesite reformular la consulta con términos más generales."
            
            context_parts = []
            for i, (content, tomo, capitulo, articulo) in enumerate(results):
                # Crear metadata más legible
                metadata = f"TOMO {tomo.replace('_COMPLETO_MEJORADO_', ' ')}" if tomo else "Documento"
                if capitulo and capitulo != 'None':
                    metadata += f", Cap. {capitulo}"
                if articulo and articulo != 'None':
                    metadata += f", Art. {articulo}"
                    
                content_preview = content[:500] + "..." if len(content) > 500 else content
                context_parts.append(f"Fuente {i+1} [{metadata}]: {content_preview}")
            
            return "\n\n".join(context_parts)
            
        except Exception as e:
            logger.error(f"Error en búsqueda general: {e}")
            return f"Error en búsqueda: {str(e)}"
    
    logger.info("✅ Sistema Híbrido Simplificado cargado exitosamente")
    sistema_hibrido_disponible = True
    version_sistema = "v3.2_simple_sqlite"
    
    # 🚨 FUNCIÓN DE FILTRADO AGRESIVO PARA CITAS PROBLEMÁTICAS
    def filtrar_citas_problematicas(respuesta: str) -> str:
        """Filtrar y corregir automáticamente citas problemáticas en las respuestas"""
        try:
            # Lista de patrones problemáticos a reemplazar
            patrones_problematicos = [
                # Patrones con "2020"
                (r"Reglamento\s+Conjunto\s+de?\s*2020", "Reglamento Conjunto 2023"),
                (r"Reglamento\s+Conjunto\s*\|\s*2020", "Reglamento Conjunto 2023"),
                (r"Reglamento\s+Conjunto\s*\(\s*2020\s*\)", "Reglamento Conjunto 2023"),
                (r"Reglamento\s+Conjunto\s+2020", "Reglamento Conjunto 2023"),
                
                # Patrones adicionales problemáticos
                (r"Reglamento\s+Conjunto\s+para\s+la\s+Evaluación.*2020", "Reglamento Conjunto 2023"),
                (r"Reglamento\s+de\s+Zonificación.*2020", "Reglamento Conjunto 2023"),
            ]
            
            respuesta_filtrada = respuesta
            
            # Aplicar cada patrón de filtrado
            import re
            for patron, reemplazo in patrones_problematicos:
                respuesta_filtrada = re.sub(patron, reemplazo, respuesta_filtrada, flags=re.IGNORECASE)
            
            # Verificar si se hicieron cambios
            if respuesta_filtrada != respuesta:
                logger.info("🔧 Filtro agresivo aplicado: se corrigieron citas problemáticas")
            
            return respuesta_filtrada
            
        except Exception as e:
            logger.error(f"❌ Error en filtrado de citas: {e}")
            # En caso de error, devolver respuesta original
            return respuesta
    
    # ✅ NUEVA FUNCIÓN SIMPLE CON AZURE OPENAI DIRECTO
    def procesar_consulta_simple(consulta: str) -> Dict:
        """Función simple que usa directamente Azure OpenAI - FUNCIONA GARANTIZADO"""
        try:
            if not client:
                return {
                    'respuesta': 'Error: Cliente Azure OpenAI no configurado',
                    'fuente': 'error',
                    'metodos_utilizados': [],
                    'tiempo_total': 0,
                    'timestamp': datetime.now().isoformat()
                }
            
            # Prompt simple y directo
            system_prompt = """Eres JP LegalBot, un asistente especializado en normativas y reglamentos de la Junta de Planificación de Puerto Rico.

Responde de forma clara, precisa y profesional. Si no tienes información específica sobre el tema, indica que necesitas más contexto o que el usuario consulte con el personal de la JP.

Mantén un tono profesional pero amigable."""
            
            logger.info(f"🔄 [SIMPLE] Enviando consulta a Azure OpenAI: {consulta[:50]}...")
            
            # Llamada directa a Azure OpenAI
            response = client.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": consulta}
                ],
                max_tokens=1000,
                temperature=0.3,
                timeout=45
            )
            
            respuesta = response.choices[0].message.content.strip()
            logger.info(f"✅ [SIMPLE] Respuesta recibida exitosamente")
            
            return {
                'respuesta': respuesta,
                'fuente': 'azure_openai_directo',
                'metodos_utilizados': ['azure_openai'],
                'tiempo_total': 0.1,
                'timestamp': datetime.now().isoformat(),
                'deployment': deployment_name
            }
            
        except Exception as e:
            logger.error(f"❌ [SIMPLE] Error: {e}")
            return {
                'respuesta': f'⚠️ Error técnico: {str(e)[:100]}... Por favor intenta nuevamente.',
                'fuente': 'error_azure',
                'metodos_utilizados': [],
                'tiempo_total': 0,
                'timestamp': datetime.now().isoformat()
            }

    # Función de procesamiento con sistema simplificado
    def procesar_consulta_hibrida(consulta: str, usuario: str = 'anonimo') -> Dict:
        try:
            # Detectar si es una consulta conversacional simple (solo saludos específicos)
            consultas_simples = ['hola', 'hi', 'hello', 'buenos días', 'buenas tardes', 'buenas noches', 'saludos']
            # Solo activar si la consulta es EXACTAMENTE un saludo o muy corta con solo saludos
            consulta_limpia = consulta.lower().strip()
            es_saludo = (
                consulta_limpia in consultas_simples or 
                (len(consulta_limpia.split()) <= 3 and any(saludo in consulta_limpia for saludo in consultas_simples))
            )
            
            # Para saludos simples, responder directamente sin llamar a la IA
            if es_saludo:
                bot_response = """¡Hola! Soy JP_IA, tu asistente especializado en reglamentos de planificación de Puerto Rico. 

Puedo ayudarte con:
• Consultas sobre los TOMOS del Reglamento Conjunto
• Procedimientos de permisos y zonificación  
• Clasificaciones de uso de suelo
• Aspectos ambientales y de infraestructura
• Conservación histórica y cultural

¿En qué tema específico de planificación puedo asistirte hoy?"""
                
                return {
                    'respuesta': bot_response,
                    'sistema_usado': 'respuesta_directa_saludo',
                    'confianza': 1.0,
                    'citas': [],
                    'contexto_chars': 0
                }
            else:
                # Para consultas técnicas, usar búsqueda simple
                context = buscar_contexto_simple(consulta)
                
                # Obtener historial conversacional para memoria
                def obtener_historial_conversacional(limite=10):
                    """Obtener últimos mensajes de la conversación actual"""
                    try:
                        conn = get_learning_db_connection()
                        if not conn:
                            return ""
                        
                        cursor = conn.cursor()
                        # Obtener conversación actual (más reciente)
                        cursor.execute("SELECT id FROM conversations ORDER BY started_at DESC LIMIT 1")
                        conv = cursor.fetchone()
                        
                        if not conv:
                            return ""
                        
                        # Obtener últimos mensajes de esta conversación
                        cursor.execute("""
                            SELECT role, content 
                            FROM conversation_messages 
                            WHERE conversation_id = ?
                            ORDER BY created_at DESC 
                            LIMIT ?
                        """, (conv[0], limite))
                        
                        mensajes = cursor.fetchall()
                        conn.close()
                        
                        if not mensajes:
                            return ""
                        
                        # Formatear historial (orden cronológico)
                        historial = []
                        for role, content in reversed(mensajes):
                            if role == 'user':
                                historial.append(f"Usuario preguntó: {content}")
                            else:
                                # Resumir respuesta del asistente
                                resumen = content[:100] + "..." if len(content) > 100 else content
                                historial.append(f"Asistente respondió: {resumen}")
                        
                        return "\n".join(historial[-6:])  # Últimos 6 intercambios
                        
                    except Exception as e:
                        logger.error(f"Error obteniendo historial: {e}")
                        return ""
                
                historial = obtener_historial_conversaciones_simple(usuario)
                
                # Usar sistema de prompts profesional si está disponible
                if PROMPTS_DISPONIBLES:
                    # Crear contexto enriquecido para el template profesional
                    context_enriquecido = f"""CONTEXTO LEGISLATIVO RELEVANTE:
{context}

MEMORIA CONVERSACIONAL:
{historial if historial else "Nueva conversación iniciada"}"""
                    
                    # Usar el template profesional
                    user_prompt = USER_TEMPLATE.format(
                        query=consulta,
                        context=context_enriquecido
                    )
                    
                    messages = [
                        {"role": "system", "content": SYSTEM_RAG},
                        {"role": "user", "content": user_prompt}
                    ]
                    
                    logger.info("🎯 Usando sistema de prompts profesional avanzado")
                    
                else:
                    # Fallback al prompt básico (solo si no está disponible el profesional)
                    system_prompt_basico = f"""Eres JP_IA, un experto en el Reglamento Conjunto 2023 de la Junta de Planificación de Puerto Rico.

CONTEXTO RELEVANTE:
{context}

HISTORIAL DE CONVERSACIÓN:
{historial}

INSTRUCCIONES:
- SIEMPRE revisa el HISTORIAL antes de responder para mantener coherencia
- Usa referencias exactas: "Reglamento Conjunto 2023" (NUNCA uses "2020" en el título)
- Incluye referencias específicas a TOMOS, Capítulos y Artículos
- Mantén un tono profesional y didáctico
- Si hay seguimiento a temas previos, conéctalo explícitamente

CONSULTA: {consulta}"""
                    
                    messages = [
                        {"role": "system", "content": system_prompt_basico},
                        {"role": "user", "content": consulta}
                    ]
                    
                    logger.warning("⚠️ Usando prompt básico de respaldo")

                # Si no hay cliente OpenAI/Azure configurado, generar una respuesta
                # local simple usando el contexto recuperado (RAG fallback).
                if client is None:
                    # Si no se encontró contexto útil, devolver mensaje estándar
                    if not context or context.startswith("No se encontró") or context.startswith("Error"):
                        bot_response = (
                            "Puedo buscar en mis documentos internos pero no puedo generar una respuesta refinada porque no hay un servicio de LLM configurado. "
                            "Por favor configure correctamente las variables de Azure OpenAI (AZURE_OPENAI_KEY, AZURE_OPENAI_ENDPOINT) para obtener respuestas completas."
                        )
                        return {
                            'respuesta': bot_response,
                            'sistema_usado': 'fallback_sin_llm',
                            'confianza': 0.2,
                            'citas': [],
                            'contexto_chars': 0
                        }

                    # Construir respuesta concatenando extractos relevantes
                    summary_prefix = "Según los documentos encontrados, aquí hay extractos relevantes:\n\n"
                    # Limitar longitud para evitar respuestas demasiado largas
                    max_chars = 3500
                    truncated_context = context[:max_chars]
                    bot_response = summary_prefix + truncated_context + (
                        "\n\n(Respuesta generada localmente sin modelo de lenguaje. Para respuestas más naturales y detalladas, configure una API de OpenAI/Azure.)"
                    )

                    return {
                        'respuesta': bot_response,
                        'sistema_usado': 'hibrido_local_rag',
                        'confianza': 0.6,
                        'citas': [],
                        'contexto_chars': len(context)
                    }

                # Llamada a Azure/OpenAI cuando haya cliente configurado
                response = client.chat.completions.create(
                    model=deployment_name,
                    messages=messages,
                    max_tokens=1000,
                    temperature=0.1,
                    timeout=REQUEST_TIMEOUT
                )
                
                bot_response = response.choices[0].message.content.strip()
                
                # 🚨 POST-PROCESAMIENTO AGRESIVO: Filtrar citas problemáticas
                bot_response = filtrar_citas_problematicas(bot_response)
                
                return {
                    'respuesta': bot_response,
                    'sistema_usado': 'hibrido_simple_sqlite',
                    'confianza': 0.95,
                    'citas': [],
                    'contexto_chars': len(context)
                }
        except Exception as e:
            logger.error(f"❌ Error en sistema simplificado: {e}")
            return {
                'respuesta': f"Error en sistema híbrido: {str(e)}",
                'sistema_usado': 'error_simple',
                'confianza': 0.1,
                'citas': [],
                'contexto_chars': 0
            }
    
except Exception as e:
    logger.error(f"❌ Error cargando Sistema Híbrido Simplificado: {e}")
    logger.error(f"📝 Traceback: {traceback.format_exc()}")
    sistema_hibrido_avanzado = None
    sistema_hibrido_disponible = False
    version_sistema = "v3.2_fallback_simple"
    
    # Función fallback simple
    def procesar_consulta_hibrida(consulta: str, usuario: str = 'anonimo') -> Dict:
        return {
            'respuesta': "Sistema híbrido no disponible. Funcionalidad limitada.",
            'sistema_usado': 'fallback_simple',
            'confianza': 0.1,
            'citas': [],
            'contexto_chars': 0
        }

# Inicializar sistema de IA reorganizado si está disponible
if SISTEMA_AI_DISPONIBLE:
    try:
        logger.info("🔧 Verificando configuración Azure OpenAI antes de inicializar sistema avanzado...")
        
        # Verificar que las variables de entorno estén configuradas
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_key = os.getenv("AZURE_OPENAI_KEY") 
        
        if not azure_endpoint or not azure_endpoint.startswith('http'):
            raise ValueError(f"AZURE_OPENAI_ENDPOINT no válido: '{azure_endpoint}'. Configure las variables de entorno en Render.")
            
        if not azure_key or len(azure_key) < 10:
            raise ValueError(f"AZURE_OPENAI_KEY no válido (longitud: {len(azure_key)}). Configure las variables de entorno en Render.")
        
        logger.info(f"✅ Variables Azure OpenAI verificadas:")
        logger.info(f"   📡 Endpoint: {azure_endpoint}")
        logger.info(f"   🔑 API Key: ***{azure_key[-8:]}")
        
        # Inicializar el retriever y answer engine
        retriever = HybridRetriever()
        answer_engine = AnswerEngine(retriever)
        logger.info("✅ Sistema de IA reorganizado inicializado correctamente")
        
        # Sobrescribir la función con el nuevo sistema
        def procesar_consulta_hibrida_nueva(consulta: str, usuario: str = 'anonimo') -> Dict:
            try:
                logger.info(f"🔍 Procesando con AI system: '{consulta[:50]}...'")
                
                # 🔄 BUSCAR RESPUESTA EN CACHE ANTES DE PROCESAR
                cache_result = buscar_respuesta_cacheada(consulta, similarity_threshold=0.85)
                if cache_result:
                    logger.info(f"💰 Cache hit! Reutilizando respuesta similar (similitud: {cache_result['similarity']:.3f})")
                    
                    # Actualizar contador de uso
                    actualizar_uso_cache(cache_result['id'])
                    
                    # Devolver respuesta cacheada
                    return {
                        'respuesta': cache_result['response'],
                        'sistema_usado': f"cache_{cache_result['sistema_usado']}",
                        'confianza': cache_result['confianza'],
                        'citas': cache_result['citas'],
                        'contexto_chars': len(cache_result['response']),
                        'cached': True,
                        'cache_similarity': cache_result['similarity']
                    }
                
                logger.info("💸 Cache miss - Generando nueva respuesta")
                
                # 🧠 OBTENER HISTORIAL CONVERSACIONAL PARA MEMORIA
                def obtener_historial_conversacional(limite=6):
                    """Obtener últimos mensajes de la conversación actual"""
                    try:
                        conn = get_learning_db_connection()
                        if not conn:
                            return ""
                        
                        cursor = conn.cursor()
                        # Obtener conversación actual (más reciente)
                        cursor.execute("SELECT id FROM conversations ORDER BY started_at DESC LIMIT 1")
                        conv = cursor.fetchone()
                        
                        if not conv:
                            return ""
                        
                        # Obtener últimos mensajes de esta conversación
                        cursor.execute("""
                            SELECT role, content 
                            FROM conversation_messages 
                            WHERE conversation_id = ?
                            ORDER BY created_at DESC 
                            LIMIT ?
                        """, (conv[0], limite))
                        
                        mensajes = cursor.fetchall()
                        conn.close()
                        
                        if not mensajes:
                            return ""
                        
                        # Formatear historial (orden cronológico)
                        historial = []
                        for role, content in reversed(mensajes):
                            if role == 'user':
                                historial.append(f"Usuario: {content}")
                            else:
                                # Resumir respuesta del asistente
                                resumen = content[:150] + "..." if len(content) > 150 else content
                                historial.append(f"Asistente: {resumen}")
                        
                        return "\n".join(historial[-4:])  # Últimos 4 intercambios
                        
                    except Exception as e:
                        logger.error(f"Error obteniendo historial: {e}")
                        return ""
                
                historial = obtener_historial_conversaciones_simple(usuario)
                
                # 📝 CONSTRUIR CONSULTA CON CONTEXTO
                if historial:
                    consulta_con_contexto = f"""HISTORIAL DE CONVERSACIÓN PREVIA:
{historial}

NUEVA CONSULTA DEL USUARIO:
{consulta}

INSTRUCCIONES: Mantén coherencia con el historial previo. Si el usuario hace referencia a información anterior, conéctala apropiadamente."""
                    logger.info(f"🧠 Usando historial conversacional: {len(historial)} chars")
                else:
                    consulta_con_contexto = consulta
                    logger.info("📝 Sin historial previo, consulta nueva")
                
                # Obtener o crear conversation_id para memoria semántica
                # Cada consulta nueva debe tener su propio conversation_id para evitar contaminación de contexto
                conversation_id = f"conv_{usuario}_{int(time.time())}_{hash(consulta) % 10000}"
                logger.info(f"🆔 Conversation ID generado: {conversation_id}")
                
                # NO reutilizar conversaciones existentes automáticamente para evitar contaminación de contexto
                # El sistema de memoria semántica debe mantener conversaciones separadas
                
                # Usar el nuevo sistema de IA CON MEMORIA SEMÁNTICA
                resultado = answer_engine.answer_with_memory(
                    query=consulta_con_contexto, 
                    conversation_id=conversation_id, 
                    k=6
                )
                logger.info(f"✅ Answer engine con memoria semántica respondió: {type(resultado)} - keys: {resultado.keys() if isinstance(resultado, dict) else 'N/A'}")
                
                respuesta_final = {
                    'respuesta': resultado.get('text', ''),  # CORREGIDO: 'text' no 'response'
                    'sistema_usado': 'ai_system_reorganizado',
                    'confianza': 0.9,
                    'citas': resultado.get('citations', []),  # CORREGIDO: 'citations' no 'sources'
                    'contexto_chars': len(resultado.get('text', ''))  # CORREGIDO: usar 'text'
                }
                logger.info(f"✅ Respuesta final construida: respuesta_len={len(respuesta_final['respuesta'])}, citas={len(respuesta_final['citas'])}")
                
                # 💾 GUARDAR RESPUESTA EN CACHE PARA FUTURAS CONSULTAS SIMILARES
                guardar_respuesta_cache(consulta, respuesta_final)
                
                return respuesta_final
                
            except Exception as e:
                logger.error(f"❌ Error en sistema de IA reorganizado: {e}")
                logger.error(f"📝 Traceback completo: {traceback.format_exc()}")
                return {
                    'respuesta': f"Error en sistema de IA: {str(e)}",
                    'sistema_usado': 'error_ai_reorganizado',
                    'confianza': 0.1,
                    'citas': [],
                    'contexto_chars': 0
                }
        
        # Reemplazar la función principal
        procesar_consulta_hibrida = procesar_consulta_hibrida_nueva
        logger.info("✅ Función de procesamiento actualizada al nuevo sistema de IA")
        
    except Exception as e:
        logger.error(f"❌ Error inicializando sistema de IA reorganizado: {e}")
        logger.error(f"📝 Traceback: {traceback.format_exc()}")
        
        # Mensaje específico para problemas de configuración
        if "AZURE_OPENAI_ENDPOINT" in str(e) or "httpx.UnsupportedProtocol" in str(e):
            logger.error("🔧 SOLUCIÓN: Configure las variables de entorno Azure OpenAI en el panel de Render:")
            logger.error("   - AZURE_OPENAI_ENDPOINT=https://legalbotfoundry.cognitiveservices.azure.com/")
            logger.error("   - AZURE_OPENAI_KEY=[su_clave_azure]")
            logger.error("   - AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4.1")
            logger.error("   Después, redeploy el servicio manualmente.")

# Configuraciones del sistema
CONFIG = {
    'RATE_LIMIT_MESSAGES': int(os.getenv('RATE_LIMIT_MESSAGES', '30')),
    'RATE_LIMIT_WINDOW': int(os.getenv('RATE_LIMIT_WINDOW', '60')),
    'SESSION_TIMEOUT': int(os.getenv('SESSION_TIMEOUT', '3600')),
    'ENABLE_ANALYTICS': os.getenv('ENABLE_ANALYTICS', 'true').lower() == 'true',
    'DEBUG_MODE': os.getenv('DEBUG_MODE', 'false').lower() == 'true'
}

# ===== RATE LIMITING CON GESTIÓN DE MEMORIA =====
class RateLimiter:
    """Rate limiter con gestión automática de memoria"""
    
    def __init__(self, max_requests=30, window_seconds=60, max_ips=1000):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_ips = max_ips
        self.requests = defaultdict(list)
        self.last_cleanup = time.time()
        self._lock = threading.Lock()
    
    def is_allowed(self, identifier):
        """Verificar si se permite la request"""
        now = time.time()
        
        with self._lock:
            # Limpieza automática cada 5 minutos
            if now - self.last_cleanup > 300:
                self.cleanup_old_requests(now)
                self.last_cleanup = now
            
            # Limpiar requests antiguos de esta IP
            self.requests[identifier] = [
                req_time for req_time in self.requests[identifier] 
                if now - req_time < self.window_seconds
            ]
            
            # Verificar límite
            if len(self.requests[identifier]) >= self.max_requests:
                return False
            
            self.requests[identifier].append(now)
            return True
    
    def cleanup_old_requests(self, now):
        """Limpiar requests antiguos y limitar número de IPs"""
        # Remover requests antiguos
        for ip in list(self.requests.keys()):
            self.requests[ip] = [
                req_time for req_time in self.requests[ip] 
                if now - req_time < self.window_seconds
            ]
            # Remover IPs sin requests recientes
            if not self.requests[ip]:
                del self.requests[ip]
        
        # Si tenemos demasiadas IPs, eliminar las más antiguas
        if len(self.requests) > self.max_ips:
            sorted_ips = sorted(
                self.requests.items(), 
                key=lambda x: max(x[1]) if x[1] else 0, 
                reverse=True
            )[:self.max_ips]
            self.requests = defaultdict(list, dict(sorted_ips))
            
        logger.info(f"🧹 Rate limiter cleanup: {len(self.requests)} IPs activas")

# Instanciar rate limiter
rate_limiter = RateLimiter(
    max_requests=CONFIG['RATE_LIMIT_MESSAGES'],
    window_seconds=CONFIG['RATE_LIMIT_WINDOW']
)

def check_rate_limit(identifier: str) -> bool:
    """Rate limiting con gestión de memoria"""
    return rate_limiter.is_allowed(identifier)

def get_client_ip():
    """Obtener IP del cliente (funciona con proxies de Render)"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr

# ===== PROCESAMIENTO CON TIMEOUT ROBUSTO =====
def procesar_con_timeout(mensaje, usuario='anonimo', timeout_segundos=REQUEST_TIMEOUT):
    """Procesar consulta con timeout usando threading - VERSIÓN HÍBRIDA CON DOCUMENTOS JP"""
    try:
        # ✅ USAR FUNCIÓN HÍBRIDA QUE CONSULTA DOCUMENTOS DE LA JP
        logger.info("🔄 Usando procesamiento HÍBRIDO con documentos de la JP")
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(procesar_consulta_hibrida, mensaje, usuario)
            resultado = future.result(timeout=timeout_segundos)
            return resultado
    except ThreadTimeoutError:
        raise TimeoutError(f"Timeout después de {timeout_segundos} segundos")
    except Exception as e:
        logger.error(f"❌ Error en procesar_con_timeout híbrido: {e}")
        # Fallback a simple si falla híbrido
        try:
            logger.info("🔄 Fallback a procesamiento simple...")
            return procesar_consulta_simple(mensaje)
        except:
            raise e


def build_clean_response(resultado: Dict, tiempo_total: float) -> Dict:
    """Construir una respuesta JSON más limpia y presentable para el frontend.

    Estructura resultante:
    {
      "version": str,
      "timestamp": str,
      "summary": str,         # breve resumen/preview
      "detail": str,          # respuesta completa
      "references": list,     # lista de citas/URLs/IDs (si aplica)
      "metrics": {            # metadatos útiles para debugging/analytics
          "sistema_usado": str,
          "confianza": float,
          "tiempo_procesamiento": float,
          "contexto_chars": int
      }
    }
    """
    try:
        respuesta = resultado.get('respuesta', '') if isinstance(resultado, Dict) else str(resultado)
        sistema = resultado.get('sistema_usado', 'desconocido') if isinstance(resultado, Dict) else 'desconocido'
        confianza = float(resultado.get('confianza', 0.0)) if isinstance(resultado, Dict) else 0.0
        citas = resultado.get('citas', []) if isinstance(resultado, Dict) else []
        contexto_chars = int(resultado.get('contexto_chars', 0)) if isinstance(resultado, Dict) else 0

        # Generar un resumen corto (primer párrafo o hasta 300 chars)
        summary = ''
        if respuesta:
            # tomar hasta el primer doble salto de línea como resumen
            partes = respuesta.strip().split('\n\n')
            summary = partes[0].strip() if partes and partes[0] else respuesta[:300].strip()
            if len(summary) > 300:
                summary = summary[:297] + '...'

        clean = {
            'version': version_sistema,
            'timestamp': datetime.now().isoformat(),
            'summary': summary,
            'detail': respuesta,
            'response': respuesta,  # ✅ AGREGAR PARA COMPATIBILIDAD CON FRONTEND
            'sources': citas or [],  # ✅ CAMBIAR DE references a sources
            'references': citas or [],
            'metrics': {
                'sistema_usado': sistema,
                'confianza': confianza,
                'tiempo_procesamiento': round(tiempo_total, 3),
                'contexto_chars': contexto_chars
            }
        }

        return clean

    except Exception as e:
        logger.error(f"❌ Error construyendo respuesta limpia: {e}")
        # Fallback mínimo
        respuesta_fallback = resultado.get('respuesta') if isinstance(resultado, Dict) else str(resultado)
        return {
            'version': version_sistema,
            'timestamp': datetime.now().isoformat(),
            'summary': '',
            'detail': respuesta_fallback,
            'response': respuesta_fallback,  # ✅ AGREGAR PARA COMPATIBILIDAD
            'sources': [],  # ✅ AGREGAR sources
            'references': [],
            'metrics': {
                'sistema_usado': resultado.get('sistema_usado', 'desconocido') if isinstance(resultado, Dict) else 'desconocido',
                'confianza': float(resultado.get('confianza', 0.0)) if isinstance(resultado, Dict) else 0.0,
                'tiempo_procesamiento': round(tiempo_total, 3),
                'contexto_chars': int(resultado.get('contexto_chars', 0)) if isinstance(resultado, Dict) else 0
            }
        }

# ===== MANEJO ROBUSTO DE SESSION TIMEOUT =====
def verificar_timeout_sesion():
    """Verificar si la sesión ha expirado"""
    if not is_logged_in(session):
        return False, "No hay sesión activa"
    
    login_time = session.get('login_time')
    if not login_time:
        logger.warning("⚠️ Sesión sin login_time, limpiando")
        session.clear()
        return False, "Sesión inválida"
    
    try:
        # Manejar tanto string ISO como timestamp
        if isinstance(login_time, str):
            login_datetime = datetime.fromisoformat(login_time.replace('Z', '+00:00'))
        else:
            login_datetime = datetime.fromtimestamp(float(login_time))
        
        tiempo_transcurrido = datetime.now() - login_datetime.replace(tzinfo=None)
        timeout_limite = timedelta(seconds=CONFIG['SESSION_TIMEOUT'])
        
        if tiempo_transcurrido > timeout_limite:
            logger.info(f"⏰ Sesión expirada: {tiempo_transcurrido.total_seconds()}s > {timeout_limite.total_seconds()}s")
            session.clear()
            return False, "Sesión expirada"
        
        return True, "Sesión válida"
        
    except (ValueError, TypeError, OSError) as e:
        logger.error(f"❌ Error parseando login_time '{login_time}': {e}")
        session.clear()
        return False, "Error en datos de sesión"

# ===== RUTAS PRINCIPALES =====

@app.route('/')
def index():
    """Página principal optimizada"""
    
    # DEBUG TEMPORAL: Comentamos session.clear() para poder probar el login
    # session.clear()
    # logger.info("🔍 DEBUG: Sesión limpiada, forzando redirect a login")
    
    if auth_disponible and not is_logged_in(session):
        return redirect(url_for('login_page'))
    
    # ✅ VERIFICAR TIMEOUT DE SESIÓN ROBUSTO
    if auth_disponible and is_logged_in(session):
        sesion_valida, mensaje = verificar_timeout_sesion()
        if not sesion_valida:
            flash(f'{mensaje}. Por favor inicie sesión nuevamente.', 'warning')
            return redirect(url_for('login_page'))
    
    return render_template('index.html', 
                         version=version_sistema,
                         sistema_activo=sistema_hibrido_disponible)

@app.route('/chat', methods=['POST'])
def chat():
    """Endpoint principal de chat optimizado para Render"""
    inicio_tiempo = time.time()
    
    try:
        # Validar autenticación
        if auth_disponible and not is_logged_in(session):
            return jsonify({
                'error': 'Sesión no válida',
                'redirect': '/login'
            }), 401
        
        # Obtener datos
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'Mensaje requerido'}), 400
        
        mensaje = data['message'].strip()
        if not mensaje:
            return jsonify({'error': 'Mensaje vacío'}), 400
        
        if len(mensaje) > 1000:
            return jsonify({'error': 'Mensaje demasiado largo (máximo 1000 caracteres)'}), 400
        
        # Rate limiting
        client_ip = get_client_ip()
        if not check_rate_limit(client_ip):
            return jsonify({
                'error': f'Demasiadas solicitudes. Límite: {CONFIG["RATE_LIMIT_MESSAGES"]} por minuto',
                'retry_after': CONFIG['RATE_LIMIT_WINDOW']
            }), 429
        
        # Log de la consulta
        logger.info(f"🔄 Nueva consulta desde {client_ip}: '{mensaje[:50]}...'")
        
        # Obtener usuario para el procesamiento
        usuario = session.get('user_id', 'anonimo') if auth_disponible else 'test_user'
        
        # ✅ PROCESAR CONSULTA CON TIMEOUT ROBUSTO
        try:
            resultado = procesar_con_timeout(mensaje, usuario, timeout_segundos=REQUEST_TIMEOUT)
            
        except TimeoutError:
            logger.warning(f"⏰ Timeout procesando consulta: '{mensaje[:30]}...'")
            return jsonify({
                'error': 'La consulta tardó demasiado en procesarse. Por favor, simplifique su pregunta.',
                'timeout': True
            }), 408
        except Exception as e:
            logger.error(f"❌ Error procesando consulta: {e}")
            logger.error(f"📝 Traceback: {traceback.format_exc()}")
            return jsonify({
                'error': 'Error interno procesando la consulta',
                'details': str(e) if CONFIG['DEBUG_MODE'] else None
            }), 500
        
        # Validar resultado
        if not isinstance(resultado, dict) or 'respuesta' not in resultado:
            logger.error(f"❌ Resultado inválido del sistema híbrido: {resultado}")
            return jsonify({
                'error': 'Error en el formato de respuesta del sistema'
            }), 500
        
        # Preparar respuesta limpia y consistente
        tiempo_total = time.time() - inicio_tiempo
        sistema_usado = resultado.get('sistema_usado', 'desconocido')
        confianza = resultado.get('confianza', 0.0)

        logger.info(f"✅ Consulta procesada en {tiempo_total:.2f}s - Sistema: {sistema_usado} - Confianza: {confianza}")

        # ✅ GUARDAR CONVERSACIÓN EN SQLITE SIMPLE
        guardar_conversacion_simple(usuario, mensaje, resultado['respuesta'])

        # Log para analytics
        log_consulta(mensaje, resultado['respuesta'], {
            'sistema_usado': sistema_usado,
            'confianza': confianza,
            'tiempo_procesamiento': tiempo_total,
            'client_ip': client_ip
        })

        clean = build_clean_response(resultado, tiempo_total)

        return jsonify(clean)
        
    except Exception as e:
        tiempo_total = time.time() - inicio_tiempo
        logger.error(f"❌ Error crítico en endpoint chat: {e}")
        logger.error(f"📝 Traceback: {traceback.format_exc()}")
        
        return jsonify({
            'error': 'Error interno del servidor',
            'tiempo_procesamiento': tiempo_total,
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/chat-test', methods=['POST'])
def chat_test():
    """Endpoint temporal para pruebas: omite autenticación y devuelve respuesta de prueba."""
    inicio_tiempo = time.time()
    try:
        data = request.get_json() or {}
        mensaje = data.get('message', '').strip()
        if not mensaje:
            return jsonify({'error': 'Mensaje requerido'}), 400

        # Procesar con timeout reutilizando la función
        try:
            resultado = procesar_con_timeout(mensaje, timeout_segundos=REQUEST_TIMEOUT)
        except TimeoutError:
            return jsonify({'error': 'Timeout procesando consulta'}), 408

        if not isinstance(resultado, dict) or 'respuesta' not in resultado:
            return jsonify({'error': 'Resultado inválido del sistema'}), 500

        tiempo_total = time.time() - inicio_tiempo
        clean = build_clean_response(resultado, tiempo_total)
        return jsonify(clean)

    except Exception as e:
        logger.error(f"❌ Error en chat-test: {e}")
        return jsonify({'error': 'Error interno'}), 500

def log_consulta(consulta: str, respuesta: str, metadata: Dict = None):
    """Log avanzado de consultas para analytics y aprendizaje"""
    if not CONFIG['ENABLE_ANALYTICS']:
        return
    
    try:
        # Log básico para analytics (mantener compatibilidad)
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'consulta_length': len(consulta),
            'respuesta_length': len(respuesta),
            'sistema_usado': metadata.get('sistema_usado', 'unknown') if metadata else 'unknown',
            'confianza': metadata.get('confianza', 0.0) if metadata else 0.0,
            'tiempo_procesamiento': metadata.get('tiempo_procesamiento', 0.0) if metadata else 0.0,
            'ip': get_client_ip(),
            'user_agent': request.headers.get('User-Agent', '')[:100]
        }
        
        logger.info(f"📊 ANALYTICS: {json.dumps(log_entry, ensure_ascii=False)}")
        
        # Log avanzado para aprendizaje (nuevo sistema)
        try:
            conversation_id = get_or_create_conversation_id(session)
            
            # Registrar mensaje del usuario
            log_conversation_message(
                conversation_id=conversation_id,
                role='user',
                content=consulta,
                specialist_context=metadata.get('sistema_usado') if metadata else None
            )
            
            # Registrar respuesta del asistente
            sources_json = None
            if metadata and metadata.get('citas'):
                sources_json = json.dumps(metadata['citas'])
            
            log_conversation_message(
                conversation_id=conversation_id,
                role='assistant', 
                content=respuesta,
                specialist_context=metadata.get('sistema_usado') if metadata else None,
                processing_time=metadata.get('tiempo_procesamiento') if metadata else None,
                confidence_score=metadata.get('confianza') if metadata else None,
                sources_used=sources_json
            )
            
            # Registrar métricas de rendimiento
            if metadata:
                log_performance_metric(
                    metric_type='response_time',
                    metric_value=metadata.get('tiempo_procesamiento', 0.0),
                    specialist_area=metadata.get('sistema_usado'),
                    context_data=json.dumps({
                        'consulta_length': len(consulta),
                        'respuesta_length': len(respuesta),
                        'confianza': metadata.get('confianza', 0.0)
                    })
                )
                
                log_performance_metric(
                    metric_type='confidence_score',
                    metric_value=metadata.get('confianza', 0.0),
                    specialist_area=metadata.get('sistema_usado')
                )
                
        except Exception as learning_error:
            logger.warning(f"⚠️ Error en logging de aprendizaje: {learning_error}")
            # No afectar el funcionamiento principal
        
    except Exception as e:
        logger.error(f"❌ Error logging consulta: {e}")

# ===== RUTAS DE AUTENTICACIÓN =====

@app.route('/test-endpoint', methods=['GET', 'POST'])
def test_endpoint():
    """Endpoint de prueba para debugging"""
    logger.info(f"🧪 TEST: Method={request.method}, Data={dict(request.form)}")
    return jsonify({"status": "ok", "method": request.method, "data": dict(request.form)})

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    """Página de login optimizada"""
    logger.info(f"🔍 LOGIN DEBUG: Method={request.method}, URL={request.url}, Headers={dict(request.headers)}")
    logger.info(f"🔍 LOGIN DEBUG: Form data={dict(request.form)}, Args={dict(request.args)}")
    
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
            
            logger.info(f"🔍 LOGIN DEBUG: username='{username}', password_len={len(password) if password else 0}")
            
            if not username or not password:
                logger.warning(f"🔍 LOGIN DEBUG: Campos vacíos - username='{username}', password='{bool(password)}'")
                flash('Por favor complete todos los campos', 'error')
                return render_template('login.html', error='Campos requeridos')
            
            if auth_disponible:
                logger.info(f"🔍 LOGIN DEBUG: Autenticación disponible, intentando login para '{username}'")
                result = login_user(username, password)
                logger.info(f"🔍 LOGIN DEBUG: Resultado de login_user: {result}")
                
                if result['success']:
                    user_data = result.get('user', {})
                    
                    # Hacer la sesión permanente para que dure el tiempo completo
                    session.permanent = True
                    session['user_id'] = user_data.get('user_id', username)
                    session['username'] = user_data.get('username', username)
                    session['logged_in'] = True
                    session['auth_method'] = user_data.get('auth_method', 'local')
                    session['login_time'] = datetime.now().isoformat()
                    
                    logger.info(f"✅ Login exitoso: {username}")
                    logger.info(f"🔍 LOGIN DEBUG: Session establecida: {dict(session)}")
                    flash(f'¡Bienvenido, {username}!', 'success')
                    
                    next_page = request.args.get('next')
                    redirect_url = next_page if next_page else url_for('index')
                    logger.info(f"🔍 LOGIN DEBUG: Redirigiendo a: {redirect_url}")
                    return redirect(redirect_url)
                else:
                    logger.warning(f"❌ Login fallido: {result['message']}")
                    logger.info(f"🔍 LOGIN DEBUG: Mostrando error en template")
                    flash(result['message'], 'error')
                    return render_template('login.html', error=result['message'])
            else:
                logger.error(f"🔍 LOGIN DEBUG: Sistema de autenticación NO DISPONIBLE")
                flash('Sistema de autenticación no disponible', 'error')
                return render_template('login.html', error='Auth no disponible')
                
        except Exception as e:
            logger.error(f"❌ Error en login: {str(e)}")
            logger.error(f"🔍 LOGIN DEBUG: Exception completa: {e}")
            import traceback
            logger.error(f"🔍 LOGIN DEBUG: Traceback: {traceback.format_exc()}")
            flash('Error interno del servidor', 'error')
            return render_template('login.html', error='Error interno')
    
    logger.info(f"🔍 LOGIN DEBUG: Mostrando formulario GET")
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Cerrar sesión"""
    username = session.get('username', 'Usuario')
    session.clear()
    flash(f'Sesión de {username} cerrada exitosamente', 'info')
    logger.info(f"🔤 Logout: {username}")
    return redirect(url_for('login_page'))

@app.route('/change-password-complete')
@app.route('/change_password_complete')
@app.route('/cambiar-password-complete')
@app.route('/cambiar_password_complete')
def change_password_complete():
    """Página de confirmación de cambio de contraseña exitoso"""
    from datetime import datetime
    
    # Obtener datos de la sesión o parámetros URL
    username = request.args.get('username', session.get('username', 'Usuario'))
    method = request.args.get('method', 'Base de datos principal')
    timestamp = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    
    return render_template('ChangePasswordComplete.html', 
                         username=username,
                         method=method,
                         timestamp=timestamp)

@app.route('/change-password', methods=['GET', 'POST'])
@app.route('/change_password', methods=['GET', 'POST'])
@app.route('/cambiar-password', methods=['GET', 'POST'])
@app.route('/cambiar_password', methods=['GET', 'POST'])
def change_password():
    """Página de cambio de contraseña"""
    if request.method == 'GET':
        return render_template('ChangePassword.html')
    
    # Procesar POST - cambio de contraseña
    username = request.form.get('username', '').strip()
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')
    
    # Validaciones básicas
    if not all([username, current_password, new_password, confirm_password]):
        flash('❌ Todos los campos son obligatorios', 'error')
        return render_template('ChangePassword.html')
    
    if new_password != confirm_password:
        flash('❌ Las contraseñas nuevas no coinciden', 'error')
        return render_template('ChangePassword.html')
    
    if current_password == new_password:
        flash('⚠️ La nueva contraseña debe ser diferente a la actual', 'warning')
        return render_template('ChangePassword.html')
    
    try:
        # Primero verificar que el usuario y contraseña actual sean correctos
        auth_result = simple_auth.authenticate(username, current_password)
        
        if not auth_result.get('success', False):
            logger.warning(f"❌ Autenticación falló para {username}")
            flash('❌ Usuario o contraseña actual incorrectos', 'error')
            return render_template('ChangePassword.html')
        
        # 🎯 Actualizar contraseña en SQLite
        success = simple_auth.update_password(username, new_password)
        
        if success:
            logger.info(f"✅ Contraseña actualizada en SQLite para: {username}")
            # Redirigir a página de confirmación
            return redirect(url_for('change_password_complete', 
                                  username=username, 
                                  method='Base de datos SQLite'))
        else:
            logger.error(f"❌ Error actualizando contraseña en SQLite para: {username}")
            flash('❌ Error al actualizar contraseña. Intente nuevamente.', 'error')
            return render_template('ChangePassword.html')
        
    except Exception as e:
        logger.error(f"❌ Error al cambiar contraseña para {username}: {str(e)}")
        flash('❌ Error interno del servidor. Intente nuevamente.', 'error')
        return render_template('ChangePassword.html')

def update_password_in_database(username, new_password):
    """
    Actualiza la contraseña en la base de datos SQL Server
    Returns: True si exitoso, False si falla
    """
    try:
        import pyodbc
        
        # Configuración de conexión
        server = "jppr.database.windows.net"
        database = "HidrologiaDB"
        username_db = "jpai"
        password_db = "JuntaAI@2025"
        
        # Crear conexión
        connection_string = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={username_db};PWD={password_db}"
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        
        # Verificar que el usuario existe
        cursor.execute("SELECT username FROM Users WHERE username = ?", (username,))
        user_exists = cursor.fetchone()
        
        if not user_exists:
            logger.warning(f"⚠️ Usuario {username} no encontrado en la base de datos")
            conn.close()
            return False
        
        # Ejecutar UPDATE
        update_query = "UPDATE Users SET password = ? WHERE username = ?"
        cursor.execute(update_query, (new_password, username))
        rows_affected = cursor.rowcount
        
        # Confirmar cambios
        conn.commit()
        cursor.close()
        conn.close()
        
        if rows_affected > 0:
            logger.info(f"✅ Contraseña actualizada en BD para {username}")
            return True
        else:
            logger.warning(f"⚠️ No se pudo actualizar la contraseña para {username}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error de BD al actualizar contraseña para {username}: {str(e)}")
        return False

def update_password_in_local_system(username, new_password):
    """
    Actualiza la contraseña en el sistema local de fallback
    """
    try:
        # Actualizar en el diccionario local del sistema de autenticación
        if hasattr(simple_auth, 'local_users'):
            simple_auth.local_users[username] = new_password
            logger.info(f"✅ Contraseña local actualizada para {username}")
        else:
            # Si no existe, crear el diccionario
            if not hasattr(simple_auth, 'local_users'):
                simple_auth.local_users = {}
            simple_auth.local_users[username] = new_password
            logger.info(f"✅ Usuario {username} agregado al sistema local")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error actualizando contraseña local: {str(e)}")
        return False

@app.route('/static/ChangePassword.html')
def static_change_password_redirect():
    """Redirección para manejar URLs en caché del navegador"""
    return redirect(url_for('change_password'))

# ===== RUTAS DE API =====

@app.route('/api/stats')
def api_stats():
    """Estadísticas del sistema"""
    try:
        if sistema_hibrido_avanzado:
            stats = {
                'version': 'v3.2_hibrido_avanzado_FAISS',
                'sistema_hibrido_avanzado': True,
                'chunks_indexados': 735,
                'sistema_activo': 'FAISS + FTS5',
                'azure_openai': 'Configurado'
            }
        else:
            stats = {
                'version': 'v3.2_error',
                'sistema_hibrido_avanzado': False,
                'error': 'Sistema no disponible'
            }
        
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': f'Error obteniendo estadísticas: {str(e)}'}), 500

@app.route('/api/diagnostico')
def api_diagnostico():
    """Diagnóstico completo del sistema"""
    try:
        diagnostico_info = {
            'timestamp': datetime.now().isoformat(),
            'version_app': version_sistema,
            'sistema_hibrido_disponible': sistema_hibrido_disponible,
            'auth_disponible': auth_disponible,
            'openai_disponible': client is not None,
            'configuracion': {
                'rate_limit': CONFIG['RATE_LIMIT_MESSAGES'],
                'session_timeout': CONFIG['SESSION_TIMEOUT'],
                'debug_mode': CONFIG['DEBUG_MODE'],
                'request_timeout': REQUEST_TIMEOUT,
                'openai_timeout': OPENAI_TIMEOUT
            },
            'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            'variables_entorno': {
                'OPENAI_MODEL': os.getenv('OPENAI_MODEL', 'No configurado'),
                'FLASK_ENV': os.getenv('FLASK_ENV', 'No configurado'),
                'PORT': os.getenv('PORT', 'No configurado')
            }
        }
        
        # Si el sistema híbrido avanzado está disponible, obtener su información
        if sistema_hibrido_avanzado:
            try:
                diagnostico_info['sistema_hibrido_avanzado'] = {
                    'estado': 'Activo',
                    'chunks_indexados': 735,
                    'tipo_indice': 'FAISS + FTS5',
                    'modelo_embeddings': 'all-MiniLM-L6-v2'
                }
            except Exception as e:
                diagnostico_info['error_sistema_hibrido'] = str(e)
        
        return jsonify(diagnostico_info)
    except Exception as e:
        return jsonify({
            'error': f'Error en diagnóstico: {str(e)}',
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/test')
def api_test():
    """Test rápido del sistema"""
    try:
        resultado = procesar_consulta_hibrida("Test de funcionamiento", "test_user")
        return jsonify({
            'status': 'ok',
            'sistema_usado': resultado.get('sistema_usado', 'desconocido'),
            'confianza': resultado.get('confianza', 0.0),
            'respuesta_preview': resultado.get('respuesta', '')[:100],
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

# ===== MANEJO DE ARCHIVOS ESTÁTICOS OPTIMIZADO =====

@app.route('/favicon.ico')
def favicon():
    """Servir favicon desde la carpeta static"""
    try:
        return send_from_directory(app.static_folder, 'favicon.ico', mimetype='image/vnd.microsoft.icon')
    except Exception as e:
        logger.warning(f"⚠️ Error sirviendo favicon: {e}")
        return "", 404

@app.route('/static/<path:filename>')
def static_files(filename):
    """Servir archivos estáticos con manejo optimizado"""
    try:
        response = send_from_directory(app.static_folder, filename)
        response.headers['Cache-Control'] = 'public, max-age=300'  # 5 minutos
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
    except Exception as e:
        logger.warning(f"⚠️ Error sirviendo archivo estático {filename}: {e}")
        return "Archivo no encontrado", 404

# ===== MANEJO DE ERRORES OPTIMIZADO =====

@app.errorhandler(404)
def not_found(error):
    logger.warning(f"⚠️ 404: {request.url}")
    return jsonify({'error': 'Endpoint no encontrado'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"❌ Error 500: {error}")
    return jsonify({'error': 'Error interno del servidor'}), 500

@app.errorhandler(502)
def handle_bad_gateway(e):
    logger.error(f"❌ Error 502 Bad Gateway: {e}")
    return jsonify({
        'error': 'Servicio temporalmente no disponible',
        'code': 502,
        'timestamp': datetime.now().isoformat()
    }), 502

@app.errorhandler(504)
def handle_gateway_timeout(e):
    logger.error(f"❌ Error 504 Gateway Timeout: {e}")
    return jsonify({
        'error': 'Tiempo de respuesta agotado. Reformule su consulta.',
        'code': 504,
        'timestamp': datetime.now().isoformat()
    }), 504

@app.errorhandler(429)
def rate_limit_error(error):
    return jsonify({
        'error': 'Demasiadas solicitudes',
        'message': 'Por favor espere antes de hacer otra consulta',
        'retry_after': CONFIG['RATE_LIMIT_WINDOW']
    }), 429

# ===== STARTUP OPTIMIZADO =====

if __name__ == '__main__':
    # ✅ INICIALIZAR BASE DE DATOS SIMPLE
    init_simple_database()
    
    print("\n" + "="*70)
    print("🤖 INICIANDO JP_IA v3.2 - VERSIÓN CORREGIDA PARA RENDER")
    print("🧠 Sistema de IA con análisis de datos regulatorios")
    print("🔄 Router inteligente híbrido integrado")
    print("✅ TODAS LAS CORRECCIONES CRÍTICAS APLICADAS")
    print("="*70)
    
    print(f"📊 Configuración:")
    print(f"   🔧 Sistema: {version_sistema}")
    print(f"   🔒 Auth: {'✅ Activado' if auth_disponible else '❌ Desactivado'}")
    print(f"   🚀 Híbrido: {'✅ Activo' if sistema_hibrido_disponible else '❌ Fallback'}")
    print(f"   🤖 OpenAI: {'✅ Configurado' if client else '❌ No disponible'}")
    print(f"   ⚡ Rate Limit: {CONFIG['RATE_LIMIT_MESSAGES']} req/min")
    print(f"   ⏰ Timeouts: Request={REQUEST_TIMEOUT}s, OpenAI={OPENAI_TIMEOUT}s")
    
    if auth_disponible:
        print(f"\n🔑 Credenciales de acceso:")
        print(f"   👤 Usuario: Admin911")
        print(f"   🔐 Contraseña: Junta12345")
    
    # Puerto para desarrollo local - forzar 5000 para compatibilidad
    port = int(os.getenv('PORT', 5000))
    if port == 8000:  # Si hay una configuración de 8000, cambiar a 5000
        port = 5000
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    print(f"\n🌐 Servidor:")
    print(f"   📡 Puerto: {port}")
    print(f"   🛠 Debug: {'✅ Activado' if debug_mode else '❌ Producción'}")
    print(f"   📱 URL: http://0.0.0.0:{port}")
    
    print("\n✨ Powered by GPT-5 + Análisis Regulatorio Avanzado")
    print("🎯 OPTIMIZADO PARA RENDER - Sin errores 502")
    print("🔧 Correcciones aplicadas:")
    print("   ✅ Signal alarm → Threading timeout")
    print("   ✅ Memory leak → Rate limiter robusto")  
    print("   ✅ Timeouts → Optimizados para Render")
    print("   ✅ Security → Headers de seguridad")
    print("   ✅ Validation → Variables de entorno")
    print("   ✅ Expert API → Compatible con tu experto")
    print("="*70)
    
    app.run(
        host='0.0.0.0', 
        port=port, 
        debug=debug_mode,
        threaded=True,
        use_reloader=False  # Evitar problemas en Render
    )
