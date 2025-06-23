import torch
from transformers import pipeline
import asyncio
import os
import tempfile
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import srt
from datetime import timedelta
import ffmpeg

# Global variable to hold the transcription pipeline
transcription_pipeline = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the transcription pipeline on startup
    global transcription_pipeline
    print("Loading Hugging Face transcription pipeline...")

    # Detect device (prioritize MPS for Apple Silicon)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    torch_dtype = torch.float16 if device == "mps" else torch.float32
    print(f"Using device: {device} with dtype: {torch_dtype}")

    try:
        # Use Whisper turbo model via transformers
        # The correct model ID for turbo in transformers is "openai/whisper-large-v3-turbo"
        model_id = "openai/whisper-large-v3-turbo"

        transcription_pipeline = pipeline(
            "automatic-speech-recognition",
            model=model_id,
            torch_dtype=torch_dtype,
            device=device,
        )
        print(f"Transcription pipeline ({model_id}) loaded successfully.")
    except Exception as e:
        print(f"Error loading transcription pipeline: {e}")
        # If model loading fails, try fallback to base model
        try:
            print("Attempting fallback to base model...")
            model_id = "openai/whisper-base"
            transcription_pipeline = pipeline(
                "automatic-speech-recognition",
                model=model_id,
                torch_dtype=torch_dtype,
                device=device,
            )
            print(f"Fallback transcription pipeline ({model_id}) loaded successfully.")
        except Exception as fallback_e:
            print(f"Error loading fallback model: {fallback_e}")
            transcription_pipeline = None

    yield
    # Clean up resources if any
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


def get_audio_duration(file_path: str) -> float:
    """Get audio duration in seconds using multiple methods"""
    # Method 1: Try ffmpeg probe with detailed debugging
    try:
        probe = ffmpeg.probe(file_path)
        print(f"Debug: ffmpeg probe keys: {list(probe.keys())}")

        # Try format duration first
        if "format" in probe and "duration" in probe["format"]:
            duration = float(probe["format"]["duration"])
            print(f"Found duration in format: {duration:.2f}s")
            return duration

        # Try streams duration
        if "streams" in probe:
            print(f"Debug: Found {len(probe['streams'])} streams")
            for i, stream in enumerate(probe["streams"]):
                print(f"Debug: Stream {i} keys: {list(stream.keys())}")
                if "duration" in stream:
                    duration = float(stream["duration"])
                    print(f"Found duration in stream {i}: {duration:.2f}s")
                    return duration

        # Try to calculate from bitrate and size
        if "format" in probe:
            format_data = probe["format"]
            print(f"Debug: Format keys: {list(format_data.keys())}")
            if "size" in format_data and "bit_rate" in format_data:
                size_bytes = int(format_data["size"])
                bitrate = int(format_data["bit_rate"])
                if bitrate > 0:
                    duration = (size_bytes * 8) / bitrate
                    print(f"Calculated duration from bitrate: {duration:.2f}s")
                    return duration

        print("Could not find duration in any probe data")

    except Exception as e:
        print(f"Error with ffmpeg probe: {e}")

    # Method 2: Try using ffmpeg duration command directly
    try:
        result = (
            os.popen(
                f'ffprobe -v quiet -show_entries format=duration -of csv="p=0" "{file_path}"'
            )
            .read()
            .strip()
        )
        if result and result != "N/A":
            duration = float(result)
            print(f"Found duration using ffprobe command: {duration:.2f}s")
            return duration
    except Exception as e:
        print(f"Error with ffprobe command: {e}")

    # Method 3: Try estimating from file size (very rough)
    try:
        file_size = os.path.getsize(file_path)
        # For compressed audio, estimate based on typical compression ratios
        # WebM/OGG typically compress to about 64-128kbps
        estimated_duration = (file_size * 8) / (96 * 1024)  # Assume 96kbps average
        print(
            f"Fallback estimate from file size ({file_size} bytes): {estimated_duration:.2f}s"
        )
        return estimated_duration
    except Exception as e:
        print(f"Fallback estimation failed: {e}")
        return 0.0


def format_as_srt(chunks):
    """Convert pipeline chunks to SRT format string"""
    srt_content = []
    for i, chunk in enumerate(chunks):
        timestamp = chunk.get("timestamp")
        if not timestamp or len(timestamp) != 2:
            continue

        start_time, end_time = timestamp
        # Ensure timestamps exist and are valid
        if start_time is None or end_time is None:
            continue

        start_delta = timedelta(seconds=start_time)
        end_delta = timedelta(seconds=end_time)
        text = chunk["text"].strip()

        if text:  # Only add non-empty text
            subtitle = srt.Subtitle(
                index=i + 1, start=start_delta, end=end_delta, content=text
            )
            srt_content.append(subtitle)

    return srt.compose(srt_content)


@app.post("/transcribe/")
async def transcribe_audio(
    file: UploadFile = File(...), audio_duration_hint: float = None
):
    if transcription_pipeline is None:
        raise HTTPException(
            status_code=503,
            detail="Transcription pipeline is not available. Please check server logs.",
        )

    if not file.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=400, detail="Invalid file type. Please upload an audio file."
        )

    tmp_audio_file_path = None
    try:
        # Create a temporary file to store the uploaded audio
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(file.filename)[1]
        ) as tmp_audio_file:
            content = await file.read()
            tmp_audio_file.write(content)
            tmp_audio_file_path = tmp_audio_file.name

        print(f"Temporary audio file saved at: {tmp_audio_file_path}")

        # Get audio duration for benchmark
        if audio_duration_hint is not None and audio_duration_hint > 0:
            audio_duration = audio_duration_hint
            print(f"Using provided audio duration hint: {audio_duration:.2f} seconds")
        else:
            audio_duration = get_audio_duration(tmp_audio_file_path)
            print(f"Detected audio duration: {audio_duration:.2f} seconds")

        # Start timing the inference
        inference_start_time = time.time()

        # Perform transcription with timestamps
        # Run in executor to avoid blocking the main thread
        loop = asyncio.get_event_loop()

        result = await loop.run_in_executor(
            None,
            lambda: transcription_pipeline(
                tmp_audio_file_path,
                return_timestamps=True,
                chunk_length_s=30,  # Process in 30-second chunks for better memory usage
            ),
        )

        # End timing
        inference_end_time = time.time()
        inference_time = inference_end_time - inference_start_time

        full_text = result["text"]
        chunks = result.get("chunks", [])

        # Generate SRT format subtitles
        srt_transcript = format_as_srt(chunks) if chunks else ""

        # Calculate performance metrics
        real_time_factor = (
            inference_time / audio_duration
            if inference_time > 0 and audio_duration > 0
            else 0
        )
        # Keep speed_factor same as real_time_factor for consistency
        speed_factor = real_time_factor

        # Create benchmark data
        benchmark = {
            "audio_duration_seconds": (
                round(audio_duration, 2) if audio_duration > 0 else "unknown"
            ),
            "inference_time_seconds": round(inference_time, 2),
            "real_time_factor": (
                round(real_time_factor, 2) if real_time_factor > 0 else "unknown"
            ),  # <1 means faster than real-time (e.g., 0.5 = 2x speed)
            "speed_factor": (
                round(speed_factor, 2) if speed_factor > 0 else "unknown"
            ),  # <1 means faster than real-time (same as real_time_factor)
            "device": "mps" if torch.backends.mps.is_available() else "cpu",
            "model": "openai/whisper-large-v3-turbo",
        }

        if audio_duration > 0:
            print(
                f"Transcription completed in {inference_time:.2f}s for {audio_duration:.2f}s audio"
            )
            if real_time_factor < 1:
                speed_description = f"{1/real_time_factor:.1f}x faster than real-time"
            elif real_time_factor > 1:
                speed_description = f"{real_time_factor:.1f}x slower than real-time"
            else:
                speed_description = "exactly real-time speed"
            print(f"Speed factor: {real_time_factor:.2f} ({speed_description})")
        else:
            print(
                f"Transcription completed in {inference_time:.2f}s (audio duration unknown)"
            )
        print(f"Transcript preview: {full_text[:100]}...")

        return {
            "transcript": full_text,
            "srt_transcript": srt_transcript,
            "benchmark": benchmark,
        }

    except Exception as e:
        print(f"Error during transcription: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error during transcription: {str(e)}"
        )
    finally:
        # Clean up the temporary file
        if tmp_audio_file_path and os.path.exists(tmp_audio_file_path):
            os.remove(tmp_audio_file_path)
            print(f"Temporary audio file {tmp_audio_file_path} deleted.")


@app.get("/")
async def root():
    device_info = {
        "device": "mps" if torch.backends.mps.is_available() else "cpu",
        "mps_available": torch.backends.mps.is_available(),
        "cuda_available": torch.cuda.is_available(),
    }
    return {
        "message": "Whisper ASR API with SRT support and benchmarking is running. Use the /transcribe endpoint to process audio.",
        "device_info": device_info,
    }


# To run the backend (from the 'backend' directory):
# 1. Create a virtual environment: uv venv
# 2. Activate it: source .venv/bin/activate (or .venv\Scripts\activate on Windows)
# 3. Install dependencies: uv pip install -r requirements.txt
# 4. Run Uvicorn: uvicorn main:app --reload

# This block will execute when running this file directly with 'python main.py'
if __name__ == "__main__":
    import uvicorn

    print("Starting Whisper ASR API server with SRT support and benchmarking...")
    # Run the server with uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
    # The reload=True option is useful during development as it auto-reloads the server when code changes
