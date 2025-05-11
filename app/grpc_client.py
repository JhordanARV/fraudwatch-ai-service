"""Cliente gRPC para enviar audio al servicio de detección de fraudes.
Ejecuta con python app/grpc_client.py [archivo_wav] [session_id]

Ejemplo: python app/grpc_client.py prueba.wav demo-session-1

Si no se pasan argumentos, usará 'prueba.wav' y 'demo-session-1' por defecto.
"""
import sys
import os
# Añadir la raíz del proyecto al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import grpc
import app.proto.fraud_detection_pb2 as fraud_detection_pb2
import app.proto.fraud_detection_pb2_grpc as fraud_detection_pb2_grpc

# Parámetros por defecto
AUDIO_PATH = sys.argv[1] if len(sys.argv) > 1 else 'prueba.wav'
SESSION_ID = sys.argv[2] if len(sys.argv) > 2 else 'demo-session-1'

def audio_chunks_from_file(path, session_id=SESSION_ID):
    with open(path, "rb") as f:
        data = f.read()
        yield fraud_detection_pb2.AudioChunk(data=data, session_id=session_id)

def main():
    channel = grpc.insecure_channel("localhost:50051")
    stub = fraud_detection_pb2_grpc.FraudDetectionStub(channel)
    print(f"Enviando archivo de audio '{AUDIO_PATH}' al servidor gRPC...")
    responses = stub.StreamAudio(audio_chunks_from_file(AUDIO_PATH, SESSION_ID))
    for response in responses:
        print("\n=== RESULTADO DEL ANÁLISIS ===")
        print(f"Transcripción: {response.transcripcion}")
        print(f"Diagnóstico: {response.diagnostico}")
        print(f"Riesgo: {response.riesgo}%")

if __name__ == "__main__":
    main()