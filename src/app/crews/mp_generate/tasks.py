"""公众号文章生成项目的 Task 定义与构造函数。

本模块作为「单一来源」维护所有 CrewAI Task 的结构，供 `flows.py` 调用。
Task 描述统一从 `app/crews/config/tasks_mp_gen.yaml` 加载，支持变量替换。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import yaml
from crewai import Task

from app.crews.mp_generate.agents import (
    get_mp_gen_optimizer,
    get_mp_gen_strategy_expert,
    get_mp_gen_topic_planner,
    get_mp_gen_writer,
)
from app.schemas.mp_generate import (
    MpGeneratedArticle,
    MpGenerateStrategyBrief,
    MpGenOptimizedArticle,
    MpTopicResearch,
)

_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def _load_tasks_config() -> dict:
    """从 tasks_mp_gen.yaml 读取全部 Task 配置。"""
    try:
        with (_CONFIG_DIR / "tasks_mp_gen.yaml").open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as e:
        from app.observability.logging import get_logger

        logger = get_logger(__name__)
        logger.error("tasks_mp_gen_yaml_load_failed", error=str(e))
        return {}


_TASKS_CFG = _load_tasks_config()


def _get_task_config(task_name: str) -> dict:
    """获取指定 Task 的配置。"""
    return _TASKS_CFG.get(task_name, {}) if isinstance(_TASKS_CFG, dict) else {}


def build_topic_research_task(
    point_id: str,
    point: str,
    topic: str,
    writing_intent: str,
) -> Task:
    """基于单个关键要点构建选题调研 Task（每个要点一个 Task，输出单个 MpTopicResearch）。"""
    cfg = _get_task_config("task_mp_gen_topic_research")

    point_json = json.dumps(
        {
            "point_id": point_id,
            "point": point,
        },
        ensure_ascii=False,
        indent=2,
    )

    description = cfg.get("description").format(
        topic=topic,
        writing_intent=writing_intent or "（未指定，可自由发挥）",
        point_info=point_json,
    )

    return Task(
        description=description,
        expected_output=cfg.get("expected_output"),
        agent=get_mp_gen_topic_planner(),
        output_pydantic=MpTopicResearch,
        async_execution=True,  # 异步执行，实现多要点并发调研
    )


def build_research_summary_task(context: List[Task]) -> Task:
    """基于多个选题调研任务的结果构建选题调研总结 Task。"""
    cfg = _get_task_config("task_mp_gen_research_summary")
    return Task(
        description=cfg.get("description", ""),
        expected_output=cfg.get("expected_output", ""),
        agent=get_mp_gen_topic_planner(),
        context=context,
        async_execution=False,
    )


def get_task_gen_strategy() -> Task:
    """从 YAML 配置构建内容策略 Task，每次调用返回新实例。"""
    cfg = _get_task_config("task_mp_gen_strategy")
    return Task(
        description=cfg.get("description", ""),
        expected_output=cfg.get("expected_output", ""),
        agent=get_mp_gen_strategy_expert(),
        output_pydantic=MpGenerateStrategyBrief,
        async_execution=False,
    )


def get_task_gen_writing(strategy_task: Task) -> Task:
    """基于内容策略 Task 构建正文创作 Task，每次调用返回新实例。"""
    cfg = _get_task_config("task_mp_gen_writing")
    return Task(
        description=cfg.get("description", ""),
        expected_output=cfg.get("expected_output", ""),
        agent=get_mp_gen_writer(),
        context=[strategy_task],  # 依赖上游内容策略任务
        output_pydantic=MpGeneratedArticle,
        async_execution=False,
    )


def get_task_gen_optimization(strategy_task: Task, writing_task: Task) -> Task:
    """基于内容策略和创作正文 Task 构建标题与排版优化 Task，每次调用返回新实例。"""
    cfg = _get_task_config("task_mp_gen_optimization")
    return Task(
        description=cfg.get("description", ""),
        expected_output=cfg.get("expected_output", ""),
        agent=get_mp_gen_optimizer(),
        context=[strategy_task, writing_task],  # 依赖上游两个任务
        output_pydantic=MpGenOptimizedArticle,
        async_execution=False,
    )
