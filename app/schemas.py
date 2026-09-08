from datetime import datetime
from typing import List, Optional, Any
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., example="ok")


class TimeResponse(BaseModel):
    utc_time: str = Field(..., example="2026-08-12T18:00:00+00:00")


class EmailItem(BaseModel):
    id: str = Field(..., example="jk14nrk1nek31jnk1j")
    subject: Optional[str] = Field(default=None, example="Skeps is hiring. Get connected.")
    body: str = Field(..., example="<!DOCTYPE html ...")
    sender: str = Field(...,description="the sender's email")
    threadId: Optional[str] = Field(default=None, example="19ff6fasd4c17bc")

class ModelDetail(BaseModel):
    id: str = Field(..., example="6b73ef82-7a41-451e-ac2b-a0107475cb38")
    name: str = Field(..., example="nemotron-3.5-lightning-30b-a3b")
    provider: str = Field(..., example="NVIDIA")
    default: bool = Field(default=False, example=False)
    api_key: Optional[str] = Field(default=None, example="...")
    setting_id: Optional[str] = Field(default=None, example="42821d65-9f24-4b44-b88b-6d3b1c85a12f")

class EmailAnalysisResult(BaseModel):
    id: str = Field(..., example="jk14nrk1nek31jnk1j")
    threadId: str = Field(..., )
    summary: Optional[str] = Field(
        default=None,
        description="AI-generated 50-word summary of the email body. Populated by the AI layer; null when not yet generated.",
        example=None,
    )
    category: Optional[str] = Field(
        default=None,
        description="Category name assigned to this email, matched from the categories table in the database.",
        example="Promotions",
    )
    priority_score: float = Field(
        ...,
        description="Numeric priority score for the email (1 = highest). Assigned by the AI layer; dummy value used until AI integration.",
        example=3)
    
    confidence_score: float = Field(
        ..., description="How confident the llm if about the classification"
    )

    versions: List[int]
    retry_count: int

class CategoryDetail(BaseModel):
    id: str = Field(..., example="56c74249-7f6c-4fa8-8441-13db516ac88c")
    name: str = Field(..., example="Important")
    description: Optional[str] = Field(default=None, example="strategic updates...")
    examples: Optional[Any] = Field(default_factory=list, example=[])

class AnalyseRequest(BaseModel):
    emails: List[EmailItem] = Field(..., min_length=1)
    model: ModelDetail

class AnalyseResponse(BaseModel):
    results: List[EmailAnalysisResult]
    
