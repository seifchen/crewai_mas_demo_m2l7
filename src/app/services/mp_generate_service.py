"""公众号文章生成项目的领域服务。

负责：
- 校验并组装领域请求模型 MpGenerateRequest；
- 调用 Crew Flow 执行多 Agent 编排；
- 返回最终的文章生成报告字符串。

与公众号改写服务不同，本项目是「从选题从零创作」，无需读取原文文件，
因此服务层主要负责入参校验（选题、要点数量、字数等）与领域模型组装。
"""

from __future__ import annotations

import uuid
from typing import List, Optional, Tuple

from app.core.config import get_settings
from app.crews.mp_generate.flows import run_mp_generate_flow
from app.observability.logging import get_logger
from app.schemas.mp_generate import MpGenerateRequest


logger = get_logger(__name__)


def _normalize_key_points(raw_points: List[str], max_points: int) -> List[str]:
    """规整关键要点列表：去空白、去重、截断到上限。"""
    normalized: List[str] = []
    seen: set[str] = set()
    for p in raw_points or []:
        s = (p or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        normalized.append(s)
        if len(normalized) >= max_points:
            break
    return normalized


async def generate_mp_article_report(
    topic: str,
    writing_intent: str = "",
    key_points: Optional[List[str]] = None,
    target_audience: str = "",
    target_style: str = "",
    word_count_requirement: str = "",
) -> Tuple[Optional[str], str]:
    """对外主入口：执行公众号文章生成流程。

    Returns:
        (final_report, error_message)
    """
    # 1. 基础校验
    if not topic or not topic.strip():
        return None, "选题 topic 不能为空"

    settings = get_settings()

    # 1.1 关键要点数量上限（复用公众号改写的篇数上限配置）
    normalized_points = _normalize_key_points(key_points or [], settings.mp_max_articles)

    # 2. 生成 run_id 便于日志追踪
    run_id = uuid.uuid4().hex[:8]

    logger.info(
        "mp_generate_service_start",
        topic=topic[:100],
        key_point_count=len(normalized_points),
        run_id=run_id,
    )

    try:
        # 3. 组装领域请求模型
        request = MpGenerateRequest(
            topic=topic.strip(),
            writing_intent=(writing_intent or "").strip(),
            key_points=normalized_points,
            target_audience=(target_audience or "").strip(),
            target_style=(target_style or "").strip(),
            word_count_requirement=(word_count_requirement or "").strip(),
        )

        # 4. 调用多 Agent 编排流程
        final_report, error = await run_mp_generate_flow(request)

        if error:
            logger.warning("mp_generate_service_failed", error=error, run_id=run_id)
        else:
            logger.info("mp_generate_service_success", run_id=run_id)
        return final_report, error
    except Exception as exc:  # noqa: BLE001
        logger.exception("mp_generate_service_exception", error=str(exc), run_id=run_id)
        return None, f"服务异常: {str(exc)}"
