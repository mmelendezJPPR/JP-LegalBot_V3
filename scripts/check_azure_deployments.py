#!/usr/bin/env python3
"""
Script para verificar deployments disponibles en Azure OpenAI
"""

import os
import sys
import requests
from dotenv import load_dotenv

# Cargar configuración
load_dotenv()

def check_azure_deployments():
    """Verificar qué deployments están disponibles en Azure OpenAI"""

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
    api_key = os.getenv("AZURE_OPENAI_KEY", "")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

    if not endpoint or not api_key:
        print("❌ Configuración incompleta. Verifica AZURE_OPENAI_ENDPOINT y AZURE_OPENAI_KEY")
        return

    print("🔍 Verificando deployments disponibles en Azure OpenAI...")
    print(f"📡 Endpoint: {endpoint}")
    print(f"🔑 API Key: {'*' * 20}...{api_key[-8:] if api_key else 'N/A'}")

    # URL para listar deployments
    deployments_url = f"{endpoint}/openai/deployments?api-version={api_version}"

    headers = {
        "api-key": api_key,
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(deployments_url, headers=headers, timeout=10)

        if response.status_code == 200:
            deployments = response.json()
            print("✅ Deployments encontrados:")

            embedding_deployments = []
            chat_deployments = []

            for deployment in deployments.get("data", []):
                model = deployment.get("model", "")
                deployment_id = deployment.get("id", "")

                if "embedding" in model.lower() or "text-embedding" in model.lower():
                    embedding_deployments.append((deployment_id, model))
                elif "gpt" in model.lower() or "chat" in model.lower():
                    chat_deployments.append((deployment_id, model))

            print(f"\n🤖 Deployments de CHAT ({len(chat_deployments)}):")
            for dep_id, model in chat_deployments:
                print(f"   - {dep_id}: {model}")

            print(f"\n🧠 Deployments de EMBEDDINGS ({len(embedding_deployments)}):")
            for dep_id, model in embedding_deployments:
                print(f"   - {dep_id}: {model}")

            if not embedding_deployments:
                print("\n⚠️ No se encontraron deployments de embeddings.")
                print("💡 Recomendaciones:")
                print("   1. Crear un deployment de 'text-embedding-3-small' en Azure OpenAI")
                print("   2. O usar OpenAI directo como fallback")
                print("   3. O usar un modelo de chat que soporte embeddings")

            return embedding_deployments, chat_deployments

        else:
            print(f"❌ Error al consultar deployments: {response.status_code}")
            print(f"   Respuesta: {response.text}")

            if response.status_code == 401:
                print("🔐 Error de autenticación. Verifica tu API key.")
            elif response.status_code == 403:
                print("🚫 Acceso denegado. Verifica permisos en Azure.")
            elif response.status_code == 404:
                print("📍 Endpoint no encontrado. Verifica la URL.")

    except requests.exceptions.RequestException as e:
        print(f"❌ Error de conexión: {e}")
        print("💡 Verifica tu conexión a internet y la URL del endpoint.")

    except Exception as e:
        print(f"❌ Error inesperado: {e}")

    return [], []

def suggest_configuration(embedding_deployments, chat_deployments):
    """Sugerir configuración basada en deployments disponibles"""

    print("\n🔧 CONFIGURACIÓN RECOMENDADA:")

    if embedding_deployments:
        print("✅ Tienes deployments de embeddings disponibles:")
        for dep_id, model in embedding_deployments:
            print(f"   export AZURE_OPENAI_EMBEDDING_DEPLOYMENT={dep_id}")
            break  # Usar el primero disponible

    else:
        print("⚠️ No tienes deployments de embeddings.")
        print("   Opción 1 - Crear deployment en Azure:")
        print("   - Ve a Azure OpenAI Studio")
        print("   - Crea un deployment de 'text-embedding-3-small'")
        print("   - Actualiza AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
        print()
        print("   Opción 2 - Usar OpenAI directo:")
        print("   - export OPENAI_API_KEY=tu_clave_openai")
        print("   - Comenta AZURE_OPENAI_EMBEDDING_DEPLOYMENT")

    if chat_deployments:
        print("✅ Deployments de chat disponibles:")
        for dep_id, model in chat_deployments:
            print(f"   - AZURE_OPENAI_DEPLOYMENT_NAME={dep_id} (modelo: {model})")

if __name__ == "__main__":
    embedding_deps, chat_deps = check_azure_deployments()
    suggest_configuration(embedding_deps, chat_deps)