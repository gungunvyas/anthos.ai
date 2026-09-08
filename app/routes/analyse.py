from fastapi import APIRouter, Depends, HTTPException
from app.services.src.workflow import EmailWorkflow 
from sqlalchemy.orm import Session
import logging
from app.logging_config import setup_logging

from app.database.db import get_db
from app.database.models import Category, Model
from app.schemas import AnalyseRequest, AnalyseResponse,CategoryDetail, ModelDetail

setup_logging()
logger = logging.getLogger(__name__)


router = APIRouter()
workflow = EmailWorkflow()


@router.post("/analyse", response_model=AnalyseResponse, summary="Analyse a batch of emails")
async def analyse(payload: AnalyseRequest, db: Session = Depends(get_db)) -> AnalyseResponse:

    db_categories = db.query(Category).all()
    categories = [
        CategoryDetail(
            id=str(cat.id),
            name=cat.name,
            description=cat.description,
            examples=cat.examples if cat.examples is not None else [],
        )
        for cat in db_categories
    ]
    db_model = (
        db.query(Model)
        .filter((Model.id == payload.model.id) | (Model.name == payload.model.name))
        .first()
    )

    if db_model:
        model_info = ModelDetail(
            id=db_model.id,
            name=db_model.name,
            provider=db_model.provider,
            api_key=db_model.api_key,
            default=payload.model.default,
            setting_id=db_model.setting_id,
        )
    else:
        model_info = ModelDetail(
            id=payload.model.id,
            name=payload.model.name,
            provider=payload.model.provider,
            default=payload.model.default,
            setting_id=payload.model.setting_id,
        )

    try:
        results = await workflow.gather_emails(incoming_emails=payload.emails,
                                incoming_user_defined_categories=categories,
                                model_type=model_info)

        

    except Exception:
        logger.exception("analyze_emails endpoint failed")
        raise HTTPException(status_code=500, detail="Failed to analyze emails")
    
 
    return AnalyseResponse(results=results)
