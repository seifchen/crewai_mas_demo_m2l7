"""公众号文章生成项目的 Agent 定义。

Agent 的角色文案（role/goal/backstory 等）配置在 `app/crews/config/agents_mp_gen.yaml` 中，
本模块只负责两类“结构化信息”：
- 绑定使用的 LLM
- 绑定 tools（IntermediateTool）

即：**除了 llm 和 tools，其余全部走 config。** 与公众号改写项目保持一致。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from crewai import Agent

from app.crews.llm import get_llm
from app.crews.tools import IntermediateTool


_INTERMEDIATE_TOOLS = [IntermediateTool()]

_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def _load_agents_config() -> dict:
    """从 agents_mp_gen.yaml 读取全部 Agent 文案与通用配置。"""
    try:
        with (_CONFIG_DIR / "agents_mp_gen.yaml").open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}


_AGENTS_CFG = _load_agents_config()


def _agent_cfg(name: str) -> dict:
    return _AGENTS_CFG.get(name, {}) if isinstance(_AGENTS_CFG, dict) else {}


def get_mp_gen_topic_planner() -> Agent:
    """每次调用创建一个新的公众号选题策划 Agent 实例。"""
    return Agent(
        config=_agent_cfg("mp_gen_topic_planner"),
        tools=_INTERMEDIATE_TOOLS,
        llm=get_llm(provider="hunyuan"),
    )


def get_mp_gen_strategy_expert() -> Agent:
    """每次调用创建一个新的公众号内容策略 Agent 实例。"""
    return Agent(
        config=_agent_cfg("mp_gen_strategy_expert"),
        tools=_INTERMEDIATE_TOOLS,
        llm=get_llm(provider="hunyuan"),
    )


def get_mp_gen_writer() -> Agent:
    """每次调用创建一个新的公众号创作编辑 Agent 实例。"""
    return Agent(
        config=_agent_cfg("mp_gen_writer"),
        tools=_INTERMEDIATE_TOOLS,
        llm=get_llm(provider="hunyuan"),
    )


def get_mp_gen_optimizer() -> Agent:
    """每次调用创建一个新的公众号标题与排版优化 Agent 实例。"""
    return Agent(
        config=_agent_cfg("mp_gen_optimizer"),
        tools=_INTERMEDIATE_TOOLS,
        llm=get_llm(provider="hunyuan"),
    )
