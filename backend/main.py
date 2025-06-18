import whisper
import asyncio
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import tempfile
from contextlib import asynccontextmanager

# Global variable to hold the Whisper model
model = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the Whisper model on startup
    global model
    print("Loading Whisper model...")
    # Using 'base' model for a balance of speed and accuracy.
    # Other options: 'tiny', 'small', 'medium', 'large'
    # For non-English tasks, you might prefer 'base.en', 'small.en', etc.
    try:
        model = whisper.load_model("medium")
        print("Whisper model loaded successfully.")
    except Exception as e:
        print(f"Error loading Whisper model: {e}")
        # If model loading fails, the app might not be useful. 
        # Consider how to handle this - perhaps by raising an exception to stop startup.
        model = None # Ensure model is None if loading failed
    yield
    # Clean up resources if any (not strictly needed for the model itself here)
    print("Application shutdown.")

app = FastAPI(lifespan=lifespan)

# Configure CORS
origins = [
    "http://localhost:4001",  # Allow your React frontend runs on port 4001
    "http://127.0.0.1:3000",
    # Add other origins if needed
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/transcribe/")
async def transcribe_audio(file: UploadFile = File(...)):
    if model is None:
        raise HTTPException(status_code=503, detail="Whisper model is not available. Please check server logs.")

    if not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload an audio file.")

    try:
        # Create a temporary file to store the uploaded audio
        # Whisper's load_audio can take a file path
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp_audio_file:
            content = await file.read()
            tmp_audio_file.write(content)
            tmp_audio_file_path = tmp_audio_file.name
        
        print(f"Temporary audio file saved at: {tmp_audio_file_path}")

        # Perform transcription
        # For potentially long transcriptions, consider running in a separate thread
        # For now, running it directly for simplicity
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, model.transcribe, tmp_audio_file_path)
        # result = model.transcribe(tmp_audio_file_path)
        transcript_text = result["text"]
        
        print(f"Transcription successful: {transcript_text[:100]}...")
        return {"transcript": transcript_text}

    except Exception as e:
        print(f"Error during transcription: {e}")
        raise HTTPException(status_code=500, detail=f"Error during transcription: {str(e)}")
    finally:
        # Clean up the temporary file
        if 'tmp_audio_file_path' in locals() and os.path.exists(tmp_audio_file_path):
            os.remove(tmp_audio_file_path)
            print(f"Temporary audio file {tmp_audio_file_path} deleted.")

@app.get("/")
async def root():
    return {"message": "Whisper ASR API is running. Use the /transcribe endpoint to process audio."}

# To run the backend (from the 'backend' directory):
# 1. Create a virtual environment: uv venv
# 2. Activate it: source .venv/bin/activate (or .venv\Scripts\activate on Windows)
# 3. Install dependencies: uv pip install -r requirements.txt
# 4. Run Uvicorn: uvicorn main:app --reload
