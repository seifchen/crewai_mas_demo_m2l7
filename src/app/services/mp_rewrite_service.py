"""公众号文章改写项目的领域服务。

负责：
- 校验并组装领域请求模型 MpRewriteRequest；
- 调用 Crew Flow 执行多 Agent 编排；
- 返回最终的改写报告字符串。

与小红书笔记服务不同，公众号改写为纯文本场景，无需图片落盘与压缩，
因此服务层主要负责入参校验、原文规整与领域模型组装。

为节省客户端 → 服务端的传输 token，`MpArticleInput` 支持以本地文件路径
（`content_path`）替代直接传大段 `content` 文本，服务层会读取文件内容
并做安全校验（白名单根目录 / 后缀 / 大小限制）。
"""

from __future__ import annotations

import os
import uuid
from typing import List, Optional, Tuple

from app.core.config import Settings, get_settings
from app.crews.mp_rewrite.flows import run_mp_rewrite_flow
from app.observability.logging import get_logger
from app.schemas.mp_rewrite import MpArticleInput, MpRewriteRequest


logger = get_logger(__name__)


def _read_article_from_path(content_path: str, settings: Settings) -> str:
    """从本地文件读取原文正文，含路径 / 后缀 / 大小安全校验。

    Raises:
        ValueError: 校验不通过或读取失败时抛出，含可回传给用户的错误说明。
    """
    raw_path = (content_path or "").strip()
    if not raw_path:
        raise ValueError("content_path 为空")

    # 解析为绝对路径并规范化，防止 `..` 目录穿越
    abs_path = os.path.realpath(os.path.abspath(os.path.expanduser(raw_path)))

    # 白名单根目录校验
    read_root = (settings.mp_article_read_root or "").strip()
    if read_root:
        allowed_root = os.path.realpath(os.path.abspath(os.path.expanduser(read_root)))
        # commonpath 在跨盘符时会抛异常，这里用 startswith + sep 兜底判断
        try:
            common = os.path.commonpath([abs_path, allowed_root])
        except ValueError:
            common = ""
        if common != allowed_root:
            raise ValueError(
                f"content_path 不在允许的目录白名单内: {raw_path}"
            )

    # 存在性 & 文件类型
    if not os.path.isfile(abs_path):
        raise ValueError(f"content_path 不存在或不是文件: {raw_path}")

    # 后缀白名单
    allowed_suffixes = settings.get_mp_article_allowed_suffixes()
    if allowed_suffixes:
        suffix = os.path.splitext(abs_path)[1].lower()
        if suffix not in allowed_suffixes:
            raise ValueError(
                f"content_path 文件后缀不被允许: {suffix}，允许的后缀: "
                f"{sorted(allowed_suffixes)}"
            )

    # 大小限制
    try:
        size = os.path.getsize(abs_path)
    except OSError as exc:
        raise ValueError(f"读取 content_path 文件大小失败: {exc}") from exc
    if size > settings.mp_article_max_file_bytes:
        raise ValueError(
            f"content_path 文件过大: {size} bytes，"
            f"上限 {settings.mp_article_max_file_bytes} bytes"
        )

    # 读取正文（UTF-8，对无法解码的字节做容错替换而不是直接抛错）
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError as exc:
        raise ValueError(f"读取 content_path 文件失败: {exc}") from exc


def _normalize_articles(
    raw_articles: List[MpArticleInput],
    settings: Settings,
) -> List[MpArticleInput]:
    """规整原文列表：

    - 若提供 `content_path` 则从本地文件读取正文（优先级高于 `content`）；
    - 重新分配唯一 `article_id`；
    - 对超长正文按字符数截断。
    """
    max_chars = settings.mp_max_article_chars
    normalized: List[MpArticleInput] = []
    for idx, art in enumerate(raw_articles):
        # 1) 优先按本地文件路径读取
        if (art.content_path or "").strip():
            try:
                content = _read_article_from_path(art.content_path, settings)
                logger.info(
                    "mp_article_loaded_from_path",
                    article_index=idx,
                    content_path=art.content_path,
                    content_len=len(content),
                )
            except ValueError as exc:
                # 冒泡给上层，由 generate_mp_rewrite_report 统一变成 error 消息
                raise ValueError(
                    f"第 {idx} 篇原文读取失败: {exc}"
                ) from exc
        else:
            content = art.content or ""

        content = content.strip()

        # 2) 超长截断
        if len(content) > max_chars:
            logger.warning(
                "mp_article_truncated",
                article_index=idx,
                original_len=len(content),
                max_chars=max_chars,
            )
            content = content[:max_chars]

        normalized.append(
            MpArticleInput(
                article_id=f"art_{idx}",
                title=(art.title or "").strip(),
                content=content,
                # 已经把文件内容内联到 content，下游无需再关心路径
                content_path=None,
            )
        )
    return normalized


async def generate_mp_rewrite_report(
    rewrite_intent: str,
    source_articles: List[MpArticleInput],
    target_style: str = "",
    word_count_requirement: str = "",
) -> Tuple[Optional[str], str]:
    """对外主入口：执行公众号文章改写流程。

    Returns:
        (final_report, error_message)
    """
    # 1. 基础校验
    if not rewrite_intent or not rewrite_intent.strip():
        return None, "改写诉求 rewrite_intent 不能为空"
    if not source_articles:
        return None, "至少需要提供一篇原文"

    settings = get_settings()

    # 1.1 篇数上限校验
    if len(source_articles) > settings.mp_max_articles:
        return None, f"最多支持提交 {settings.mp_max_articles} 篇原文"

    # 1.2 过滤既没有 content 也没有 content_path 的空原文
    valid_articles = [
        a
        for a in source_articles
        if (a.content or "").strip() or (a.content_path or "").strip()
    ]
    if not valid_articles:
        return None, "所有原文均为空（content 与 content_path 都未提供），无法改写"

    # 2. 生成 run_id 便于日志追踪
    run_id = uuid.uuid4().hex[:8]

    logger.info(
        "mp_rewrite_service_start",
        rewrite_intent=rewrite_intent[:100],
        article_count=len(valid_articles),
        run_id=run_id,
    )

    try:
        # 3. 规整原文并组装领域请求模型（此处会读取本地文件）
        try:
            articles = _normalize_articles(valid_articles, settings)
        except ValueError as exc:
            logger.warning(
                "mp_rewrite_article_normalize_failed",
                error=str(exc),
                run_id=run_id,
            )
            return None, str(exc)

        # 3.1 读取 / 截断后如果所有正文都为空，直接返回
        if not any((a.content or "").strip() for a in articles):
            return None, "所有原文正文均为空，无法改写"

        request = MpRewriteRequest(
            rewrite_intent=rewrite_intent.strip(),
            target_style=(target_style or "").strip(),
            word_count_requirement=(word_count_requirement or "").strip(),
            source_articles=articles,
        )

        # 4. 调用多 Agent 编排流程
        final_report, error = await run_mp_rewrite_flow(request)

        if error:
            logger.warning("mp_rewrite_service_failed", error=error, run_id=run_id)
        else:
            logger.info("mp_rewrite_service_success", run_id=run_id)
        return final_report, error
    except Exception as exc:  # noqa: BLE001
        logger.exception("mp_rewrite_service_exception", error=str(exc), run_id=run_id)
        return None, f"服务异常: {str(exc)}"
