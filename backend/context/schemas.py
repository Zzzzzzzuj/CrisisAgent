from pydantic import BaseModel, Field


class ContextItem(BaseModel):
    source: str
    content: str
    priority: int = Field(default=0)
    token_size: int = Field(default=0, ge=0)
