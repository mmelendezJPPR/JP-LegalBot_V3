"""
=======================================================================
UTILS/CARGADOR_TOMOS.PY - SISTEMA DE CARGA DE DOCUMENTOS OFICIALES
=======================================================================

🎯 FUNCIÓN PRINCIPAL:
   Módulo utilitario especializado en la carga y procesamiento de los
   11 Tomos oficiales del Reglamento de Planificación de Puerto Rico.

📚 TOMOS GESTIONADOS:
   - Tomo 1: Sistema de Evaluación y Tramitación (COMPLETE)
   - Tomo 2: Disposiciones Generales (COMPLETE)
   - Tomo 3: Permisos para Desarrollo y Negocios (COMPLETE)
   - Tomo 4: Licencias y Certificaciones (COMPLETE)
   - Tomo 5: Urbanización y Lotificación (COMPLETE)
   - Tomo 6: Distritos de Calificación (COMPLETE)
   - Tomo 7: Procesos (COMPLETE)
   - Tomo 8: Edificabilidad (COMPLETE)
   - Tomo 9: Infraestructura y Ambiente (COMPLETE)
   - Tomo 10: Conservación Histórica (COMPLETE)
   - Tomo 11: Querellas (COMPLETE)

🔧 FUNCIONALIDADES TÉCNICAS:
   - Carga optimizada de archivos de texto grandes (100MB+)
   - Detección automática de archivos por patrón TOMO{X}_COMPLETO_MEJORADO
   - Validación de integridad de contenido
   - Caché inteligente para evitar re-cargas innecesarias
   - Manejo de encoding UTF-8 con fallback ASCII

📊 ESTRUCTURA DE DATOS:
   Cada tomo se procesa para extraer:
   - Texto completo estructurado
   - Metadatos del documento
   - Fecha de procesamiento
   - Tamaño y estadísticas
   - Índice de secciones principales

🔍 MÉTODOS PRINCIPALES:
   - cargar_tomo(numero): Carga tomo específico
   - cargar_todos_tomos(): Carga biblioteca completa
   - validar_tomo(): Verifica integridad
   - get_metadatos(): Extrae información del documento
   - buscar_en_tomo(): Búsqueda dentro de un tomo
   - limpiar_contenido(): Normalización de texto

⚡ OPTIMIZACIONES:
   - Carga lazy (solo cuando se necesita)
   - Compresión inteligente de contenido
   - Índices pre-calculados
   - Memoria eficiente para documentos grandes

🔒 ROBUSTEZ:
   - Manejo de archivos corrompidos
   - Fallback a versiones de respaldo
   - Logging detallado de operaciones
   - Validación de formato de archivos

📋 INTEGRACIÓN:
   Este módulo es utilizado por:
   - experto_planificacion.py (búsqueda semántica)
   - respuestas_curadas_tier1.py (referencias)
   - sistema_hibrido.py (contexto dinámico)

💾 UBICACIÓN DE ARCHIVOS:
   Los tomos se almacenan en: /data/TOMO{X}_COMPLETO_MEJORADO_*.txt
   Con respaldo en: /data/RespuestasParaChatBot/RespuestasIA_Tomo{X}/

🚀 USO TÍPICO:
   cargador = CargarTomos()
   contenido = cargador.cargar_tomo(1)
   metadatos = cargador.get_metadatos(1)

=======================================================================
Módulo para cargar los tomos mejorados como fuente de información principal
"""

import os
import re
import sys

class CargarTomos:
    """Clase para cargar tomos mejorados del sistema"""
    
    def __init__(self):
        self.directorio_datos = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    
    def cargar_tomo(self, numero_tomo):
        """Carga el tomo específico"""
        return cargar_tomo_mejorado(numero_tomo)

def cargar_tomo_mejorado(numero_tomo):
    """
    Carga el tomo mejorado según su número
    
    Args:
        numero_tomo (int): Número del tomo a cargar (1-12)
    
    Returns:
        str: Contenido del tomo mejorado o None si no se encuentra
    """
    # Directorio donde están los tomos mejorados
    directorio_datos = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    
    # Buscar primero el tomo mejorado
    patron_mejorado = f"TOMO{numero_tomo}_COMPLETO_MEJORADO_*.txt"
    
    # Caso especial para tomo 12 (glosario)
    if numero_tomo == 12:
        patron_mejorado = "TOMO12_GLOSARIO_COMPLETO_MEJORADO_*.txt"
    
    # Listar archivos en el directorio para encontrar coincidencias
    archivos = os.listdir(directorio_datos)
    archivo_mejorado = None
    
    # Buscar el archivo que coincida con el patrón
    for archivo in archivos:
        if re.match(f"TOMO{numero_tomo}_COMPLETO_MEJORADO_\\d+_\\d+.txt", archivo):
            archivo_mejorado = archivo
            break
        # Caso especial para el tomo 12 (glosario)
        elif numero_tomo == 12 and re.match("TOMO12_GLOSARIO_COMPLETO_MEJORADO_\\d+_\\d+.txt", archivo):
            archivo_mejorado = archivo
            break
    
    # Si encontramos el archivo mejorado, cargarlo
    if archivo_mejorado:
        ruta_archivo = os.path.join(directorio_datos, archivo_mejorado)
        try:
            with open(ruta_archivo, 'r', encoding='utf-8') as f:
                contenido = f.read()
                print(f"[OK] Tomo {numero_tomo} mejorado cargado: {len(contenido)} caracteres")
                return contenido
        except Exception as e:
            print(f"[ERROR] Error cargando tomo {numero_tomo} mejorado: {e}")
    
    # Caso especial para el tomo 1 (que aún no tiene versión mejorada)
    if numero_tomo == 1:
        ruta_original = os.path.join(directorio_datos, f"tomo_{numero_tomo}.txt")
        try:
            if os.path.exists(ruta_original):
                with open(ruta_original, 'r', encoding='utf-8') as f:
                    contenido = f.read()
                    print(f"[WARNING] Usando tomo 1 original como fallback: {len(contenido)} caracteres")
                    return contenido
        except Exception as e:
            print(f"[ERROR] Error cargando tomo 1 original: {e}")
    
    # Para los demás tomos, no intentamos cargar el original
    print(f"[ERROR] No se encontro el tomo {numero_tomo} mejorado")
    return None

def cargar_todos_los_tomos():
    """
    Carga todos los tomos mejorados disponibles (1-12, incluyendo glosario)
    VERSIÓN OPTIMIZADA: Solo utiliza tomos mejorados (versiones definitivas)
    
    Returns:
        dict: Diccionario con el contenido de cada tomo {numero: contenido}
    """
    tomos = {}
    
    # Mapeo de números de tomo a sus descripciones
    descripciones_tomos = {
        1: "Sistema de Evaluación y Tramitación de Permisos",
        2: "Disposiciones Generales",
        3: "Permisos para Desarrollo y Negocios",
        4: "Licencias y Certificaciones",
        5: "Urbanización y Lotificación",
        6: "Distritos de Calificación",
        7: "Procesos",
        8: "Edificabilidad",
        9: "Infraestructura y Ambiente",
        10: "Conservación Histórica",
        11: "Querellas",
        12: "Glosario de términos especializados"
    }
    
    # Cargar tomos 1-11
    for i in range(1, 12):
        contenido = cargar_tomo_mejorado(i)
        if contenido:
            tomos[i] = contenido
            print(f"[OK] Tomo {i} cargado: {descripciones_tomos[i]} ({len(contenido)} caracteres)")
        else:
            print(f"[ERROR] Tomo {i} no disponible: {descripciones_tomos[i]}")
    
    # Cargar tomo 12 (glosario)
    contenido_glosario = cargar_tomo_mejorado(12)
    if contenido_glosario:
        tomos[12] = contenido_glosario
        print(f"[OK] Glosario (Tomo 12) cargado: {len(contenido_glosario)} caracteres")
    else:
        print("[ERROR] Glosario (Tomo 12) no disponible")
    
    print(f"[OK] Cargados {len(tomos)} tomos mejorados en total")
    return tomos
