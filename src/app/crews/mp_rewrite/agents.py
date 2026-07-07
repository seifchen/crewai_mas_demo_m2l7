"""公众号文章改写项目的 Agent 定义。

Agent 的角色文案（role/goal/backstory 等）配置在 `app/crews/config/agents.yaml` 中，
本模块只负责两类“结构化信息”：
- 绑定使用的 LLM（纯文本 qwen3-max-2026-01-23）
- 绑定 tools（IntermediateTool）

即：**除了 llm 和 tools，其余全部走 config。** 与小红书笔记项目保持一致。
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
    """从 agents.yaml 读取全部 Agent 文案与通用配置。"""
    try:
        with (_CONFIG_DIR / "agents_mp.yaml").open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}


_AGENTS_CFG = _load_agents_config()


def _agent_cfg(name: str) -> dict:
    return _AGENTS_CFG.get(name, {}) if isinstance(_AGENTS_CFG, dict) else {}


def get_mp_content_analyst() -> Agent:
    """每次调用创建一个新的公众号内容分析 Agent 实例。"""
    return Agent(
        config=_agent_cfg("mp_content_analyst"),
        tools=_INTERMEDIATE_TOOLS,
        llm=get_llm(provider="hunyuan",),
    )


def get_mp_strategy_expert() -> Agent:
    """每次调用创建一个新的公众号改写策略 Agent 实例。"""
    return Agent(
        config=_agent_cfg("mp_strategy_expert"),
        tools=_INTERMEDIATE_TOOLS,
        llm=get_llm(provider="hunyuan",),
    )


def get_mp_rewriter() -> Agent:
    """每次调用创建一个新的公众号改写编辑 Agent 实例。"""
    return Agent(
        config=_agent_cfg("mp_rewriter"),
        tools=_INTERMEDIATE_TOOLS,
        llm=get_llm(provider="hunyuan", ),
    )


def get_mp_optimizer() -> Agent:
    """每次调用创建一个新的公众号标题与排版优化 Agent 实例。"""
    return Agent(
        config=_agent_cfg("mp_optimizer"),
        tools=_INTERMEDIATE_TOOLS,
        llm=get_llm(provider="hunyuan"),
    )
