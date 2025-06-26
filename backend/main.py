import asyncio
import logging
import os
import tempfile
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import ffmpeg
from transcription_wrapper import TranscriptionWrapper, MLX_AVAILABLE

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variable to hold the transcription wrapper
transcription_wrapper = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the transcription pipeline on startup
    global transcription_wrapper
    logger.info("Initializing Transcription Wrapper...")
    transcription_wrapper = TranscriptionWrapper()
    yield
    # Clean up resources if any
    logger.info("Application shutdown.")


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


@app.post("/transcribe/")
async def transcribe_audio(
    file: UploadFile = File(...), audio_duration_hint: float = None
):
    if transcription_wrapper is None:
        raise HTTPException(
            status_code=503,
            detail="Transcription service is not available. Please check server logs.",
        )
    
    # For MLX inference, we don't need a pre-loaded model
    if transcription_wrapper.device != "mps" and transcription_wrapper.model is None:
        raise HTTPException(
            status_code=503,
            detail="Transcription service is not available. Please check server logs.",
        )

    if not file.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=400, detail="Invalid file type. Please upload an audio file."
        )

    tmp_audio_file_path = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(file.filename)[1]
        ) as tmp_audio_file:
            content = await file.read()
            tmp_audio_file.write(content)
            tmp_audio_file_path = tmp_audio_file.name

        audio_duration = (
            audio_duration_hint
            if audio_duration_hint and audio_duration_hint > 0
            else get_audio_duration(tmp_audio_file_path)
        )

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: transcription_wrapper.transcribe(tmp_audio_file_path),
        )

        inference_time = result["inference_time"]
        full_text = result["text"]
        srt_transcript = result["srt_transcript"]

        real_time_factor = (
            inference_time / audio_duration if audio_duration > 0 else 0
        )

        benchmark = {
            "audio_duration_seconds": round(audio_duration, 2) if audio_duration > 0 else "unknown",
            "inference_time_seconds": round(inference_time, 2),
            "real_time_factor": round(real_time_factor, 2) if real_time_factor > 0 else "unknown",
            "device": transcription_wrapper.device,
            "model": "Whisper-large-v3-turbo"
        }

        logger.info(f"Transcription completed: {len(full_text)} characters, "
                    f"{len(srt_transcript)} SRT characters, "
                    f"Inference time: {inference_time:.2f} seconds, "
                    f"Real-time factor: {real_time_factor:.2f}, "
                    f"Audio duration: {audio_duration:.2f} seconds")

        return {
            "transcript": full_text,
            "srt_transcript": srt_transcript,
            "benchmark": benchmark,
        }

    except Exception as e:
        logger.error(f"Error during transcription: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error during transcription: {str(e)}"
        )
    finally:
        if tmp_audio_file_path and os.path.exists(tmp_audio_file_path):
            os.remove(tmp_audio_file_path)


@app.get("/")
async def root():
    device_info = {
        "device": transcription_wrapper.device if transcription_wrapper else "unknown",
        "mlx_available": MLX_AVAILABLE,
        "hugging_face_available": transcription_wrapper.model is not None if transcription_wrapper else False,
    }
    return {
        "message": "Whisper ASR API with SRT support and benchmarking is running. Use the /transcribe endpoint to process audio.",
        "device_info": device_info,
    }

if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Whisper ASR API server...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
