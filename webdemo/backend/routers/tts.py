from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from ..services.tts_service import TTSError, media_type, synthesize_bytes

router = APIRouter()


@router.get("/tts")
def tts(
    text: str = Query(..., min_length=1),
    voice: str | None = Query(default=None),
    tone: str | None = Query(default=None),
    speaker: str | None = Query(default=None),
) -> Response:
    if not text.strip():
        raise HTTPException(status_code=400, detail="empty text")
    try:
        audio = synthesize_bytes(text=text, voice=voice, tone=tone, speaker=speaker)
    except TTSError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return Response(
        content=audio,
        media_type=media_type(),
        headers={"Cache-Control": "public, max-age=3600"},
    )
