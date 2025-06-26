import torch
import time
import logging
from datetime import timedelta
import srt

# Configure logging
logger = logging.getLogger(__name__)

# Conditional import for MLX
try:
    import mlx.core as mx
    import mlx_whisper
    from mlx_whisper import load_models
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False

# Conditional import for Hugging Face
try:
    from transformers import pipeline
    HUGGING_FACE_AVAILABLE = True
except ImportError:
    HUGGING_FACE_AVAILABLE = False

class TranscriptionWrapper:
    def __init__(self):
        self.device = self._get_device()
        self.model = self._load_model()
        self.model_name = "mlx-community/whisper-large-v3-turbo"  # Store model name for MLX

    def _get_device(self):
        if MLX_AVAILABLE and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def _load_model(self):
        logger.info(f"Using device: {self.device}")
        if self.device == "mps" and MLX_AVAILABLE:
            try:
                logger.info("Directly use MLX.")
            except Exception as e:
                logger.error(f"Error loading MLX Whisper model: {e}")
                logger.info("Falling back to Hugging Face model...")
                return self._load_hugging_face_model()
        else:
            return self._load_hugging_face_model()

    def _load_hugging_face_model(self):
        if not HUGGING_FACE_AVAILABLE:
            logger.warning("Hugging Face transformers not available.")
            return None

        logger.info("Loading Hugging Face transcription pipeline...")
        torch_dtype = torch.float16 if self.device == "mps" else torch.float32
        model_id = "openai/whisper-large-v3-turbo"
        try:
            transcription_pipeline = pipeline(
                "automatic-speech-recognition",
                model=model_id,
                torch_dtype=torch_dtype,
                device=self.device,
            )
            logger.info(f"Hugging Face pipeline ({model_id}) loaded successfully.")
            return transcription_pipeline
        except Exception as e:
            logger.error(f"Error loading Hugging Face model: {e}")
            return None

    def transcribe(self, audio_path):
        is_mlx = self.device == "mps" and MLX_AVAILABLE
        if self.model is None and not is_mlx:
            raise RuntimeError("Transcription model not loaded.")

        start_time = time.time()
        if self.device == "mps" and MLX_AVAILABLE:
            # Use MLX Whisper with pre-loaded model
            logger.info("Transcribing with MLX Whisper...")
            # Fallback to using model name
            result = mlx_whisper.transcribe(
                audio_path,
                path_or_hf_repo=self.model_name,
                word_timestamps=True
            )
            
            text = result["text"]
            segments = result["segments"]
            srt_transcript = self._format_as_srt_from_segments(segments)
            chunks = segments

        else:
            # Use Hugging Face pipeline
            result = self.model(
                audio_path,
                return_timestamps=True,
                chunk_length_s=30,
            )
            text = result["text"]
            chunks = result.get("chunks", [])
            srt_transcript = self._format_as_srt_from_chunks(chunks)

        end_time = time.time()
        inference_time = end_time - start_time

        return {
            "text": text,
            "srt_transcript": srt_transcript,
            "inference_time": inference_time,
            "chunks": chunks,
        }

    def _format_as_srt_from_chunks(self, chunks):
        srt_content = []
        for i, chunk in enumerate(chunks):
            timestamp = chunk.get("timestamp")
            if not timestamp or len(timestamp) != 2:
                continue

            start_time, end_time = timestamp
            if start_time is None or end_time is None:
                continue

            start_delta = timedelta(seconds=start_time)
            end_delta = timedelta(seconds=end_time)
            text = chunk["text"].strip()

            if text:
                subtitle = srt.Subtitle(
                    index=i + 1, start=start_delta, end=end_delta, content=text
                )
                srt_content.append(subtitle)
        return srt.compose(srt_content)

    def _format_as_srt_from_segments(self, segments):
        srt_content = []
        for i, segment in enumerate(segments):
            start_time = segment["start"]
            end_time = segment["end"]
            text = segment["text"].strip()
            start_delta = timedelta(seconds=start_time)
            end_delta = timedelta(seconds=end_time)
            if text:
                subtitle = srt.Subtitle(index=i + 1, start=start_delta, end=end_delta, content=text)
                srt_content.append(subtitle)
        return srt.compose(srt_content)