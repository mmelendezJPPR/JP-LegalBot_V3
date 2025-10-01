# 🚀 Deployment en Render - JP_IA

## Instrucciones para Deploy en Render.com

### 1. Preparación del Repositorio
✅ **Ya completado**: Todos los archivos necesarios están incluidos

### 2. Crear Servicio en Render

1. **Conectar GitHub**:
   - Ve a [render.com](https://render.com)
   - Connect Repository: `mmelendezJPPR/JP_LegalBot`

2. **Configurar el Servicio**:
   - **Type**: Web Service
   - **Runtime**: Docker
   - **Dockerfile Path**: `./Dockerfile` (automático)
   - **Region**: Oregon (US West)

### 3. Variables de Entorno REQUERIDAS

Configura estas variables en Render Dashboard > Environment:

```bash
# OBLIGATORIO
OPENAI_API_KEY=sk-your-openai-key-here

# Configuración de producción
FLASK_ENV=production
FLASK_DEBUG=false
PORT=10000

# SQL Server (OPCIONAL - la app funciona sin estas)
SQL_SERVER=jppr.database.windows.net
SQL_DATABASE=HidrologiaDB  
SQL_USERNAME=jpai
SQL_PASSWORD=JuntaAI@2025
```

### 4. Configuración del Build

Render detectará automáticamente el `Dockerfile` y:
- ✅ Instalará drivers ODBC para SQL Server
- ✅ Instalará dependencias Python
- ✅ Configurará el contenedor Linux

### 5. Acceso al Sistema

Una vez desplegado:
- **URL**: `https://tu-app.onrender.com`
- **Usuario**: `Admin911`
- **Contraseña**: `Junta12345`

**Alternativas** (si SQL Server falla):
- `admin` / `123`
- `demo` / `demo123`

### 6. Características del Deploy

✅ **Autenticación con Fallback**: SQL Server → Usuarios locales
✅ **Sistema Híbrido**: 6 especialistas funcionando
✅ **Base de Conocimiento**: 12 tomos cargados
✅ **HTTPS**: Automático en Render
✅ **Escalado**: Automático
✅ **Logs**: Disponibles en Dashboard

### 7. Solución de Problemas

#### Error: "ODBC Driver not found"
- ✅ **Solucionado**: Dockerfile instala drivers automáticamente

#### Error: "SQL Server connection failed"  
- ✅ **Solucionado**: Sistema usa autenticación local como fallback

#### Error: "OpenAI API key not found"
- ❗ **Acción requerida**: Configurar `OPENAI_API_KEY` en Environment

### 8. Logs Esperados

```
✅ Cliente OpenAI configurado correctamente
🔄 SQL Server no disponible, usando autenticación local
✅ Sistema Híbrido JP_IA v3.0 importado correctamente
✅ Cargados 12 tomos para análisis experto
🌐 Puerto: 10000
```

### 9. Tiempo de Deploy

- **Primera vez**: ~5-8 minutos (install drivers)
- **Updates**: ~2-3 minutos
- **Cold starts**: ~30 segundos

¡El sistema estará listo para usar! 🎉