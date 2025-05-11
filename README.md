# FraudWatch AI Service

Este proyecto es un sistema de detección de fraude que utiliza FastAPI para el backend, gRPC para la comunicación entre microservicios y una interfaz web para la interacción del usuario. Incluye funcionalidades para procesar audio, detectar fraude con modelos de IA y comunicarse con servicios externos.

## Tabla de Contenidos
- [Descripción General](#descripción-general)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Componentes Principales](#componentes-principales)
- [Instalación](#instalación)
- [Uso](#uso)
- [Testing](#testing)
- [Despliegue en Railway](#despliegue-en-railway)
- [Solución de Problemas](#solución-de-problemas)
- [Licencia](#licencia)

## Descripción General
El sistema permite cargar archivos de audio, procesarlos y detectar posibles fraudes utilizando modelos de OpenAI (Whisper para transcripción y GPT para análisis). La comunicación entre servicios se realiza mediante gRPC y la interfaz web permite a los usuarios interactuar de manera sencilla.

Funcionalidades principales:
- Transcripción de audio a texto usando modelos de IA
- Análisis de posibles estafas en texto con formato estructurado
- Comunicación en tiempo real entre componentes mediante gRPC
- Interfaz web para grabar audio y visualizar resultados

## Estructura del Proyecto
```
detector-fraude/
├── app/
│   ├── __init__.py
│   ├── main.py                # Servidor FastAPI principal
│   ├── grpc_server.py         # Servidor gRPC
│   ├── grpc_client.py         # Cliente gRPC
│   ├── utils/
│   │   └── __init__.py
│   └── proto/
│       ├── __init__.py
│       ├── fraud_detection.proto   # Definición del servicio gRPC
│       ├── fraud_detection_pb2.py   # Generado automáticamente
│       └── fraud_detection_pb2_grpc.py # Generado automáticamente
├── frontend/
│   ├── index.html              # Interfaz de usuario
│   └── recorder.js             # Grabación de audio
├── tests/
│   └── test_main.py            # Tests de la API
├── .env                      # Variables de entorno (no incluido)
├── .gitignore
├── LICENSE
├── Procfile                  # Configuración para Railway
├── README.md
└── requirements.txt         # Dependencias del proyecto
```

## Componentes Principales

### Backend FastAPI (app/main.py)
El servidor FastAPI implementa los siguientes endpoints:

- **GET /** - Página principal (frontend)
- **POST /register** - Registro de usuario
- **POST /login** - Login de usuario (devuelve JWT)
- **POST /analizar-texto** - Analiza un texto para detectar fraudes (requiere JWT)
- **POST /analisis** - Guarda un análisis asociado al usuario (requiere JWT)
- **DELETE /analisis/{analisis_id}** - Elimina un análisis del usuario (requiere JWT)
- **POST /transcribir-audio** - Transcribe un archivo de audio a texto
- **POST /analizar-audio-grpc** - Envía audio al servicio gRPC y devuelve análisis
- **POST /analizar-audio-stream** - Procesa fragmentos de audio en tiempo real

### Servicio gRPC (app/grpc_server.py y proto/)
Implementa un servicio bidireccional que permite:

- Enviar fragmentos de audio desde el cliente al servidor
- Recibir resultados de transcripción y análisis de fraude
- Streaming en tiempo real para análisis de audio

Definición en Protocol Buffers (proto):
```protobuf
service FraudDetection {
  rpc StreamAudio (stream AudioChunk) returns (stream TranscriptionResult);
}

message AudioChunk {
  bytes data = 1;           // Fragmento de audio en binario
  string session_id = 2;    // ID de sesión
}

message TranscriptionResult {
  string transcripcion = 1;
  string diagnostico = 2;
  int32 riesgo = 3;         // Porcentaje de riesgo
}
```

### Análisis de Fraude con IA
Utiliza modelos de OpenAI para:

1. **Transcripción de audio**: Usa el modelo Whisper para convertir audio a texto
2. **Análisis de fraude**: Usa GPT para evaluar si un texto es potencialmente fraudulento

El análisis devuelve una respuesta estructurada con:
- **Diagnóstico**: "Estafa" o "No Estafa"
- **Explicación**: Razones detalladas del diagnóstico
- **Riesgo**: Puntuación de 0 a 100

## Instalación
1. Clona el repositorio:
   ```bash
   git clone https://github.com/JhordanARV/fraudwatch-ai-service.git
   cd fraudwatch-ai-service
   ```
2. Crea un entorno virtual e instala dependencias:
   ```bash
   python -m venv venv
   # En Windows:
   venv\Scripts\activate
   # En Linux/Mac:
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. (Opcional) Configura las variables de entorno en `.env`.

## Uso
### 1. Ejecutar el servidor gRPC
```bash
python app/grpc_server.py
```

### 2. Ejecutar el servidor FastAPI
```bash
uvicorn app.main:app --reload
```

### 3. Registro y login de usuario (ejemplo con curl)
```bash
# Registro
curl -X POST http://localhost:8000/register -H "Content-Type: application/json" -d '{"username":"usuario1","email":"usuario1@ejemplo.com","password":"clave123"}'

# Login
curl -X POST http://localhost:8000/login -d "username=usuario1&password=clave123" -H "Content-Type: application/x-www-form-urlencoded"
# Obtendrás un access_token que debes usar como Bearer en endpoints protegidos
```

### 4. Acceder a la Interfaz Web
Abre `frontend/index.html` en tu navegador o configura el backend para servir archivos estáticos.

---

## Documentación Interactiva de la API

La API genera automáticamente documentación Swagger (OpenAPI) a través de FastAPI. Puedes explorar todos los endpoints, ver los modelos de entrada/salida y probar la API desde tu navegador en:

- [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI)
- [http://localhost:8000/redoc](http://localhost:8000/redoc) (ReDoc)

Se recomienda revisar esta documentación para entender rápidamente cómo usar el servicio y probar los endpoints de manera interactiva.

## Testing
Asegúrate de tener instalado `pytest` (ya incluido en requirements.txt):

```bash
pip install -r requirements.txt
pytest
```
Esto ejecutará los tests ubicados en la carpeta `tests/`.

**Nota importante:** Algunos endpoints requieren autenticación JWT. Los tests incluyen registro y login automático para obtener el token y probar los endpoints protegidos. Si cambias la lógica de autenticación, actualiza los tests.

Puedes agregar más archivos de test siguiendo el patrón `test_*.py`.

## Despliegue en Railway
1. Sube tu proyecto a GitHub.
2. En Railway, crea un nuevo proyecto y selecciona tu repositorio.
3. Railway detectará el archivo `Procfile` y ejecutará:
   - El backend FastAPI con: `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - El servidor gRPC con: `grpc: python app/grpc_server.py`
4. Añade tus variables de entorno en el panel de Railway.
5. El frontend puede ser servido desde FastAPI o desde otro servicio estático.

## Solución de Problemas

### Errores comunes

1. **Error "No module named 'app'"**
   - **Problema**: Al ejecutar el servidor gRPC, puede aparecer un error de importación.
   - **Solución**: El proyecto está estructurado como un paquete. Ejecuta los scripts desde la raíz del proyecto:
     ```bash
     python -m app.grpc_server
     ```

2. **Error de conexión con el servidor gRPC**
   - **Problema**: El cliente no puede conectarse al servidor gRPC.
   - **Solución**: Asegúrate de que el servidor gRPC esté ejecutándose en el puerto 50051.

3. **No se genera la respuesta esperada del análisis de fraude**
   - **Problema**: El formato del diagnóstico no es el esperado.
   - **Solución**: El sistema analiza el texto con IA y extrae información estructurada. Si la respuesta no es clara, intenta con un mensaje más largo o claro.

### Variables de Entorno

Crea un archivo `.env` en la raíz del proyecto con las siguientes variables:

```
OPENAI_API_KEY=tu_clave_de_api_aqui
GRPC_SERVER_URL=localhost:50051
DATABASE_URL=postgresql+asyncpg://usuario:contraseña@host:puerto/db
SECRET_KEY=alguna_clave_segura
```

Puedes obtener tu clave de API en [OpenAI Platform](https://platform.openai.com/api-keys).

## Licencia
Este proyecto está licenciado bajo los términos de la licencia MIT. Consulta el archivo [LICENSE](LICENSE) para más detalles.

---

### Notas
- Los archivos `fraud_detection_pb2.py` y `fraud_detection_pb2_grpc.py` son generados automáticamente por `protoc` a partir de `fraud_detection.proto`.
- Los archivos temporales de audio (`temp_*.wav`) están excluidos del repositorio mediante `.gitignore`.
- La carpeta `venv` y archivos de caché también están excluidos.
- Para regenerar los archivos de Protocol Buffers, instala `grpcio-tools` y ejecuta:
  ```bash
  python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. app/proto/fraud_detection.proto
  ```

---

¿Tienes dudas o sugerencias? ¡Crea un issue o pull request en el repositorio!
