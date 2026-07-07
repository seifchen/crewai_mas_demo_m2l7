"""公众号文章改写报告 API。

POST /api/v1/mp/articles/rewrite
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_request_id, require_api_key
from app.observability.logging import get_logger
from app.schemas.common import ApiResponse
from app.schemas.mp_rewrite import MpRewriteReportResponse, MpRewriteRequest
from app.services.mp_rewrite_service import generate_mp_rewrite_report


router = APIRouter()
logger = get_logger(__name__)


@router.post(
    "/articles/rewrite",
    response_model=ApiResponse[MpRewriteReportResponse],
    summary="生成公众号文章改写报告",
    description=(
        "通过 JSON 提交改写诉求与一篇或多篇原文，"
        "由多 Agent 协同完成原文内容分析、改写策略、正文改写与标题排版优化，"
        "最终返回结构化的公众号文章改写报告。\n\n"
        "**原文两种传入方式（二选一，节省 token 推荐第二种）：**\n"
        "1. `content`：直接把原文正文塞进 JSON body；\n"
        "2. `content_path`：仅传服务端本地文件路径（如 `.txt` / `.md`），"
        "服务端读取文件内容作为原文，客户端无需在请求体中传输大段文本。"
    ),
    status_code=status.HTTP_200_OK,
)
async def create_mp_rewrite_report(
    payload: MpRewriteRequest,
    request_id: str = Depends(get_request_id),
    _api_key: str = Depends(require_api_key),
) -> ApiResponse[MpRewriteReportResponse]:
    """生成公众号文章改写报告。"""
    try:
        final_report, error = await generate_mp_rewrite_report(
            rewrite_intent=payload.rewrite_intent,
            source_articles=payload.source_articles,
            target_style=payload.target_style,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("mp_rewrite_api_failed", error=str(exc), request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"公众号文章改写异常: {exc}",
        ) from exc

    if error or final_report is None:
        return ApiResponse(
            code=1,
            message=f"公众号文章改写失败: {error}",
            data=None,
            request_id=request_id,
        )

    response_payload = MpRewriteReportResponse(report=final_report)
    return ApiResponse(
        code=0,
        message="ok",
        data=response_payload,
        request_id=request_id,
    )
