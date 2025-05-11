import sys
import os
import warnings
# Filtrar advertencias molestas
warnings.filterwarnings("ignore", message=".*import python_multipart.*")
warnings.filterwarnings("ignore", message=".*aifc.*deprecated.*")
warnings.filterwarnings("ignore", message=".*audioop.*deprecated.*")
warnings.filterwarnings("ignore", message=".*PydanticDeprecatedSince20.*")

# Agregar la raíz del proyecto al sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import importlib.util
import pytest
from fastapi.testclient import TestClient

# Importar la app desde app/main.py usando importlib
main_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'app', 'main.py'))
if not os.path.exists(main_path):
    main_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app', 'main.py'))
spec = importlib.util.spec_from_file_location("main", main_path)
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)

client = TestClient(main.app)

def test_home():
    response = client.get("/")
    assert response.status_code == 200
    assert "<!DOCTYPE html>" in response.text

def test_analizar_texto():
    response = client.post("/analizar-texto", json={"texto": "Esto es una prueba de estafa"})
    assert response.status_code == 200
    assert "resultado" in response.json()

def test_transcribir_audio_wav():
    # Se prueba que rechaza archivos que no sean .wav
    response = client.post("/transcribir-audio", files={"file": ("test.mp3", b"fakecontent")})
    assert response.status_code == 400
    assert response.json()["detail"] == "Solo se aceptan archivos .wav"

# Los siguientes tests requieren archivos .wav válidos y/o un servidor gRPC corriendo
# Puedes descomentarlos y adaptarlos en tu entorno local
#
# def test_analizar_audio_grpc():
#     with open("tests/audio_test.wav", "rb") as audio:
#         response = client.post("/analizar-audio-grpc", files={"file": ("audio_test.wav", audio, "audio/wav")})
#     # El test espera un servidor gRPC activo y un archivo válido
#     assert response.status_code == 200
#     data = response.json()
#     assert "transcripcion" in data
#     assert "diagnostico" in data
#     assert "riesgo" in data
#
# def test_analizar_audio_stream():
#     with open("tests/audio_test.wav", "rb") as audio:
#         response = client.post("/analizar-audio-stream", files={"file": ("audio_test.wav", audio, "audio/wav")})
#     assert response.status_code == 200
#     data = response.json()
#     assert "transcripcion" in data
#     assert "diagnostico" in data
#     assert "session_id" in data
