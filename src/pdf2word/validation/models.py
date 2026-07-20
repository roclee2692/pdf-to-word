from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Severity = Literal["info", "warning", "error"]
CheckLayer = Literal["structure", "text", "table", "image", "visual"]


class ValidationIssue(BaseModel):
    layer: CheckLayer
    severity: Severity
    code: str
    message: str
    page: int | None = None
    element_id: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class LayerSummary(BaseModel):
    status: Literal["pass", "warn", "fail", "skipped"]
    issue_count: int = 0
    metrics: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None


class ValidationReport(BaseModel):
    """Four-layer validation result for one conversion job."""

    schema_version: str = "1.0"
    mode: str
    passed: bool
    structure: LayerSummary
    text: LayerSummary
    table: LayerSummary
    image: LayerSummary
    visual: LayerSummary
    issues: list[ValidationIssue] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()
