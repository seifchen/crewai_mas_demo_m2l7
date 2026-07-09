"""公众号文章生成项目的流程编排。

提供对外函数 run_mp_generate_flow，接收领域请求模型并返回最终报告。

两阶段编排（对齐公众号改写项目的设计）：
- 阶段一（并行）：为每个关键要点创建一个选题调研 Task 并发执行，最后汇总；
  若未提供关键要点，则对整体选题做一次调研。
- 阶段二（串行）：内容策略 -> 正文创作 -> 标题与排版优化，生成最终报告。
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Tuple

from crewai import Agent, Crew, Process, Task

from app.core.config import get_settings
from app.crews.mp_generate.tasks import (
    build_research_summary_task,
    build_topic_research_task,
    get_task_gen_optimization,
    get_task_gen_strategy,
    get_task_gen_writing,
)
from app.observability.logging import get_crew_log_file_path, get_logger
from app.observability.metrics import (
    ai_agent_error_total,
    crew_execution_seconds,
)
from app.schemas.mp_generate import (
    MpGeneratedArticle,
    MpGenerateRequest,
    MpGenerateStrategyBrief,
    MpGenOptimizedArticle,
    MpResearchBatchReport,
    MpTopicResearch,
)


logger = get_logger(__name__)


def _generate_final_report(
    request: MpGenerateRequest,
    optimized: MpGenOptimizedArticle,
    generated: MpGeneratedArticle,
) -> str:
    """将结构化中间结果组装为最终字符串报告。"""
    report = ""
    report += f"选题 / 主题: {request.topic}\n"
    if request.writing_intent:
        report += f"创作诉求: {request.writing_intent}\n"
    if request.target_audience:
        report += f"目标读者: {request.target_audience}\n"
    if request.target_style:
        report += f"目标文风: {request.target_style}\n"
    report += "-" * 40 + "\n"
    report += f"优化后标题: {optimized.optimized_title}\n"
    report += f"备选标题: {optimized.alternative_titles}\n"
    report += f"文章摘要: {generated.digest}\n"
    report += f"优化后正文:\n{optimized.optimized_content}\n"
    report += "-" * 40 + "\n"
    report += "排版建议:\n"
    for idx, tip in enumerate(optimized.typesetting_suggestions, start=1):
        report += f"  {idx}. {tip}\n"
    report += f"关键词 / 话题标签: {optimized.keywords}\n"
    report += f"关键段落 / 金句: {generated.key_paragraphs}\n"
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


def _build_research_points(request: MpGenerateRequest) -> List[Tuple[str, str]]:
    """构建待调研的要点列表：(point_id, point)。

    - 若用户提供了 key_points，则每个要点一条；
    - 否则退化为对整体选题做一次调研。
    """
    points = [p.strip() for p in (request.key_points or []) if (p or "").strip()]
    if not points:
        return [("point_0", request.topic)]
    return [(f"point_{i}", p) for i, p in enumerate(points)]


# ============================================================================
# Step 1：为每个关键要点创建「选题调研」任务（并发执行）
# ============================================================================


async def _run_research_phase(
    request: MpGenerateRequest,
) -> Tuple[Dict[str, MpTopicResearch], str]:
    """并发执行所有要点的选题调研，返回按 point_id 索引的结果字典与总结。"""
    research_points = _build_research_points(request)
    if not research_points:
        return {}, ""

    tasks: List[Task] = [
        build_topic_research_task(
            point_id=pid,
            point=point,
            topic=request.topic,
            writing_intent=request.writing_intent,
        )
        for pid, point in research_points
    ]

    summary_task = build_research_summary_task(tasks)
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
        _handle_crew_error(exc, ["mp_gen_topic_planner"])
        raise

    # 将结果按 point_id 索引（跳过最后一个 summary task）
    research_by_id: Dict[str, MpTopicResearch] = {}
    tasks_output = getattr(result, "tasks_output", []) or []

    for task_output in tasks_output[:-1] if len(tasks_output) > 1 else tasks_output:
        research = getattr(task_output, "pydantic", None)
        if isinstance(research, MpTopicResearch):
            research_by_id[research.point_id] = research

    # summary task 是最后一个任务，提取其原始字符串输出
    summary = ""
    if tasks_output:
        summary_output = tasks_output[-1]
        summary = getattr(summary_output, "raw", "") or ""
        if not isinstance(summary, str):
            summary = str(summary)

    logger.info(
        "mp_generate_research_phase_done",
        point_count=len(research_points),
        research_result=research_by_id,
    )
    return research_by_id, summary


# ============================================================================
# Step 2：基于选题调研，顺序执行：内容策略 -> 正文创作 -> 标题排版优化
# ============================================================================


async def _run_writing_phase(
    request: MpGenerateRequest,
    research_batch: MpResearchBatchReport,
) -> Tuple[MpGenerateStrategyBrief, MpGeneratedArticle, MpGenOptimizedArticle]:
    """顺序执行内容策略、正文创作、标题排版优化三个任务，返回三类结构化结果。"""

    strategy_task = get_task_gen_strategy()
    writing_task = get_task_gen_writing(strategy_task)
    optimization_task = get_task_gen_optimization(strategy_task, writing_task)

    crew = Crew(
        agents=_get_tasks_agents([strategy_task, writing_task, optimization_task]),
        tasks=[strategy_task, writing_task, optimization_task],
        process=Process.sequential,
        verbose=True,
        output_log_file=get_crew_log_file_path(get_settings().log_dir),
    )

    try:
        timeout = get_settings().crew_execution_timeout
        result = await asyncio.wait_for(
            crew.akickoff(
                inputs={
                    "topic": request.topic,
                    "writing_intent": request.writing_intent
                    or "（未指定，可自由发挥）",
                    "target_audience": request.target_audience
                    or "（未指定，由策略专家根据选题判断）",
                    "target_style": request.target_style or "（未指定，可自由发挥）",
                    "word_count_requirement": (
                        request.word_count_requirement
                        or "（未指定，由创作编辑按题材自行判断合适篇幅）"
                    ),
                    "research_report": research_batch.model_dump_json(indent=2),
                }
            ),
            timeout=timeout,
        )

        # 约定 tasks_output 顺序分别为：内容策略、创作正文、标题排版优化
        strategy_brief: MpGenerateStrategyBrief = result.tasks_output[0].pydantic
        generated: MpGeneratedArticle = result.tasks_output[1].pydantic
        optimized: MpGenOptimizedArticle = result.tasks_output[2].pydantic

        logger.info("mp_generate_writing_phase_done")
        return strategy_brief, generated, optimized
    except Exception as exc:  # noqa: BLE001
        _handle_crew_error(
            exc,
            ["mp_gen_strategy_expert", "mp_gen_writer", "mp_gen_optimizer"],
        )
        raise


# ============================================================================
# 对外入口：run_mp_generate_flow
# ============================================================================


async def run_mp_generate_flow(
    request: MpGenerateRequest,
) -> Tuple[str | None, str]:
    """执行公众号文章生成多 Agent 流程（多要点并发调研 + 下游串行创作）。

    Returns:
        (final_report, error_message): 成功时返回 (report, "")，失败时返回 (None, error_msg)
    """
    flow_name = "mp_generate_flow"
    start_time = time.perf_counter()

    logger.info(
        "mp_generate_flow_start",
        topic=request.topic[:100],
        key_point_count=len(request.key_points or []),
    )

    if not request.topic or not request.topic.strip():
        return None, "本次请求未提供选题 topic"

    try:
        # Step 1：选题调研（并发）
        research_by_id, research_summary = await _run_research_phase(request)

        # 按要点顺序整理调研结果
        research_points = _build_research_points(request)
        points_research: List[MpTopicResearch] = [
            research_by_id[pid]
            for pid, _ in research_points
            if pid in research_by_id
        ]

        if not points_research:
            return None, "所有选题调研均失败，无法继续创作"

        research_batch = MpResearchBatchReport(
            topic=request.topic,
            writing_intent=request.writing_intent,
            points_research=points_research,
            summary=research_summary,
        )

        # Step 2：内容策略 -> 正文创作 -> 标题排版优化（顺序执行）
        _strategy_brief, generated, optimized = await _run_writing_phase(
            request,
            research_batch,
        )

        # 将结构化中间结果组装为最终字符串报告
        final_report = _generate_final_report(request, optimized, generated)

        duration = time.perf_counter() - start_time
        crew_execution_seconds.labels(flow_name=flow_name).observe(duration)

        logger.info(
            "mp_generate_flow_success",
            point_count=len(points_research),
            duration_seconds=round(duration, 2),
            final_report=final_report,
        )
        return final_report, ""

    except Exception as exc:  # noqa: BLE001
        duration = time.perf_counter() - start_time
        crew_execution_seconds.labels(flow_name=flow_name).observe(duration)

        error_msg = f"流程执行失败: {type(exc).__name__}: {str(exc)}"
        logger.exception(
            "mp_generate_flow_failed",
            error=error_msg,
            duration_seconds=round(duration, 2),
        )
        return None, error_msg
