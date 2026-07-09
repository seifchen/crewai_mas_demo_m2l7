"""公众号文章生成多 Agent 项目相关的 Pydantic 数据模型。

设计理念与公众号改写 / 小红书笔记项目保持一致——「契约先行」：
先定义各阶段 Agent 之间的数据接口，再实现具体业务逻辑。

与「公众号改写」不同：改写是「有原文 → 分析 → 改写」，
本项目是「有选题诉求 → 选题调研 → 从零创作」，无需提供原文正文。

流程概览：
- 阶段一（并行）：对每个关键要点做选题调研 / 素材扩展（MpTopicResearch），并汇总（MpResearchBatchReport）；
  若未提供关键要点，则对整体选题做一次调研。
- 阶段二（串行）：内容策略（MpGenerateStrategyBrief）→ 正文创作（MpGeneratedArticle）
  → 标题与排版优化（MpGenOptimizedArticle）。
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class MpGenerateRequest(BaseModel):
    """从 API 解析后进入业务层 / 流程编排层的领域请求模型。"""

    topic: str = Field(
        ..., description="本次要创作的公众号文章选题 / 主题，如“如何在低谷期重建自律”。"
    )
    writing_intent: str = Field(
        "",
        description=(
            "对本次创作的补充诉求 / 目标（可选），如受众、场景、侧重点、要达成的效果等；"
            "为空时由选题策划按主题自行判断。"
        ),
    )
    key_points: List[str] = Field(
        default_factory=list,
        description=(
            "希望文章覆盖的关键要点 / 分论点列表（可选）。"
            "若提供，将对每个要点并行做选题调研与素材扩展；为空时对整体选题做一次调研。"
        ),
    )
    target_audience: str = Field(
        "", description="期望的目标读者画像（可选），如“职场新人”“宝妈”“考研党”等。"
    )
    target_style: str = Field(
        "", description="期望的目标文风（可选），如“轻松活泼”“专业干货”“故事化叙述”等。"
    )
    word_count_requirement: str = Field(
        "1500-2000字",
        description=(
            "文章字数要求（可选，自然语言描述），如“控制在 1500–2000 字”“不少于 3000 字”"
            "“800 字左右”等；为空时由创作编辑按题材自行判断合适篇幅。"
        ),
    )


class MpTopicResearch(BaseModel):
    """针对单个关键要点（或整体选题）的选题调研 / 素材扩展结果。"""

    point_id: str = Field(..., description="要点唯一标识，如 point_0。")
    point: str = Field(..., description="被调研的关键要点或整体选题描述。")
    core_argument: str = Field(..., description="围绕该要点可展开的核心论点 / 立意。")
    supporting_ideas: List[str] = Field(
        ..., description="支撑该论点的分论据 / 论证思路列表（至少 3 条）。"
    )
    reader_pain_points: str = Field(
        ..., description="该要点对应的读者痛点 / 关切 / 阅读动机。"
    )
    material_suggestions: List[str] = Field(
        ..., description="可用于创作的素材建议（案例、比喻、数据方向、场景等）。"
    )
    potential_hooks: List[str] = Field(
        ..., description="围绕该要点可用于开头或小标题的钩子 / 金句方向。"
    )


class MpResearchBatchReport(BaseModel):
    """多个关键要点的选题调研汇总报告。"""

    topic: str = Field(..., description="用户的原始选题 / 主题。")
    writing_intent: str = Field(..., description="用户的补充创作诉求。")
    points_research: List[MpTopicResearch] = Field(
        ..., description="所有关键要点的选题调研结果列表。"
    )
    summary: str = Field(..., description="整体选题调研的一句话总结。")


class MpGenerateStrategyBrief(BaseModel):
    """内容策略简报，由公众号内容策略 Agent 产出。"""

    content_angle: str = Field(
        ..., description="本次创作选定的切入角度 / 核心立意。"
    )
    target_audience_persona: str = Field(
        ..., description="目标读者画像：身份、场景、心理诉求等。"
    )
    core_value: str = Field(..., description="文章要传递给读者的核心价值 / 收益。")
    suggested_title_direction: str = Field(
        ..., description="建议的标题方向（钩子类型、情绪 / 利益点等），非最终标题。"
    )
    content_outline: List[str] = Field(
        ..., description="文章的结构大纲（开头钩子、主体分段、结尾引导等）。"
    )
    hook_design: str = Field(
        ..., description="开头钩子与阅读留存设计：如何抓住前 3 秒、如何引导读完。"
    )
    tone_guidance: str = Field(
        ..., description="行文语气与情绪基调指引，供创作编辑落地时统一风格。"
    )


class MpGeneratedArticle(BaseModel):
    """创作完成的文章正文，由公众号创作编辑 Agent 产出。"""

    title: str = Field(..., description="创作的公众号文章标题。")
    content: str = Field(..., description="完整的公众号正文（保留分段）。")
    digest: str = Field(..., description="公众号摘要 / 导语（约 100 字以内）。")
    key_paragraphs: List[str] = Field(
        ..., description="文中关键段落 / 金句列表，便于做重点标记与二次传播。"
    )


class MpGenOptimizedArticle(BaseModel):
    """标题与排版优化后的最终文章，由公众号优化 Agent 产出。"""

    optimization_summary: str = Field(
        ..., description="本次优化的要点与改动说明。"
    )
    optimized_title: str = Field(..., description="优化后的主标题。")
    alternative_titles: List[str] = Field(
        ..., description="3-5 个可用于 A/B 测试的备选标题。"
    )
    optimized_content: str = Field(..., description="优化后的正文（含排版建议标记）。")
    typesetting_suggestions: List[str] = Field(
        ..., description="公众号排版建议：小标题、分段、加粗、配图位置、引导语等。"
    )
    keywords: List[str] = Field(..., description="用于分发与检索的关键词 / 话题标签。")
    compliance_notes: str = Field(
        ..., description="合规与风险提示：需规避的夸大表述、敏感内容、版权风险等。"
    )


class MpGenerateFinalReport(BaseModel):
    """整体创作报告，供 API 直接返回（结构化版本）。"""

    topic: str = Field(..., description="原始选题 / 主题文本。")
    strategy_brief: MpGenerateStrategyBrief = Field(..., description="内容策略简报。")
    generated_article: MpGeneratedArticle = Field(..., description="创作的原始文章。")
    optimized_article: MpGenOptimizedArticle = Field(
        ..., description="标题与排版优化后的最终文章。"
    )


class MpGenerateReportResponse(BaseModel):
    """顶层响应数据结构，便于与统一 ApiResponse 泛型结合。"""

    report: str = Field(..., description="最终公众号文章生成报告。")
