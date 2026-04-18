from fastapi import APIRouter, HTTPException

from ..config import DASHSCOPE_API_KEY
from ..models import ReportRequest, ReportResponse
from ..services.report_service import build_report

router = APIRouter()


@router.post("/report", response_model=ReportResponse)
def report(req: ReportRequest) -> ReportResponse:
    if not DASHSCOPE_API_KEY:
        raise HTTPException(status_code=424, detail="服务器未配置 DASHSCOPE_API_KEY")
    try:
        payload = build_report(req)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return ReportResponse(**payload)
