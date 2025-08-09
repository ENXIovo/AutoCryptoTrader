from typing import Literal, Optional
from pydantic import BaseModel, Field, conlist, confloat, constr

Category = Literal[
    "macro", "regulation", "etf", "exchange_status", "security_incident",
    "whale_transaction", "project_upgrade", "partnership",
    "stablecoin", "mining", "derivatives", "onchain_metric"
]

class LabelRequest(BaseModel):
    text: constr(strip_whitespace=True, min_length=1, max_length=2000)

class LabelResponse(BaseModel):
    category: conlist(Category, min_length=1, max_length=3) = Field(
        description="pick 1–3 from list"
    )
    importance: confloat(ge=0.0, le=1.0) = Field(
        description="0.1 minor · 0.5 notable · 0.8 major"
    )
    durability: Literal["hours", "days", "weeks", "months"] = Field(
        description="FIXED TTL: hours=6h, days=7d, weeks=3w, months=3mo"
    )
    summary: constr(min_length=10, max_length=300) = Field(
        description="1 neutral English sentence"
    )
    confidence: confloat(ge=0.0, le=1.0) = Field(
        description="text-only: 0.3 speculative · 0.6 stated w/ specifics · 0.9 explicit proof in text"
    )

class NewsItem(BaseModel):
    source: str
    category: str
    importance: str
    durability: str
    summary: str
    confidence: str
    ts: str
    key: str
    label_version: str
    weight: float
    age: Optional[str] = None