"""公众号文章改写项目的流程编排。

提供对外函数 run_mp_rewrite_flow，接收领域请求模型并返回最终报告。

两阶段编排（对齐小红书笔记项目的设计）：
- 阶段一（并行）：为每篇原文创建一个内容分析 Task 并发执行，最后汇总；
- 阶段二（串行）：改写策略 -> 正文改写 -> 标题与排版优化，生成最终报告。
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Tuple

from crewai import Agent, Crew, Process, Task

from app.core.config import get_settings
from app.crews.mp_rewrite.tasks import (
    build_article_analysis_summary_task,
    build_article_analysis_task,
    get_task_optimization,
    get_task_rewrite,
    get_task_rewrite_strategy,
)
from app.observability.logging import get_crew_log_file_path, get_logger
from app.observability.metrics import (
    ai_agent_error_total,
    crew_execution_seconds,
)
from app.schemas.mp_rewrite import (
    MpAnalysisBatchReport,
    MpArticleAnalysis,
    MpFinalOptimizedArticle,
    MpRewriteRequest,
    MpRewriteStrategyBrief,
    MpRewrittenArticle,
)


logger = get_logger(__name__)


def _generate_final_report(
    request: MpRewriteRequest,
    optimized: MpFinalOptimizedArticle,
    rewritten: MpRewrittenArticle,
) -> str:
    """将结构化中间结果组装为最终字符串报告。"""
    report = ""
    report += f"原始改写诉求: {request.rewrite_intent}\n"
    if request.target_style:
        report += f"目标文风: {request.target_style}\n"
    report += f"原文篇数: {len(request.source_articles)}\n"
    report += "-" * 40 + "\n"
    report += f"优化后标题: {optimized.optimized_title}\n"
    report += f"备选标题: {optimized.alternative_titles}\n"
    report += f"文章摘要: {rewritten.digest}\n"
    report += f"优化后正文:\n{optimized.optimized_content}\n"
    report += "-" * 40 + "\n"
    report += "排版建议:\n"
    for idx, tip in enumerate(optimized.typesetting_suggestions, start=1):
        report += f"  {idx}. {tip}\n"
    report += f"关键词 / 话题标签: {optimized.keywords}\n"
    report += f"关键段落 / 金句: {rewritten.key_paragraphs}\n"
    report += f"合规与风险提示: {optimized.compliance_notes}\n"
    report += f"优化说明: {optimized.optimization_summary}\n"
    return report


def _handle_crew_error(exc: Exception, agent_roles: list[str]) -> None:
    """统一处理 Crew 执行错误：记录指标和日志。"""
    error_type = type(exc).__name__
    for role in agent_roles:
        ai_agent_error_total.labels(agent_role=role, error_type=error_type).inc()
    logger.exception("crew_execution_failed", agent_roles=agent_roles, error=str(exc))


def _get_tasks_agents(tasks: List[Task]) -> List[Agent]:
    """获取任务的 Agent 列表。"""
    return [task.agent for task in tasks]


# ============================================================================
# Step 1：为每篇原文创建「内容分析」任务（并发执行）
# ============================================================================


async def _run_analysis_phase(
    request: MpRewriteRequest,
) -> Tuple[Dict[str, MpArticleAnalysis], str]:
    """并发执行所有原文的内容分析，返回按 article_id 索引的结果字典与总结。"""
    if not request.source_articles:
        return {}, ""

    tasks: List[Task] = [
        build_article_analysis_task(art, request.rewrite_intent)
        for art in request.source_articles
    ]
    if not tasks:
        return {}, ""

    summary_task = build_article_analysis_summary_task(tasks)
    tasks.append(summary_task)

    crew = Crew(
        agents=_get_tasks_agents(tasks),
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        output_log_file=get_crew_log_file_path(get_settings().log_dir),
    )

    try:
        timeout = get_settings().crew_execution_timeout
        result = await asyncio.wait_for(crew.akickoff(), timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        _handle_crew_error(exc, ["mp_content_analyst"])
        raise

    # 将结果按 article_id 索引（跳过最后一个 summary task）
    analysis_by_id: Dict[str, MpArticleAnalysis] = {}
    tasks_output = getattr(result, "tasks_output", []) or []

    for task_output in tasks_output[:-1] if len(tasks_output) > 1 else tasks_output:
        analysis = getattr(task_output, "pydantic", None)
        if isinstance(analysis, MpArticleAnalysis):
            analysis_by_id[analysis.article_id] = analysis

    # summary task 是最后一个任务，提取其原始字符串输出
    summary = ""
    if tasks_output:
        summary_output = tasks_output[-1]
        summary = getattr(summary_output, "raw", "") or ""
        if not isinstance(summary, str):
            summary = str(summary)

    logger.info(
        "mp_rewrite_analysis_phase_done",
        article_count=len(request.source_articles),
        analysis_result=analysis_by_id,
    )
    return analysis_by_id, summary


# ============================================================================
# Step 2：基于原文分析，顺序执行：改写策略 -> 正文改写 -> 标题排版优化
# ============================================================================


async def _run_rewrite_phase(
    request: MpRewriteRequest,
    analysis_batch: MpAnalysisBatchReport,
) -> Tuple[MpRewriteStrategyBrief, MpRewrittenArticle, MpFinalOptimizedArticle]:
    """顺序执行改写策略、正文改写、标题排版优化三个任务，返回三类结构化结果。"""

    strategy_task = get_task_rewrite_strategy()
    rewrite_task = get_task_rewrite(strategy_task)
    optimization_task = get_task_optimization(strategy_task, rewrite_task)

    crew = Crew(
        agents=_get_tasks_agents([strategy_task, rewrite_task, optimization_task]),
        tasks=[strategy_task, rewrite_task, optimization_task],
        process=Process.sequential,
        verbose=True,
        output_log_file=get_crew_log_file_path(get_settings().log_dir),
    )

    try:
        timeout = get_settings().crew_execution_timeout
        result = await asyncio.wait_for(
            crew.akickoff(
                inputs={
                    "rewrite_intent": request.rewrite_intent,
                    "target_style": request.target_style or "（未指定，可自由发挥）",
                    "word_count_requirement": (
                        request.word_count_requirement
                        or "（未指定，由改写编辑按题材自行判断合适篇幅）"
                    ),
                    "analysis_report": analysis_batch.model_dump_json(indent=2),
                }
            ),
            timeout=timeout,
        )

        # 约定 tasks_output 顺序分别为：改写策略、改写正文、标题排版优化
        strategy_brief: MpRewriteStrategyBrief = result.tasks_output[0].pydantic
        rewritten: MpRewrittenArticle = result.tasks_output[1].pydantic
        optimized: MpFinalOptimizedArticle = result.tasks_output[2].pydantic

        logger.info("mp_rewrite_rewrite_phase_done")
        return strategy_brief, rewritten, optimized
    except Exception as exc:  # noqa: BLE001
        _handle_crew_error(
            exc,
            ["mp_strategy_expert", "mp_rewriter", "mp_optimizer"],
        )
        raise


# ============================================================================
# 对外入口：run_mp_rewrite_flow
# ============================================================================


async def run_mp_rewrite_flow(
    request: MpRewriteRequest,
) -> Tuple[str | None, str]:
    """执行公众号文章改写多 Agent 流程（多原文并发分析 + 下游串行改写）。

    Returns:
        (final_report, error_message): 成功时返回 (report, "")，失败时返回 (None, error_msg)
    """
    flow_name = "mp_rewrite_flow"
    start_time = time.perf_counter()

    logger.info(
        "mp_rewrite_flow_start",
        rewrite_intent=request.rewrite_intent[:100],
        article_count=len(request.source_articles),
    )

    if not request.source_articles:
        return None, "本次请求未提供任何原文"

    try:
        # Step 1：全部原文内容分析（并发）
        analysis_by_id, analysis_summary = await _run_analysis_phase(request)

        # 按原文顺序整理分析结果
        articles_analysis: List[MpArticleAnalysis] = [
            analysis_by_id[art.article_id]
            for art in request.source_articles
            if art.article_id in analysis_by_id
        ]

        if not articles_analysis:
            return None, "所有原文内容分析均失败，无法继续改写"

        analysis_batch = MpAnalysisBatchReport(
            rewrite_intent=request.rewrite_intent,
            articles_analysis=articles_analysis,
            summary=analysis_summary,
        )

        # Step 2：改写策略 -> 正文改写 -> 标题排版优化（顺序执行）
        _strategy_brief, rewritten, optimized = await _run_rewrite_phase(
            request,
            analysis_batch,
        )

        # 将结构化中间结果组装为最终字符串报告
        final_report = _generate_final_report(request, optimized, rewritten)

        duration = time.perf_counter() - start_time
        crew_execution_seconds.labels(flow_name=flow_name).observe(duration)

        logger.info(
            "mp_rewrite_flow_success",
            article_count=len(articles_analysis),
            duration_seconds=round(duration, 2),
            final_report=final_report,
        )
        return final_report, ""

    except Exception as exc:  # noqa: BLE001
        duration = time.perf_counter() - start_time
        crew_execution_seconds.labels(flow_name=flow_name).observe(duration)

        error_msg = f"流程执行失败: {type(exc).__name__}: {str(exc)}"
        logger.exception(
            "mp_rewrite_flow_failed",
            error=error_msg,
            duration_seconds=round(duration, 2),
        )
        return None, error_msg
