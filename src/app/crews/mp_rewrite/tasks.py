"""公众号文章改写项目的 Task 定义与构造函数。

本模块作为「单一来源」维护所有 CrewAI Task 的结构，供 `flows.py` 调用。
Task 描述统一从 `app/crews/config/tasks.yaml` 加载，支持变量替换。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import yaml
from crewai import Task

from app.crews.mp_rewrite.agents import (
    get_mp_content_analyst,
    get_mp_optimizer,
    get_mp_rewriter,
    get_mp_strategy_expert,
)
from app.schemas.mp_rewrite import (
    MpArticleAnalysis,
    MpArticleInput,
    MpFinalOptimizedArticle,
    MpRewriteStrategyBrief,
    MpRewrittenArticle,
)

_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def _load_tasks_config() -> dict:
    """从 tasks.yaml 读取全部 Task 配置。"""
    try:
        with (_CONFIG_DIR / "tasks_mp.yaml").open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as e:
        from app.observability.logging import get_logger

        logger = get_logger(__name__)
        logger.error("tasks_yaml_load_failed", error=str(e))
        return {}


_TASKS_CFG = _load_tasks_config()


def _get_task_config(task_name: str) -> dict:
    """获取指定 Task 的配置。"""
    return _TASKS_CFG.get(task_name, {}) if isinstance(_TASKS_CFG, dict) else {}


def build_article_analysis_task(article: MpArticleInput, rewrite_intent: str) -> Task:
    """基于单篇原文构建内容分析 Task（每篇一个 Task，输出单篇 MpArticleAnalysis）。"""
    cfg = _get_task_config("task_mp_article_analysis")

    # 仅传入当前这一篇原文的信息
    article_json = json.dumps(
        {
            "article_id": article.article_id,
            "title": article.title,
            "content": article.content,
        },
        ensure_ascii=False,
        indent=2,
    )

    description = cfg.get("description").format(
        rewrite_intent=rewrite_intent,
        article_info=article_json,
    )

    return Task(
        description=description,
        expected_output=cfg.get("expected_output"),
        agent=get_mp_content_analyst(),
        output_pydantic=MpArticleAnalysis,
        async_execution=True,  # 异步执行，实现多篇原文并发分析
    )


def build_article_analysis_summary_task(context: List[Task]) -> Task:
    """基于多个原文分析任务的结果构建内容分析总结 Task。"""
    cfg = _get_task_config("task_mp_article_analysis_summary")
    return Task(
        description=cfg.get("description", ""),
        expected_output=cfg.get("expected_output", ""),
        agent=get_mp_content_analyst(),
        context=context,
        async_execution=False,
    )


def get_task_rewrite_strategy() -> Task:
    """从 YAML 配置构建改写策略 Task，每次调用返回新实例。"""
    cfg = _get_task_config("task_mp_rewrite_strategy")
    return Task(
        description=cfg.get("description", ""),
        expected_output=cfg.get("expected_output", ""),
        agent=get_mp_strategy_expert(),
        output_pydantic=MpRewriteStrategyBrief,
        async_execution=False,
    )


def get_task_rewrite(strategy_task: Task) -> Task:
    """基于改写策略 Task 构建正文改写 Task，每次调用返回新实例。"""
    cfg = _get_task_config("task_mp_rewrite")
    return Task(
        description=cfg.get("description", ""),
        expected_output=cfg.get("expected_output", ""),
        agent=get_mp_rewriter(),
        context=[strategy_task],  # 依赖上游改写策略任务
        output_pydantic=MpRewrittenArticle,
        async_execution=False,
    )


def get_task_optimization(strategy_task: Task, rewrite_task: Task) -> Task:
    """基于改写策略和改写正文 Task 构建标题与排版优化 Task，每次调用返回新实例。"""
    cfg = _get_task_config("task_mp_optimization")
    return Task(
        description=cfg.get("description", ""),
        expected_output=cfg.get("expected_output", ""),
        agent=get_mp_optimizer(),
        context=[strategy_task, rewrite_task],  # 依赖上游两个任务
        output_pydantic=MpFinalOptimizedArticle,
        async_execution=False,
    )
