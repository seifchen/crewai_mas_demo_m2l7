"""公众号文章生成报告 API。

POST /api/v1/mp/articles/generate
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_request_id, require_api_key
from app.observability.logging import get_logger
from app.schemas.common import ApiResponse
from app.schemas.mp_generate import MpGenerateReportResponse, MpGenerateRequest
from app.services.mp_generate_service import generate_mp_article_report


router = APIRouter()
logger = get_logger(__name__)


@router.post(
    "/articles/generate",
    response_model=ApiResponse[MpGenerateReportResponse],
    summary="生成公众号原创文章",
    description=(
        "通过 JSON 提交选题与创作诉求，由多 Agent 协同完成选题调研、内容策略、"
        "正文创作与标题排版优化，最终返回结构化的公众号原创文章报告。\n\n"
        "**与「文章改写」的区别：** 本接口无需提供原文，仅需给出选题 `topic`，"
        "可选提供 `key_points`（关键要点，将并行调研）、`target_audience`（目标读者）、"
        "`target_style`（文风）与 `word_count_requirement`（字数要求）。"
    ),
    status_code=status.HTTP_200_OK,
)
async def create_mp_generate_report(
    payload: MpGenerateRequest,
    request_id: str = Depends(get_request_id),
    _api_key: str = Depends(require_api_key),
) -> ApiResponse[MpGenerateReportResponse]:
    """生成公众号原创文章报告。"""
    try:
        final_report, error = await generate_mp_article_report(
            topic=payload.topic,
            writing_intent=payload.writing_intent,
            key_points=payload.key_points,
            target_audience=payload.target_audience,
            target_style=payload.target_style,
            word_count_requirement=payload.word_count_requirement,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("mp_generate_api_failed", error=str(exc), request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"公众号文章生成异常: {exc}",
        ) from exc

    if error or final_report is None:
        return ApiResponse(
            code=1,
            message=f"公众号文章生成失败: {error}",
            data=None,
            request_id=request_id,
        )

    response_payload = MpGenerateReportResponse(report=final_report)
    return ApiResponse(
        code=0,
        message="ok",
        data=response_payload,
        request_id=request_id,
    )
