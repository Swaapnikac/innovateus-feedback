import io
import os
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.transcribe_service import transcribe_audio
from app.services.pii_service import strip_pii
from app.schemas import TranscriptResponse

router = APIRouter()

MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".webm", ".mp3", ".wav", ".ogg", ".m4a", ".mp4", ".mpeg"}
ALLOWED_CONTENT_TYPES = {
    "audio/webm", "audio/mp3", "audio/mpeg", "audio/wav", "audio/ogg",
    "audio/mp4", "audio/x-m4a", "audio/aac", "audio/webm;codecs=opus",
}


@router.post("/transcribe", response_model=TranscriptResponse)
async def transcribe(audio: UploadFile = File(...)):
    # Validate file type
    filename = audio.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    content_type = (audio.content_type or "").split(";")[0].strip()
    if ext not in ALLOWED_EXTENSIONS and content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported file type. Please upload an audio file.")

    # Read with size limit
    chunks = []
    total = 0
    while True:
        chunk = await audio.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_AUDIO_SIZE:
            raise HTTPException(status_code=413, detail="Audio file exceeds 10 MB limit.")
        chunks.append(chunk)

    audio_bytes = b"".join(chunks)
    buffer = io.BytesIO(audio_bytes)
    buffer.name = filename or "audio.webm"

    transcript = await transcribe_audio(buffer)
    transcript = strip_pii(transcript) or ""

    del audio_bytes
    buffer.close()

    return TranscriptResponse(transcript=transcript)
