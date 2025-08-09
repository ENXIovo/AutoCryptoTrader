from typing import Literal
from pydantic import BaseModel, Field, conlist, confloat, constr

# 受控小词表（最多选 3 个）
Category = Literal[
    "macro", "regulation", "etf", "exchange_status", "security_incident",
    "whale_transaction", "project_upgrade", "partnership",
    "stablecoin", "mining", "derivatives", "onchain_metric"
]

class LabelRequest(BaseModel):
    # 文本最多 2000 字符，避免长文抬高 token
    text: constr(strip_whitespace=True, min_length=1, max_length=2000)

class LabelResponse(BaseModel):
    # 注意：conlist 使用 min_length / max_length（不是 min_items / max_items）
    category: conlist(Category, min_length=1, max_length=3) = Field(
        ..., description="Choose 1-3 labels from the controlled list"
    )
    importance: confloat(ge=0.0, le=1.0) = Field(
        ..., description="0.1 minor, 0.5 notable, 0.8 major"
    )
    durability: Literal["hours", "days", "weeks", "months"] = Field(
        ..., description="Impact bucket; exact TTL/half-life handled by backend"
    )
    summary: constr(min_length=10, max_length=300) = Field(
        ..., description="One-sentence, neutral, English summary"
    )
    confidence: confloat(ge=0.0, le=1.0) = Field(
        ..., description="0.3 rumor, 0.6 partial, 0.9 confirmed"
    )
