from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Depends, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import List
import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from app.database import get_db
from app import models, schemas

import grpc
import app.proto.fraud_detection_pb2 as fraud_detection_pb2
import app.proto.fraud_detection_pb2_grpc as fraud_detection_pb2_grpc
import speech_recognition as sr
from openai import OpenAI
from pydub import AudioSegment

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

# --- Seguridad y JWT ---
SECRET_KEY = os.getenv("SECRET_KEY", "cambia_esto_en_produccion")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

# Utilidades de autenticación

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

async def authenticate_user(db: AsyncSession, username: str, password: str):
    result = await db.execute(select(models.Usuario).where(models.Usuario.username == username))
    user = result.scalars().first()
    if user and verify_password(password, user.hashed_password):
        return user
    return None

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No autorizado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    result = await db.execute(select(models.Usuario).where(models.Usuario.username == username))
    user = result.scalars().first()
    if user is None:
        raise credentials_exception
    return user

# --- Endpoints de autenticación ---

@app.post("/register", response_model=schemas.UsuarioOut)
async def register(user_in: schemas.UsuarioCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Usuario).where((models.Usuario.username == user_in.username) | (models.Usuario.email == user_in.email)))
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(status_code=400, detail="El usuario o email ya existe")
    hashed_pw = get_password_hash(user_in.password)
    user = models.Usuario(username=user_in.username, email=user_in.email, hashed_password=hashed_pw)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@app.post("/login", response_model=schemas.Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Credenciales incorrectas")
    access_token = create_access_token(data={"sub": user.username}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": access_token, "token_type": "bearer"}

# --- Endpoints de análisis asociados al usuario ---

@app.post("/analisis", response_model=schemas.AnalisisOut)
async def crear_analisis(analisis_in: schemas.AnalisisCreate, db: AsyncSession = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    analisis = models.Analisis(
        usuario_id=current_user.id,
        texto_analizado=analisis_in.texto_analizado,
        resultado=analisis_in.resultado,
        session_id=analisis_in.session_id
    )
    db.add(analisis)
    await db.commit()
    await db.refresh(analisis)
    return analisis

import logging

@app.get("/analisis", response_model=List[schemas.AnalisisOut])
async def obtener_analisis(db: AsyncSession = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    try:
        result = await db.execute(
            select(models.Analisis)
            .where(models.Analisis.usuario_id == current_user.id)
            .order_by(models.Analisis.fecha.desc())
        )
        analisis = result.scalars().all()
        return analisis
    except Exception as e:
        logging.exception("Error al obtener el historial de análisis")
        # Opcional: puedes devolver el error para depuración
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

# --- FIN autenticación y endpoints de análisis ---

# --- Endpoint para eliminar análisis ---
from fastapi import Path

@app.delete("/analisis/{analisis_id}", status_code=204, tags=["Análisis"], dependencies=[Depends(oauth2_scheme)])
async def eliminar_analisis(analisis_id: int = Path(..., gt=0), db: AsyncSession = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    from app.models import Analisis
    result = await db.execute(select(Analisis).where(Analisis.id == analisis_id, Analisis.usuario_id == current_user.id))
    analisis = result.scalars().first()
    if not analisis:
        raise HTTPException(status_code=404, detail="Análisis no encontrado o no autorizado")
    await db.delete(analisis)
    await db.commit()
    return None


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

# Puedes modificar esta función para guardar automáticamente cada análisis en la base de datos si lo deseas

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
            model="gpt-4o-mini",
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
        from_attributes = True
        json_schema_extra = {
            "example": {
                "resultado": "Diagnóstico: Estafa\n\nExplicación: Este mensaje solicita datos personales...\n\nRiesgo: 90/100"
            }
        }

class TranscripcionResponse(BaseModel):
    transcripcion: str
    class Config:
        from_attributes = True
        json_schema_extra = {
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
        from_attributes = True
        json_schema_extra = {
            "example": {
                "session_id": "session-123",
                "transcripcion": "Has sido seleccionado para recibir un premio...",
                "diagnostico": "Diagnóstico: Estafa\n\nExplicación: Este mensaje solicita datos personales...\n\nRiesgo: 90/100",
                "ruta_archivo": "temp_stream_16k.wav"
            }
        }

@app.post("/analizar-texto", response_model=AnalisisTextoResponse, tags=["Análisis"])
async def endpoint_analizar_texto(payload: dict, db: AsyncSession = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    texto = payload.get("texto", "")
    session_id = payload.get("session_id")
    origen = payload.get("origen", "manual")  # Por defecto 'manual' si no viene
    if not texto:
        raise HTTPException(status_code=400, detail="Texto vacío")
    resultado = analizar_con_ia(texto)
    # Guardar en base de datos
    from app.models import Analisis
    analisis = Analisis(
        usuario_id=current_user.id,
        texto_analizado=texto,
        resultado=resultado,
        session_id=session_id,
        origen=origen
    )
    db.add(analisis)
    await db.commit()
    await db.refresh(analisis)
    return {"resultado": resultado}

@app.post("/transcribir-audio", response_model=TranscripcionResponse, tags=["Transcripción"], dependencies=[Depends(oauth2_scheme)])
async def endpoint_transcribir_audio(file: UploadFile = File(...), current_user: models.Usuario = Depends(get_current_user)):
    """
    Transcribe un archivo de audio usando OpenAI Whisper.
    """
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name
    transcripcion = transcribir_audio(tmp_path)
    return {"transcripcion": transcripcion}

@app.post("/analizar-audio-stream", response_model=AnalisisAudioStreamResponse, tags=["Análisis"])
async def analizar_audio_stream(file: UploadFile = File(...), session_id: str = None, texto_acumulado: str = Form(None), origen: str = Form("audio_stream"), db: AsyncSession = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
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
    # Guardar en base de datos
    from app.models import Analisis
    analisis = Analisis(
        usuario_id=current_user.id,
        texto_analizado=texto_para_analizar,
        resultado=resultado,
        session_id=session_id,
        origen=origen
    )
    db.add(analisis)
    await db.commit()
    await db.refresh(analisis)
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
    import os
    GRPC_SERVER_URL = os.getenv("GRPC_SERVER_URL", "localhost:50051")
    channel = grpc.insecure_channel(GRPC_SERVER_URL)
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

@app.post("/analizar-audio-stream", response_model=AnalisisAudioStreamResponse, tags=["Análisis"])
async def analizar_audio_stream(file: UploadFile = File(...), session_id: str = None, texto_acumulado: str = Form(None), origen: str = Form("audio_stream"), db: AsyncSession = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
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
    # Guardar en base de datos
    from app.models import Analisis
    analisis = Analisis(
        usuario_id=current_user.id,
        texto_analizado=texto_para_analizar,
        resultado=resultado,
        session_id=session_id,
        origen=origen
    )
    db.add(analisis)
    await db.commit()
    await db.refresh(analisis)
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
