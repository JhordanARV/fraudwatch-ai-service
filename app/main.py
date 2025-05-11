from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import grpc
import app.proto.fraud_detection_pb2 as fraud_detection_pb2
import app.proto.fraud_detection_pb2_grpc as fraud_detection_pb2_grpc
import speech_recognition as sr
from openai import OpenAI
from pydub import AudioSegment
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env automáticamente
load_dotenv()

app = FastAPI(title="FraudWatch AI Service", description="API y gRPC para la detección de fraude en texto y audio", version="1.0")

# Montar carpeta frontend como estáticos
app.mount("/static", StaticFiles(directory="frontend", html=True), name="static")

# Configura tu API Key aquí (mejor usar variable de entorno en producción)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def transcribir_audio(audio_path):
    try:
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="es"
            )
        return transcript.text
    except Exception as e:
        return f"Error en la transcripción con Whisper: {e}"

def analizar_con_ia(texto):
    prompt = f"""
Eres un analista de seguridad. Evalúa si el siguiente mensaje es potencialmente una estafa.
Devuelve tu respuesta SOLO en este formato JSON exacto sin añadir ningún otro texto:
{{"diagnostico": "Estafa" o "No Estafa", "explicacion": "tu explicación aquí", "riesgo": número entre 0 y 100}}

Mensaje:
{texto}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un analista de seguridad de ciberfraudes que responde solo en formato JSON estructurado."},
                {"role": "user", "content": prompt}
            ]
        )
        respuesta = response.choices[0].message.content.strip()
        
        # Intenta parsear como JSON
        import json
        try:
            datos_json = json.loads(respuesta)
            # Formatea la respuesta en texto legible
            respuesta_formateada = f"Diagnóstico: {datos_json.get('diagnostico', '?')}\n\n"
            respuesta_formateada += f"Explicación: {datos_json.get('explicacion', '?')}\n\n"
            respuesta_formateada += f"Riesgo: {datos_json.get('riesgo', '?')}/100"
            return respuesta_formateada
        except json.JSONDecodeError:
            # Si no se puede parsear como JSON, devuelve la respuesta original
            return respuesta
    except Exception as e:
        return f"Error en el análisis con OpenAI: {e}"

class AnalisisTextoResponse(BaseModel):
    resultado: str
    class Config:
        schema_extra = {
            "example": {
                "resultado": "Diagnóstico: Estafa\n\nExplicación: Este mensaje solicita datos personales...\n\nRiesgo: 90/100"
            }
        }

class TranscripcionResponse(BaseModel):
    transcripcion: str
    class Config:
        schema_extra = {
            "example": {
                "transcripcion": "Has sido seleccionado para recibir un premio..."
            }
        }

class AnalisisAudioStreamResponse(BaseModel):
    session_id: str = None
    transcripcion: str
    diagnostico: str = None
    ruta_archivo: str = None
    class Config:
        schema_extra = {
            "example": {
                "session_id": "session-123",
                "transcripcion": "Has sido seleccionado para recibir un premio...",
                "diagnostico": "Diagnóstico: Estafa\n\nExplicación: Este mensaje solicita datos personales...\n\nRiesgo: 90/100",
                "ruta_archivo": "temp_stream_16k.wav"
            }
        }

@app.post("/analizar-texto", response_model=AnalisisTextoResponse, tags=["Análisis"])
def endpoint_analizar_texto(payload: dict):
    texto = payload.get("texto", "")
    if not texto:
        raise HTTPException(status_code=400, detail="Texto vacío")
    resultado = analizar_con_ia(texto)
    return {"resultado": resultado}

@app.post("/transcribir-audio", response_model=TranscripcionResponse, tags=["Transcripción"])
def endpoint_transcribir_audio(file: UploadFile = File(...)):
    if not file.filename.endswith('.wav'):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .wav")
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as f:
        f.write(file.file.read())
    texto = transcribir_audio(temp_path)
    os.remove(temp_path)
    return {"transcripcion": texto}

@app.post("/analizar-audio-stream", response_model=AnalisisAudioStreamResponse, tags=["Análisis"])
def analizar_audio_stream(file: UploadFile = File(...), session_id: str = None, texto_acumulado: str = Form(None)):
    """
    Endpoint para analizar fragmentos de audio en tiempo real.
    Recibe un fragmento de audio (wav), un session_id opcional y el texto acumulado.
    Devuelve la transcripción y el análisis de fraude.
    """
    # Guardar archivo temporalmente, sin importar el nombre
    temp_path = f"temp_stream.wav"
    with open(temp_path, "wb") as f:
        f.write(file.file.read())
    # Validar encabezado RIFF/WAVE
    try:
        with open(temp_path, "rb") as f:
            header = f.read(12)
            if not (header[:4] == b'RIFF' and header[8:12] == b'WAVE'):
                os.remove(temp_path)
                raise HTTPException(status_code=400, detail="El archivo no es un WAV válido.")
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=400, detail="No se pudo leer el archivo de audio.")
    # Convertir a 16kHz mono para máxima compatibilidad
    temp_path_16k = "temp_stream_16k.wav"
    audio = AudioSegment.from_wav(temp_path)
    audio = audio.set_frame_rate(16000).set_channels(1)
    audio.export(temp_path_16k, format="wav")
    # --- Detección de silencio en el backend ---
    min_size_bytes = 2000  # Tamaño mínimo para considerar que hay voz (~0.1 seg)
    min_rms = 10  # Energía mínima (ajustable, ahora más sensible)
    import os
    file_size = os.path.getsize(temp_path_16k)
    rms = audio.rms
    print(f"[DEBUG] Tamaño archivo recibido: {file_size} bytes | RMS: {rms}")
    if file_size < min_size_bytes or rms < min_rms:
        print('[DEBUG] Fragmento ignorado por silencio o archivo vacío (backend)')
        return {
            "session_id": session_id,
            "transcripcion": "",
            "diagnostico": None,
            "ruta_archivo": temp_path_16k
        }
    texto = transcribir_audio(temp_path_16k)
    # Filtro de frases irrelevantes
    FRASES_IRRELEVANTES = [
        "Subtítulos realizados por la comunidad de Amara.org",
        "Subtitulado por la comunidad de Amara.org",
        "¡Gracias por ver el vídeo!",
        "No olvides suscribirte al canal",
        "Gracias por ver",
        "Gracias por ver el video",
        "¡Suscríbete y activa notificaciones!"
    ]
    def es_transcripcion_irrelevante(texto):
        t = texto.strip()
        return t in FRASES_IRRELEVANTES or len(t.split()) <= 3
    if es_transcripcion_irrelevante(texto):
        print('[DEBUG] Transcripción irrelevante detectada, se ignora')
        texto = ""
    print(f"[DEBUG] Texto transcrito por Whisper: '{texto}'")
    # os.remove(temp_path)  # No borrar para inspección manual
    # os.remove(temp_path_16k)  # No borrar para inspección manual
    # Usar el texto acumulado si existe para el análisis
    texto_para_analizar = texto_acumulado if texto_acumulado else texto
    resultado = analizar_con_ia(texto_para_analizar) if texto_para_analizar and 'Error' not in texto_para_analizar else None
    return {
        "session_id": session_id,
        "transcripcion": texto,
        "diagnostico": resultado,
        "ruta_archivo": temp_path_16k  # Para referencia
    }

class AnalisisGRPCResponse(BaseModel):
    transcripcion: str = Field(...)
    diagnostico: str = Field(...)
    riesgo: int = Field(...)
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "transcripcion": "Has sido seleccionado para recibir un premio...",
                    "diagnostico": "Estafa. Este tipo de mensajes suelen ser comunes...",
                    "riesgo": 90
                }
            ]
        }
    }

@app.post("/analizar-audio-grpc", response_model=AnalisisGRPCResponse, summary="Analiza audio usando el microservicio gRPC", tags=["Análisis gRPC"])
async def analizar_audio_grpc(
    file: UploadFile = File(..., description="Archivo de audio .wav"),
    session_id: str = Form("rest-session", description="ID de sesión para seguimiento")
):
    """Envía el audio al microservicio gRPC y retorna la transcripción, diagnóstico y riesgo."""
    audio_bytes = await file.read()
    channel = grpc.insecure_channel("localhost:50051")
    stub = fraud_detection_pb2_grpc.FraudDetectionStub(channel)
    def audio_chunks():
        yield fraud_detection_pb2.AudioChunk(data=audio_bytes, session_id=session_id)
    responses = stub.StreamAudio(audio_chunks())
    for response in responses:
        return AnalisisGRPCResponse(
            transcripcion=response.transcripcion,
            diagnostico=response.diagnostico,
            riesgo=response.riesgo
        )

@app.post("/analizar-audio-stream")
def analizar_audio_stream(file: UploadFile = File(...), session_id: str = None, texto_acumulado: str = Form(None)):
    """
    Endpoint para analizar fragmentos de audio en tiempo real.
    Recibe un fragmento de audio (wav), un session_id opcional y el texto acumulado.
    Devuelve la transcripción y el análisis de fraude.
    """
    # Guardar archivo temporalmente, sin importar el nombre
    temp_path = f"temp_stream.wav"
    with open(temp_path, "wb") as f:
        f.write(file.file.read())
    # Validar encabezado RIFF/WAVE
    try:
        with open(temp_path, "rb") as f:
            header = f.read(12)
            if not (header[:4] == b'RIFF' and header[8:12] == b'WAVE'):
                os.remove(temp_path)
                raise HTTPException(status_code=400, detail="El archivo no es un WAV válido.")
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=400, detail="No se pudo leer el archivo de audio.")
    # Convertir a 16kHz mono para máxima compatibilidad
    temp_path_16k = "temp_stream_16k.wav"
    audio = AudioSegment.from_wav(temp_path)
    audio = audio.set_frame_rate(16000).set_channels(1)
    audio.export(temp_path_16k, format="wav")
    # --- Detección de silencio en el backend ---
    min_size_bytes = 2000  # Tamaño mínimo para considerar que hay voz (~0.1 seg)
    min_rms = 10  # Energía mínima (ajustable, ahora más sensible)
    import os
    file_size = os.path.getsize(temp_path_16k)
    rms = audio.rms
    print(f"[DEBUG] Tamaño archivo recibido: {file_size} bytes | RMS: {rms}")
    if file_size < min_size_bytes or rms < min_rms:
        print('[DEBUG] Fragmento ignorado por silencio o archivo vacío (backend)')
        return {
            "session_id": session_id,
            "transcripcion": "",
            "diagnostico": None,
            "ruta_archivo": temp_path_16k
        }
    texto = transcribir_audio(temp_path_16k)
    # Filtro de frases irrelevantes
    FRASES_IRRELEVANTES = [
        "Subtítulos realizados por la comunidad de Amara.org",
        "Subtitulado por la comunidad de Amara.org",
        "¡Gracias por ver el vídeo!",
        "No olvides suscribirte al canal",
        "Gracias por ver",
        "Gracias por ver el video",
        "¡Suscríbete y activa notificaciones!"
    ]
    def es_transcripcion_irrelevante(texto):
        t = texto.strip()
        return t in FRASES_IRRELEVANTES or len(t.split()) <= 3
    if es_transcripcion_irrelevante(texto):
        print('[DEBUG] Transcripción irrelevante detectada, se ignora')
        texto = ""
    print(f"[DEBUG] Texto transcrito por Whisper: '{texto}'")
    # os.remove(temp_path)  # No borrar para inspección manual
    # os.remove(temp_path_16k)  # No borrar para inspección manual
    # Usar el texto acumulado si existe para el análisis
    texto_para_analizar = texto_acumulado if texto_acumulado else texto
    resultado = analizar_con_ia(texto_para_analizar) if texto_para_analizar and 'Error' not in texto_para_analizar else None
    return {
        "session_id": session_id,
        "transcripcion": texto,
        "diagnostico": resultado,
        "ruta_archivo": temp_path_16k  # Para referencia
    }

@app.get("/", response_class=HTMLResponse)
def home():
    with open("frontend/index.html", encoding="utf-8") as f:
        return f.read()
