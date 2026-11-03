from typing import List, Literal
from pydantic import BaseModel, Field


class ConditionResult(BaseModel):
    condition_id: str = Field(description="Unique identifier of the condition")
    description: str = Field(description="Brief text of the condition")
    met: bool = Field(description="True if the condition is fully met on the chart; otherwise False")
    reason: str = Field(description="Strictly one sentence explaining why this condition is met or not met")


class ArgonAnalysisResult(BaseModel):
    direction: Literal["BUY", "SELL", "NONE"] = Field(
        description="Trade bias indicated by the chart setup"
    )
    checklist: List[ConditionResult] = Field(
        description="Evaluation results for each rule in the trading plan checklist"
    )
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        default="MEDIUM",
        description="Confidence level in the pattern clarity"
    )
    summary: str = Field(
        description="One or two sentences summarizing the overall setup"
    )


def get_analysis_json_schema() -> dict:
    """Returns the JSON schema dict to pass to agy CLI --json-schema."""
    return ArgonAnalysisResult.model_json_schema()

