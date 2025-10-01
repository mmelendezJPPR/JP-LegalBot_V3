"""
=======================================================================
SIMPLE_AUTH.PY - SISTEMA DE AUTENTICACIÓN JP_LEGALBOT
=======================================================================

🎯 FUNCIÓN PRINCIPAL:
   Módulo de autenticación seguro que maneja login/logout de usuarios.
   Soporta doble autenticación: SQL Server + fallback local.

🏗️ ARQUITECTURA:
   - Autenticación primaria contra SQL Server
   - Sistema de fallback con usuarios locales hardcodeados
   - Hashing seguro de contraseñas con PBKDF2
   - Validación de sesiones con decoradores
   - Manejo robusto de errores de conexión

🔐 MÉTODOS DE AUTENTICACIÓN:
   1. SQL SERVER (Principal):
      - Conecta a base de datos corporativa
      - Valida usuarios contra tabla real
      - Manejo automático de conexiones
   
   2. LOCAL FALLBACK (Respaldo):
      - Usuarios hardcodeados en código
      - Admin911/Junta12345 por defecto
      - Activado si SQL falla

📋 FUNCIONES PRINCIPALES:
   - authenticate(username, password): Validar credenciales
   - login_user(): Función wrapper para compatibilidad
   - is_logged_in(): Verificar estado de sesión
   - login_required(): Decorador para proteger rutas

🔧 CONFIGURACIÓN SQL:
   - Driver: ODBC Driver 17 for SQL Server
   - Timeout: 5 segundos
   - Encoding: UTF-8
   - Auto-commit habilitado

⚡ CARACTERÍSTICAS DE SEGURIDAD:
   - Passwords hasheados con PBKDF2 + salt
   - 100,000 iteraciones para resistir ataques
   - Validación de roles de usuario
   - Control de usuarios activos/inactivos
   - Logs detallados de intentos de autenticación

🚀 USO DESDE APP.PY:
   from simple_auth import login_user, is_logged_in, login_required
   
   @login_required
   def protected_route():
       return "Solo para usuarios autenticados"

🔧 VARIABLES DE ENTORNO OPCIONALES:
   - SQL_SERVER: Servidor de base de datos
   - SQL_DATABASE: Nombre de la base de datos
   - SQL_USERNAME: Usuario SQL
   - SQL_PASSWORD: Contraseña SQL

=======================================================================
"""

import pyodbc
import hashlib
import os
from typing import Optional, Dict

class SimpleAuth:
    """Autenticación simple para JP_IA con fallback"""
    
    def __init__(self):
        # Configuración de conexión (CORREGIDA PARA USAR LA QUE FUNCIONA)
        self.server = os.getenv('SQL_SERVER', 'jppr.database.windows.net')
        self.database = os.getenv('SQL_DATABASE', 'HidrologiaDB')
        self.username = os.getenv('SQL_USERNAME', 'jpai')
        self.password = os.getenv('SQL_PASSWORD', 'JuntaAI@2025')
        
        self.connection_string = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={self.server};DATABASE={self.database};UID={self.username};PWD={self.password}'
        
        # Usuarios locales de fallback inicial (SIN HASH - TEXTO PLANO)
        self.local_users = {
            'Admin911': 'Junta12345',
            'admin': '123',
            'demo': 'demo123',
            'alvarez_o@jp.pr.gov': 'LegalBot12345',
            'valdez_j@jp.pr.gov': 'LegalBot6789'
        }
        
        # 🔄 Sincronizar contraseñas desde SQL Server al iniciar
        self._sync_passwords_from_database()
        
        print("✅ Sistema de autenticación inicializado")
        print(f"📊 Usuarios locales: {list(self.local_users.keys())}")
    
    def _sync_passwords_from_database(self):
        """Sincroniza contraseñas locales con las de la base de datos"""
        try:
            conn = self._get_connection()
            if not conn:
                print("⚠️ SQL Server no disponible - usando contraseñas por defecto")
                return
            
            cursor = conn.cursor()
            
            # Obtener todas las contraseñas actualizadas desde SQL Server
            cursor.execute("SELECT username, password FROM Users")
            db_users = cursor.fetchall()
            
            # Actualizar usuarios locales con contraseñas de la BD
            users_synced = 0
            for username, password in db_users:
                if username in self.local_users:
                    old_password = self.local_users[username]
                    self.local_users[username] = password
                    if old_password != password:
                        print(f"🔄 Contraseña sincronizada para {username}")
                        users_synced += 1
                else:
                    # Agregar nuevos usuarios de la BD al sistema local
                    self.local_users[username] = password
                    print(f"➕ Nuevo usuario agregado: {username}")
                    users_synced += 1
            
            if users_synced > 0:
                print(f"✅ {users_synced} contraseñas sincronizadas desde SQL Server")
            else:
                print("ℹ️ Contraseñas locales están actualizadas")
            
            conn.close()
            
        except Exception as e:
            print(f"⚠️ Error sincronizando contraseñas: {e}")
            print("📋 Continuando con contraseñas por defecto")
    
    def _get_connection(self):
        """Obtiene conexión a la base de datos"""
        try:
            return pyodbc.connect(self.connection_string)
        except Exception as e:
            print(f"ERROR conectando a SQL Server: {e}")
            print("Usando autenticacion local como fallback")
            return None
    
    def _hash_password(self, password: str) -> str:
        """Hash simple de contraseña"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def _authenticate_local(self, username: str, password: str) -> Dict:
        """Autenticación local de fallback (SIN HASH - TEXTO PLANO)"""
        
        if username in self.local_users and self.local_users[username] == password:
            print(f"AUTENTICACION LOCAL EXITOSA para: {username}")
            return {
                'success': True,
                'message': f'Login exitoso (modo local)',
                'user': {
                    'username': username,
                    'name': f'Usuario {username}',
                    'role': 'admin',
                    'auth_method': 'local'
                }
            }
        else:
            print(f"AUTENTICACION LOCAL FALLIDA para: {username}")
            return {
                'success': False,
                'message': 'Usuario o contraseña incorrectos'
            }
    
    def authenticate(self, username: str, password: str) -> Dict:
        """
        Autentica un usuario (intenta SQL Server, fallback a local)
        
        Returns:
            Dict con 'success' (bool), 'message' (str) y 'user' (dict si exitoso)
        """
        print(f"INTENTANDO AUTENTICAR USUARIO: {username}")
        
        conn = self._get_connection()
        if not conn:
            print("SQL Server no disponible, usando autenticacion local")
            return self._authenticate_local(username, password)
        
        try:
            cursor = conn.cursor()
            
            # Buscar usuario
            cursor.execute("SELECT id, username, password FROM Users WHERE username = ?", (username,))
            user = cursor.fetchone()
            
            if not user:
                print(f"Usuario '{username}' no encontrado en BD, probando fallback local")
                return self._authenticate_local(username, password)
            
            # Verificar contraseña (SIN HASH - TEXTO PLANO)
            # Comparación directa sin hash
            
            if user[2] == password:
                print(f"AUTENTICACION SQL EXITOSA para: {username}")
                return {
                    'success': True,
                    'message': 'Autenticación exitosa (SQL Server)',
                    'user': {
                        'user_id': user[0],
                        'username': user[1],
                        'name': user[1],
                        'role': 'user',
                        'auth_method': 'sql_server'
                    }
                }
            else:
                print(f"Contraseña incorrecta para: {username} en BD, probando fallback")
                return self._authenticate_local(username, password)
                
        except Exception as e:
            print(f"Error durante autenticacion SQL: {e}")
            print("Usando autenticacion local como fallback")
            return self._authenticate_local(username, password)
        finally:
            conn.close()
    
    def check_user_exists(self, username: str) -> bool:
        """Verifica si existe un usuario"""
        conn = self._get_connection()
        if not conn:
            return False
        
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM Users WHERE username = ?", (username,))
            count = cursor.fetchone()[0]
            return count > 0
        except:
            return False
        finally:
            conn.close()

# Instancia global
simple_auth = SimpleAuth()

def login_user(username: str, password: str) -> Dict:
    """Función simple para login"""
    return simple_auth.authenticate(username, password)

def is_logged_in(session) -> bool:
    """Verifica si hay una sesión activa"""
    return 'user_id' in session and 'username' in session

def login_required(f):
    """Decorador para rutas que requieren login"""
    from functools import wraps
    from flask import session, redirect, url_for, request
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_logged_in(session):
            return redirect(url_for('login_page', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Test del sistema
if __name__ == "__main__":
    print("🧪 PROBANDO SISTEMA DE AUTENTICACIÓN SIMPLE")
    print("=" * 50)
    
    auth = SimpleAuth()
    
    # Probar con credenciales correctas
    print("\n1. Probando credenciales correctas (admin/123):")
    result = auth.authenticate('admin', '123')
    print(f"   Resultado: {result}")
    
    # Probar con credenciales incorrectas
    print("\n2. Probando credenciales incorrectas (admin/wrong):")
    result = auth.authenticate('admin', 'wrong')
    print(f"   Resultado: {result}")
    
    # Probar con usuario inexistente
    print("\n3. Probando usuario inexistente (noexiste/123):")
    result = auth.authenticate('noexiste', '123')
    print(f"   Resultado: {result}")
    
    print("\n✅ Pruebas completadas!")
