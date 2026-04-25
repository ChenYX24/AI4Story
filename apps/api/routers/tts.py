import base64

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from ..config import XIAOMI_TTS_FORMAT
from ..models import TTSBatchRequest, TTSBatchResponse, TTSBatchResponseItem
from ..services.tts_service import TTSError, media_type, synthesize_batch, synthesize_bytes

router = APIRouter()


@router.get("/tts")
def tts(
    text: str = Query(..., min_length=1),
    voice: str | None = Query(default=None),
    tone: str | None = Query(default=None),
    speaker: str | None = Query(default=None),
    story_id: str | None = Query(default=None),
    speaker_gender: str | None = Query(default=None),
) -> Response:
    if not text.strip():
        raise HTTPException(status_code=400, detail="empty text")
    try:
        audio = synthesize_bytes(
            text=text, voice=voice, tone=tone, speaker=speaker,
            story_id=story_id, speaker_gender=speaker_gender,
        )
    except TTSError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return Response(
        content=audio,
        media_type=media_type(),
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.post("/tts/batch", response_model=TTSBatchResponse)
def tts_batch(req: TTSBatchRequest):
    if len(req.items) > 20:
        raise HTTPException(status_code=400, detail="max 20 items per batch")
    if not req.items:
        raise HTTPException(status_code=400, detail="items list is empty")

    raw_items = [item.model_dump() for item in req.items]
    try:
        audio_list = synthesize_batch(raw_items, story_id=req.story_id)
    except TTSError as e:
        raise HTTPException(status_code=502, detail=str(e))

    fmt = XIAOMI_TTS_FORMAT.lower()
    response_items = [
        TTSBatchResponseItem(
            index=i,
            audio_b64=base64.b64encode(audio).decode(),
            format=fmt,
        )
        for i, audio in enumerate(audio_list)
    ]
    return TTSBatchResponse(items=response_items)
