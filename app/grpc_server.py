import sys
import os
# Añadir la raíz del proyecto al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import grpc
from concurrent import futures
import app.proto.fraud_detection_pb2 as fraud_detection_pb2
import app.proto.fraud_detection_pb2_grpc as fraud_detection_pb2_grpc

# Importa las funciones del backend REST
from app.main import transcribir_audio, analizar_con_ia

class FraudDetectionServicer(fraud_detection_pb2_grpc.FraudDetectionServicer):
    def StreamAudio(self, request_iterator, context):
        # Recibe fragmentos de audio, los guarda, y responde con la transcripción y diagnóstico
        session_id = None
        audio_data = b""
        for audio_chunk in request_iterator:
            session_id = audio_chunk.session_id
            audio_data += audio_chunk.data
            # Aquí podrías guardar el audio a un archivo temporal y transcribirlo
            # Por simplicidad, asumimos que el audio está completo al final del stream
        # Guardar el audio recibido a un archivo temporal
        temp_path = f"temp_{session_id or 'audio'}.wav"
        with open(temp_path, "wb") as f:
            f.write(audio_data)
        texto = transcribir_audio(temp_path)
        if texto is None:
            texto = ""
        diagnostico = analizar_con_ia(texto)
        if diagnostico is None:
            diagnostico = ""
        # Devuelve el resultado al cliente, nunca None
        yield fraud_detection_pb2.TranscriptionResult(
            transcripcion=texto or "",
            diagnostico=diagnostico or "",
            riesgo=extraer_riesgo(diagnostico or "")
        )

def extraer_riesgo(diagnostico):
    import re
    import json
    
    # Para el nuevo formato JSON estructurado
    if diagnostico and "Riesgo:" in diagnostico:
        match = re.search(r"Riesgo:\s*([0-9]{1,3})/100", diagnostico)
        if match:
            return int(match.group(1))
    
    # Para respuestas no estructuradas
    match = re.search(r"([0-9]{1,3})%", diagnostico)
    if match:
        return int(match.group(1))
    match = re.search(r"Puntuación de riesgo:\s*([0-9]{1,3})", diagnostico)
    if match:
        return int(match.group(1))
    
    # Valor por defecto si no se encuentra ningún patrón
    return 50  # Riesgo moderado como valor predeterminado

def serve():
    try:
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        fraud_detection_pb2_grpc.add_FraudDetectionServicer_to_server(FraudDetectionServicer(), server)
        server.add_insecure_port('[::]:50051')
        server.start()
        print("gRPC server running on port 50051...")
        print("Presiona Ctrl+C para terminar el servidor")
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("\nServidor gRPC detenido")
    except Exception as e:
        print(f"Error en el servidor gRPC: {e}")

if __name__ == '__main__':
    serve()
