"""公众号文章改写多 Agent 项目相关的 Pydantic 数据模型。

设计理念与小红书笔记项目保持一致——「契约先行」：
先定义各阶段 Agent 之间的数据接口，再实现具体业务逻辑。

流程概览：
- 阶段一（并行）：对每篇原文做内容分析（MpArticleAnalysis），并汇总（MpAnalysisBatchReport）；
- 阶段二（串行）：改写策略（MpRewriteStrategyBrief）→ 正文改写（MpRewrittenArticle）
  → 标题与排版优化（MpFinalOptimizedArticle）。
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class MpArticleInput(BaseModel):
    """进入业务层 / 流程编排层的单篇原文。

    支持两种传入方式（二选一，`content_path` 优先级更高）：
    - `content`：直接把原文正文放到 JSON 里；
    - `content_path`：仅传服务端可读的本地文件路径（推荐大文本使用，可显著减少
      客户端 → 服务端传输的 token / 请求体体积）。
    """

    article_id: str = Field("", description="服务端为每篇原文分配的唯一标识，如 art_0；调用方可不传。")
    title: str = Field("", description="原文标题（可为空）。")
    content: str = Field(
        "",
        description="原文正文内容。若同时提供 `content_path`，则以 `content_path` 读取的文件内容为准。",
    )
    content_path: Optional[str] = Field(
        None,
        description=(
            "服务端本地文件路径（如 `.txt` / `.md`），用于替代直接传大段 `content` 以节省 token；"
            "服务端将读取该文件内容作为原文正文。为安全起见，可通过配置项 "
            "`APP_MP_ARTICLE_READ_ROOT` 限制允许读取的根目录。"
        ),
    )

    @model_validator(mode="after")
    def _check_content_or_path(self) -> "MpArticleInput":
        has_content = bool((self.content or "").strip())
        has_path = bool((self.content_path or "").strip())
        if not has_content and not has_path:
            raise ValueError("`content` 与 `content_path` 至少需要提供一个")
        return self


class MpRewriteRequest(BaseModel):
    """从 API 解析后进入业务层 / 流程编排层的领域请求模型。"""

    rewrite_intent: str = Field(
        ..., description="用户对本次改写的自然语言诉求 / 目标，如受众、风格、侧重点等。"
    )
    target_style: str = Field(
        "", description="期望的目标文风（可选），如“轻松活泼”“专业干货”“故事化叙述”等。"
    )
    word_count_requirement: str = Field(
        "1500-2000字",
        description=(
            "文章字数要求（可选，自然语言描述），如“控制在 1500–2000 字”“不少于 3000 字”"
            "“800 字左右”等；为空时由改写编辑按题材自行判断合适篇幅。"
        ),
    )
    source_articles: List[MpArticleInput] = Field(
        ..., description="本次参与分析与改写的原文列表（支持多篇素材聚合改写）。"
    )


class MpArticleAnalysis(BaseModel):
    """单篇原文的内容分析结果。"""

    article_id: str = Field(..., description="原文唯一标识，对应 MpArticleInput.article_id。")
    core_theme: str = Field(..., description="原文核心主题 / 中心思想的客观概括。")
    key_points: List[str] = Field(
        ..., description="原文的关键信息点 / 核心论据列表（至少 3 条）。"
    )
    structure_outline: str = Field(
        ..., description="原文的结构脉络（如开头、论证、案例、结尾等）。"
    )
    tone_style: str = Field(..., description="原文的语言风格与语气（如严肃、口语化、煽情等）。")
    target_audience: str = Field(..., description="原文推断的目标读者画像。")
    highlights: List[str] = Field(
        ..., description="值得在改写中保留 / 放大的亮点或金句。"
    )
    reusable_material: str = Field(
        ..., description="可在改写中复用的素材（数据、案例、观点等）概述。"
    )


class MpAnalysisBatchReport(BaseModel):
    """多篇原文的内容分析汇总报告。"""

    rewrite_intent: str = Field(..., description="用户的原始改写诉求。")
    articles_analysis: List[MpArticleAnalysis] = Field(
        ..., description="所有原文的内容分析结果列表。"
    )
    summary: str = Field(..., description="所有原文内容分析的总结。")


class MpRewriteStrategyBrief(BaseModel):
    """改写策略简报，由公众号策略 Agent 产出。"""

    content_angle: str = Field(
        ..., description="本次改写选定的切入角度 / 核心立意。"
    )
    target_audience_persona: str = Field(
        ..., description="目标读者画像：身份、场景、心理诉求等。"
    )
    core_value: str = Field(..., description="改写后要传递给读者的核心价值 / 收益。")
    suggested_title_direction: str = Field(
        ..., description="建议的标题方向（钩子类型、情绪 / 利益点等），非最终标题。"
    )
    content_outline: List[str] = Field(
        ..., description="改写后文章的结构大纲（开头钩子、主体分段、结尾引导等）。"
    )
    hook_design: str = Field(
        ..., description="开头钩子与阅读留存设计：如何抓住前 3 秒、如何引导读完。"
    )
    differentiation: str = Field(
        ..., description="相较原文的差异化改写策略（视角、结构或表达上的升级点）。"
    )


class MpRewrittenArticle(BaseModel):
    """改写后的文章正文，由公众号改写编辑 Agent 产出。"""

    title: str = Field(..., description="改写后的公众号文章标题。")
    content: str = Field(..., description="改写后的完整公众号正文（保留分段）。")
    digest: str = Field(..., description="公众号摘要 / 导语（约 100 字以内）。")
    key_paragraphs: List[str] = Field(
        ..., description="文中关键段落 / 金句列表，便于做重点标记与二次传播。"
    )


class MpFinalOptimizedArticle(BaseModel):
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


class MpRewriteFinalReport(BaseModel):
    """整体改写报告，供 API 直接返回（结构化版本）。"""

    rewrite_intent: str = Field(..., description="原始改写诉求文本。")
    strategy_brief: MpRewriteStrategyBrief = Field(..., description="改写策略简报。")
    rewritten_article: MpRewrittenArticle = Field(..., description="改写后的原始文章。")
    optimized_article: MpFinalOptimizedArticle = Field(
        ..., description="标题与排版优化后的最终文章。"
    )


class MpRewriteReportResponse(BaseModel):
    """顶层响应数据结构，便于与统一 ApiResponse 泛型结合。"""

    report: str = Field(..., description="最终公众号改写报告。")
