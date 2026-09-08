from typing import TypedDict, List,Optional
from pydantic import BaseModel, Field

from app.schemas import ModelDetail,CategoryDetail,EmailItem

class EmailRequest(BaseModel):

    mails: List[EmailItem]
    user_categories: List[CategoryDetail]
    

class ProcessedEmail(EmailItem):

    cleaned_subject: Optional[str] = None
    cleaned_body: Optional[str] = None
    category: Optional[str] = None
    priority_score: Optional[float] = None
    confidence_score: Optional[float] = None
    summary: Optional[str] = None


class SupervisorOutput(BaseModel):

    approved: bool = Field(...,description="Whether the classification is acceptable or not ,either true or false")
    feedback: Optional[str] = None

class CategorizeEmailOutput(BaseModel):

    category: str = Field(...,description="The category assigned to the email, indicating its type based on predefined rules.")
    confidence_score: float|int = Field(...,description="How confident the model is about the classification",ge=0,le=1)
    priority_score: float|int = Field(...,description="Priority ranking of each mail",ge=0,le=10)
    summary: Optional[str] = Field(
            default=None,
            description="AI-generated 50-word summary of the email body. Populated by the AI layer; null when not yet generated."
        )

class MainGraphState(TypedDict): # main langgraph state with data every node might need

    one_email: ProcessedEmail
    email_count: int
    user_defined_email_categories: List[CategoryDetail]
    model_detail: ModelDetail
    supervisor_output: SupervisorOutput
    retry_counter: int = 0
    version_list: List[int] = [1]
    



    
