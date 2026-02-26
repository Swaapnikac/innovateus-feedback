import io
from fastapi import APIRouter, UploadFile, File
from app.services.transcribe_service import transcribe_audio
from app.schemas import TranscriptResponse

router = APIRouter()


@router.post("/transcribe", response_model=TranscriptResponse)
async def transcribe(audio: UploadFile = File(...)):
    audio_bytes = await audio.read()
    buffer = io.BytesIO(audio_bytes)
    buffer.name = audio.filename or "audio.webm"

    transcript = await transcribe_audio(buffer)

    del audio_bytes
    buffer.close()

    return TranscriptResponse(transcript=transcript)
