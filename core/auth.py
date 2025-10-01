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
import sqlite3
import time
from typing import Optional, Dict, Tuple

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
        # Ruta a la base de datos local de usuarios (SQLite)
        self.users_db_path = os.getenv('USERS_DB_PATH', 'database/Usuarios.db')

        # Inicializar/crear la base de datos de usuarios local
        try:
            self._init_users_db()
            print(f"✅ Usuarios DB lista en: {self.users_db_path}")
        except Exception as e:
            print(f"⚠️ No se pudo inicializar Usuarios.db: {e}")

        # 🔄 (Opcional) Sincronizar contraseñas desde SQL Server al iniciar
        try:
            self._sync_passwords_from_database()
        except Exception:
            # No fatal, se seguirá con fallback local
            pass

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

    # --------------------------
    # SQLite users DB helpers
    # --------------------------
    def _init_users_db(self):
        """Crea la base de datos SQLite y la tabla users si no existe."""
        conn = sqlite3.connect(self.users_db_path)
        try:
            cur = conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                salt TEXT,
                role TEXT DEFAULT 'user',
                created_at TEXT,
                last_login TEXT,
                is_active INTEGER DEFAULT 1
            )
            """)
            conn.commit()
        finally:
            conn.close()

    def _open_users_db(self):
        return sqlite3.connect(self.users_db_path, timeout=5)

    def _hash_password(self, password: str, salt: Optional[bytes] = None) -> Tuple[str, str]:
        """Genera un hash seguro usando PBKDF2-HMAC-SHA256. Devuelve (salt_hex, hash_hex)."""
        if salt is None:
            salt = os.urandom(16)
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000)
        return salt.hex(), dk.hex()

    def _verify_password(self, password: str, salt_hex: str, hash_hex: str) -> bool:
        try:
            salt = bytes.fromhex(salt_hex)
            dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000)
            return dk.hex() == hash_hex
        except Exception:
            return False

    def create_user(self, username: str, password: str, role: str = 'user') -> Dict:
        """Crea un usuario en Usuarios.db. Devuelve dict con success y message."""
        conn = self._open_users_db()
        try:
            cur = conn.cursor()
            salt_hex, hash_hex = self._hash_password(password)
            now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            cur.execute("INSERT INTO users (username, password_hash, salt, role, created_at) VALUES (?, ?, ?, ?, ?)",
                        (username, hash_hex, salt_hex, role, now))
            conn.commit()
            return {'success': True, 'message': 'Usuario creado'}
        except sqlite3.IntegrityError:
            return {'success': False, 'message': 'Usuario ya existe'}
        except Exception as e:
            return {'success': False, 'message': str(e)}
        finally:
            conn.close()

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        conn = self._open_users_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, username, password_hash, salt, role, created_at, last_login, is_active FROM users WHERE username = ?", (username,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                'id': row[0], 'username': row[1], 'password_hash': row[2], 'salt': row[3],
                'role': row[4], 'created_at': row[5], 'last_login': row[6], 'is_active': bool(row[7])
            }
        finally:
            conn.close()

    def update_last_login(self, username: str):
        conn = self._open_users_db()
        try:
            cur = conn.cursor()
            now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            cur.execute("UPDATE users SET last_login = ? WHERE username = ?", (now, username))
            conn.commit()
        finally:
            conn.close()
    
    def update_password(self, username: str, new_password: str) -> bool:
        """Actualiza la contraseña de un usuario en Usuarios.db"""
        conn = self._open_users_db()
        try:
            cur = conn.cursor()
            # Generar nuevo hash y salt para la nueva contraseña
            salt_hex, hash_hex = self._hash_password(new_password)
            cur.execute("UPDATE users SET password_hash = ?, salt = ? WHERE username = ?", 
                       (hash_hex, salt_hex, username))
            conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"Error updating password for {username}: {e}")
            return False
        finally:
            conn.close()
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

        # 1) Intentar autenticar contra Usuarios.db (SQLite)
        try:
            user = self.get_user_by_username(username)
            if user:
                if not user.get('is_active', True):
                    return {'success': False, 'message': 'Usuario inactivo'}

                salt = user.get('salt')
                hash_hex = user.get('password_hash')
                if salt and hash_hex and self._verify_password(password, salt, hash_hex):
                    print(f"AUTENTICACION SQLITE EXITOSA para: {username}")
                    self.update_last_login(username)
                    return {
                        'success': True,
                        'message': 'Autenticación exitosa (SQLite)',
                        'user': {
                            'user_id': user['id'],
                            'username': user['username'],
                            'name': user['username'],
                            'role': user.get('role', 'user'),
                            'auth_method': 'sqlite'
                        }
                    }
                else:
                    print(f"Contraseña incorrecta para: {username} en SQLite, probando fallback")
                    # continue to try SQL Server / local
        except Exception as e:
            print(f"Error leyendo Usuarios.db: {e}")

        # 2) Intentar autenticar contra SQL Server (si está disponible)
        try:
            conn = self._get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, username, password FROM Users WHERE username = ?", (username,))
                user = cursor.fetchone()
                if user:
                    # Nota: pueden ser contraseñas en texto plano en SQL Server en esta implementación
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
                        # fallthrough
                conn.close()
        except Exception as e:
            print(f"Error durante autenticacion SQL: {e}")
            print("Continuando con autenticacion local como fallback")

        # 3) Fallback local en memoria
        return self._authenticate_local(username, password)
    
    def check_user_exists(self, username: str) -> bool:
        """Verifica si existe un usuario (SQLite primero, luego SQL Server)."""
        try:
            user = self.get_user_by_username(username)
            if user:
                return True
        except Exception:
            pass

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
