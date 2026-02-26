import io
import logging
from openai import AsyncOpenAI
from app.config import get_settings

logger = logging.getLogger(__name__)


async def transcribe_audio(audio_buffer: io.BytesIO) -> str:
    settings = get_settings()

    if not settings.openai_api_key or settings.openai_api_key == "sk-your-key-here":
        audio_buffer.close()
        raise ValueError("OpenAI API key not configured")

    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)

        response = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_buffer,
            response_format="text",
        )

        audio_buffer.close()
        return response.strip() if isinstance(response, str) else response.text.strip()
    except Exception as e:
        audio_buffer.close()
        logger.error(f"Transcription failed: {e}")
        raise
