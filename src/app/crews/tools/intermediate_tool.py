"""中间结果保存工具：在 Agent 执行过程中保存中间思考产物，供后续步骤使用。"""

from __future__ import annotations

import json
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field, field_validator, model_validator

from app.observability.logging import get_logger

logger = get_logger(__name__)

# 规范字段名
_CANONICAL_FIELD = "intermediate_product"


class IntermediateToolSchema(BaseModel):
    """中间结果保存工具的输入。"""

    intermediate_product: Any = Field(
        ...,
        description=(
            "需要保存的中间思考产物。"
            "支持任意类型：字符串、列表、字典等，会自动转换为字符串。"
            "例如：列表 ['a', 'b'] 会转为 'a\\nb'，字典会转为 JSON 字符串。"
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_name(cls, data: Any) -> Any:
        """容错处理：LLM 调用时常把参数名写成 `intermediate_product_to_save`、
        `product`、`content` 等变体，导致规范字段 `intermediate_product` 缺失而校验失败。

        本校验器在正式校验前把这些"跑偏"的键归一化到 `intermediate_product`，
        避免因参数名不精确导致的 Tool 调用失败。
        """
        if not isinstance(data, dict):
            return data

        # 已包含规范字段（且非 None）则无需处理
        if data.get(_CANONICAL_FIELD) is not None:
            return data

        # 1) 优先匹配包含 "intermediate_product" 的变体键（如 *_to_save）
        for key in list(data.keys()):
            if _CANONICAL_FIELD in str(key).lower():
                data[_CANONICAL_FIELD] = data[key]
                return data

        # 2) 其次匹配常见近义键
        for candidate in ("product", "content", "text", "value", "result", "data"):
            if candidate in data and data[candidate] is not None:
                data[_CANONICAL_FIELD] = data[candidate]
                return data

        # 3) 兜底：只有一个键时，直接把它的值当作中间产物
        non_canonical = {k: v for k, v in data.items() if k != _CANONICAL_FIELD}
        if len(non_canonical) == 1:
            data[_CANONICAL_FIELD] = next(iter(non_canonical.values()))
        elif non_canonical:
            # 多个未知键时，整体作为字典传入（下游会转成 JSON 字符串）
            data[_CANONICAL_FIELD] = dict(non_canonical)

        return data

    @field_validator("intermediate_product", mode="before")
    @classmethod
    def convert_to_string(cls, v: Any) -> str:
        """将任意类型转为字符串：str 原样，list 用换行连接，dict 用 JSON，其余 str()。"""
        if isinstance(v, str):
            return v
        if isinstance(v, list):
            return "\n".join(str(item) for item in v)
        if isinstance(v, dict):
            try:
                return json.dumps(v, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                return str(v)
        return str(v)


class IntermediateTool(BaseTool):
    """
    中间结果保存工具。用于在 Agent 执行中保存中间思考产物，便于后续步骤使用。
    支持任意类型输入，自动转为字符串，无需手动转换。
    """

    name: str = "Save_Intermediate_Product_Tool"
    description: str = (
        "A tool that can be used to save intermediate thinking products "
        "during agent execution. "
        "\n\n"
        "✅ Supports any input type (string, list, dict, etc.) and automatically converts to string format. "
        "You can pass lists, dictionaries, or any other type directly - no need to convert manually. "
        "\n\n"
        "Examples: "
        "- String: 'my text' → saved as 'my text'"
        "- List: ['item1', 'item2'] → saved as 'item1\\nitem2'"
        "- Dict: {'key': 'value'} → saved as JSON string"
    )
    args_schema: type[BaseModel] = IntermediateToolSchema

    def _run(self, intermediate_product: str, **kwargs: Any) -> str:
        """保存中间思考产物，返回固定提示。"""
        logger.debug("intermediate_saved", length=len(intermediate_product))
        return "中间结果已保存，可以进行下一步 Thought"
