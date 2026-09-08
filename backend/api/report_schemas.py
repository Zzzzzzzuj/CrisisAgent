from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


ReportFormat = Literal["json", "markdown"]


class MarkdownReportResponse(BaseModel):
    format: Literal["markdown"]
    event_id: str
    markdown_content: str
    automatic_publish: bool = False
