# 🤖 JP_IA - Sistema Experto en Planificación

Sistema de Inteligencia Artificial especializado en reglamentos de planificación de Puerto Rico. Combina análisis experto con IA avanzada para brindar consultas especializadas en zonificación, procedimientos, construcción y más.

## � Características Principales

- **🧠 Sistema Híbrido**: Combina especialistas dedicados con IA general
- **�🎯 6 Especialistas**: Zonificación, Procedimientos, Técnico-Gráfico, Edificabilidad, Ambiental e Histórico
- **🔐 Autenticación**: Sistema de login seguro
- **📚 Base de Conocimiento**: 12 tomos de reglamentos de planificación
- **⚡ Respuestas Inteligentes**: Selección automática del especialista más adecuado
- **🌐 Interfaz Web**: Chat interactivo con indicadores en tiempo real

## 🚀 Inicio Rápido

### Prerequisitos
```bash
Python 3.8+
OpenAI API Key
```

### Instalación
```bash
# 1. Clonar el repositorio
git clone https://github.com/mmelendezJPPR/JP_LegalBot.git
cd JP_LegalBot

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
# Crear archivo .env con:
OPENAI_API_KEY=tu_api_key_aqui

# 4. Ejecutar la aplicación
python app.py
```

### Acceso al Sistema
- **URL**: http://127.0.0.1:5002
- **Usuario**: Admin911  
- **Contraseña**: Junta12345

## 🏗️ Arquitectura del Sistema

### 📂 Estructura del Proyecto

```
📂 JP_IA/
├── 🐍 app.py                    # Aplicación Flask principal
├── 🔐 simple_auth.py           # Sistema de autenticación
├── 🤖 sistema_hibrido.py       # Router inteligente de consultas
├── 🧠 experto_planificacion.py # Sistema experto base
├── ⚡ mini_especialistas.py    # 6 especialistas dedicados
├── 📋 requirements.txt         # Dependencias del proyecto
├── 🌐 templates/
│   ├── index.html              # Interfaz de chat principal
│   └── login.html              # Página de autenticación
├── 🎨 static/
│   ├── css/style.css           # Estilos de la aplicación
│   ├── js/app.js              # Lógica del chat frontend
│   └── 🖼️ JP_V2.png           # Logos e imágenes
├── 📊 data/                    # Base de conocimiento
│   ├── TOMO1-12_*.txt         # Reglamentos de planificación
│   └── RespuestasParaChatBot/ # Respuestas pre-generadas
└── 🛠️ utils/                  # Utilidades del sistema
    ├── cargador_tomos.py      # Carga de documentos
    └── procesador_texto.py    # Procesamiento de texto
```

## 🎯 Especialistas Disponibles

| Especialista | Área de Expertise | Tomo |
|--------------|-------------------|------|
| **Zonificación** | Distritos, usos permitidos, clasificaciones | 2-3 |
| **Procedimientos** | Trámites, permisos, solicitudes | 4-5 |
| **Técnico Gráfico** | Planos, especificaciones técnicas | 6-7 |
| **Edificabilidad** | Densidad, parámetros de construcción | 8-9 |
| **Ambiental** | Impacto ambiental, infraestructura | 10-11 |
| **Histórico** | Conservación patrimonial, SHPO | 12 |

## � Funcionalidades

### ✅ Sistema Híbrido Inteligente
- **Router Automático**: Selecciona el especialista más apropiado
- **Análisis de Confianza**: Evalúa la certeza de cada respuesta
- **Fallback Inteligente**: Sistema general para consultas ambiguas

### ✅ Interfaz de Usuario
- **Chat en Tiempo Real**: Conversación fluida con indicadores
- **Autenticación Segura**: Control de acceso con sesiones
- **Diseño Responsivo**: Compatible con dispositivos móviles
- **Indicadores Visuales**: Estados de carga y procesamiento

### ✅ Base de Conocimiento
- **12 Tomos Regulatorios**: Documentación completa de planificación
- **Respuestas Pre-generadas**: Casos comunes optimizados
- **Actualización Dinámica**: Carga automática de contenido

### 🧠 Sistema de Memoria Semántica (V3)
- **Embeddings Avanzados**: Búsqueda semántica con Azure OpenAI text-embedding-3-small
- **Memoria Conversacional**: Contexto persistente entre consultas usando embeddings
- **Búsqueda Híbrida**: Combina búsqueda vectorial (semántica) con búsqueda léxica (keyword)
- **Aprendizaje Incremental**: Actualización automática del índice de embeddings
- **Consolidación de Memoria**: Conversión de interacciones frecuentes en conocimiento a largo plazo
- **Reranking Inteligente**: Mejora de resultados por diversidad y relevancia

## 🔧 Configuración

### Variables de Entorno (.env)

#### 🚀 Embeddings Locales (Nuevo - Recomendado)

**Características:**
- ✅ **Sin costos de API** - Funciona completamente offline
- ✅ **Privacidad total** - Datos nunca salen del servidor
- ✅ **Modelo multilingüe** - Soporta español e inglés perfectamente
- ✅ **Rendimiento optimizado** - Modelo ligero (24MB, 384 dimensiones)

**Configuración automática:**
```bash
# El sistema detecta automáticamente y usa embeddings locales
# No se requiere configuración adicional - funciona out-of-the-box
python app.py
```

**Para reconstruir índice con embeddings locales:**
```bash
python scripts/rebuild_index_local.py
```

#### Configuración Azure OpenAI (Opcional)
```bash
# Azure OpenAI (para chat - más económico y seguro)
AZURE_OPENAI_ENDPOINT=https://tu-recurso.openai.azure.com/
AZURE_OPENAI_KEY=tu_clave_azure_aqui
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4.1

# Embeddings - DESHABILITADO (usando locales por defecto)
# AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
```

### 🚀 Inicio Rápido con Embeddings

1. **Configura OpenAI API Key** (requerido para embeddings):
   ```bash
   # Edita el archivo .env
   OPENAI_API_KEY=sk-tu_clave_openai_aqui
   ```

2. **Configura Azure OpenAI** (opcional pero recomendado):
   ```bash
   # En .env agrega:
   AZURE_OPENAI_ENDPOINT=https://tu-recurso.openai.azure.com/
   AZURE_OPENAI_KEY=tu_clave_azure
   AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4.1
   ```

3. **Prueba los embeddings**:
   ```bash
   python scripts/test_embeddings.py
   ```

### ⚙️ Funcionamiento de Embeddings

- **Con Azure + OpenAI**: Chat usa Azure (económico), embeddings usan OpenAI directo
- **Solo Azure**: Si tienes deployment de embeddings en Azure
- **Solo OpenAI**: Funciona pero más costoso
- **Sin embeddings**: El sistema usa solo búsqueda textual (funciona pero menos preciso)

## 📊 API Endpoints

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/` | GET | Página principal (redirige a login) |
| `/login` | GET/POST | Autenticación de usuarios |
| `/logout` | POST | Cerrar sesión |
| `/chat` | POST | Procesar consulta de chat |
| `/api/stats` | GET | Estadísticas del sistema |

## 🤝 Contribución

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/nueva-funcionalidad`)
3. Commit tus cambios (`git commit -m 'Agregar nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Ver `LICENSE` para más detalles.

## 👥 Autores

- **Junta de Planificación de Puerto Rico** - *Desarrollo inicial*
- **Equipo JP_IA** - *Implementación y mantenimiento*

## 🙏 Agradecimientos

- OpenAI por la API GPT
- Comunidad de desarrolladores de Flask
- Equipo de la Junta de Planificación

---

## 📞 Soporte

Para soporte técnico o consultas:
- **Email**: [soporte@jp.pr.gov](mailto:soporte@jp.pr.gov)
- **Issues**: [GitHub Issues](https://github.com/mmelendezJPPR/JP_LegalBot/issues)

---

### � Última Actualización: Septiembre 2025
**Versión**: 3.0 - Sistema Híbrido con Especialistas Mejorados

- El sistema está optimizado para desarrollo local
- La base de datos ya está configurada y funcionando
- Todos los archivos de prueba fueron eliminados para simplicidad
- Solo se mantuvieron los archivos esenciales para el funcionamiento

---

### 🎉 ¡Sistema listo para usar!
**Solo ejecuta `python app.py` y ve a http://127.0.0.1:5002**