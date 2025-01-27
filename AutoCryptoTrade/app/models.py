from pydantic import BaseModel
from typing import Optional, Literal

class MarketRequest(BaseModel):
    symbol: str
    mode: Optional[str] = None
    

class MessageRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    system_message: Optional[str] = None
    context_length: Optional[int] = None
    temperature: Optional[float] = None
    deployment_name: Optional[str] = None
    def to_payload(self) -> dict:
        """
        Convert the MessageRequest object to a dictionary,
        excluding None values.
        """
        return self.model_dump(exclude_none=True)

class GPTResponse(BaseModel):
    message: str
