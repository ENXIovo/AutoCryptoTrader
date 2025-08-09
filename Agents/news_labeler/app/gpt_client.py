import logging
from openai import OpenAI
from .models import LabelResponse
from .config import settings

logger = logging.getLogger(__name__)

class GPTClient:
    """
    LLM-lite：
    - 超短 system message（行为约束）
    - 严格 Structured Outputs（结构约束来自 LabelResponse 的 JSON Schema）
    """

    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.labeler_model
        self.system = settings.labeler_system_prompt.strip()
        logger.info("[GPTClient] model=%s", self.model)

    def label_news(self, text: str) -> LabelResponse:
        t = (text or "").strip()
        if not t:
            raise ValueError("empty text")

        resp = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": self.system},
                {"role": "user", "content": t[:2000]},
            ],
            text_format=LabelResponse,  # 直接按 Pydantic 模型解析
        )
        parsed: LabelResponse = resp.output_parsed  # 不合规会抛错或为 None
        return parsed
