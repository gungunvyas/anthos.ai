import asyncio
from contextlib import contextmanager
import logging
from typing import Generator

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette import status

from app.database.db import get_db
from app.database.models import Category, Model
from app.logging_config import current_log_queue, setup_logging
from app.schemas import AnalyseRequest, AnalyseResponse, CategoryDetail, ModelDetail
from app.services.src.workflow import EmailWorkflow
from app.settings import get_settings

setup_logging()
logger = logging.getLogger(__name__)

router = APIRouter()
workflow = EmailWorkflow()
settings = get_settings()


def is_origin_allowed(origin: str | None) -> bool:
    """
    Check whether the WebSocket client's Origin is permitted based on ANTHOSWEB_URL.

    If the origin header is omitted (e.g. CLI tools, unit tests), it is allowed.
    If present, it must match one of the allowed origins configured in settings.cors_origins.
    """
    if not origin:
        return True
    allowed_origins = settings.cors_origins
    if "*" in allowed_origins:
        return True
    return origin.strip().rstrip("/") in allowed_origins


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Safely manage a database session lifecycle for WebSocket requests.
    Guarantees session closure upon exiting the context block, preventing connection pool leaks.
    """
    db_gen = get_db()
    db = next(db_gen)
    try:
        yield db
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


async def execute_email_analysis(payload: AnalyseRequest, db: Session) -> list[dict]:
    """
    Core business logic to analyze a batch of emails:
    1. Fetches user categories from the database.
    2. Resolves model configuration (custom model from DB or payload details).
    3. Runs the multi-agent LangGraph workflow.
    """
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

    results = await workflow.gather_emails(
        incoming_emails=payload.emails,
        incoming_user_defined_categories=categories,
        model_type=model_info,
    )
    return results


@router.websocket("/analyse")
async def websocket_analyse(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time email batch analysis on /analyse.

    Protocol:
    1. Origin Validation: Confirms incoming request Origin matches ANTHOSWEB_URL.
    2. Connection: Accepts the WebSocket handshake.
    3. Request Receipt & Immediate Confirmation:
       - Client sends JSON matching AnalyseRequest.
       - Server immediately sends a confirmation frame:
         {"type": "confirmation", "status": "confirmed", "message": "...", "email_count": N}
    4. Real-Time Log Streaming:
       - Binds current_log_queue ContextVar for the current task.
       - All console logs emitted during processing (cleaning, regex, LLM categorization,
         supervisor verification, retries, summary) are forwarded live to the frontend:
         {"type": "log", "status": "processing", "level": "INFO", "message": "...", "timestamp": "..."}
    5. Final Completion:
       - Sends {"type": "complete", "status": "completed", "results": [...]}
    6. Error Handling:
       - If an error occurs, sends {"type": "error", "status": "error", "message": "...", "detail": "..."}
    """
    origin = websocket.headers.get("origin")
    if not is_origin_allowed(origin):
        logger.warning(
            "Rejected WebSocket connection from unauthorized origin: %s (allowed: %s)",
            origin,
            settings.cors_origins,
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Origin not allowed")
        return

    await websocket.accept()
    logger.info("WebSocket /analyse connection accepted from origin: %s", origin or "direct/test")

    try:
        while True:
            # Receive analysis request payload
            try:
                raw_message = await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info("WebSocket /analyse client disconnected")
                break
            except Exception as e:
                logger.warning("Error receiving message from WebSocket: %s", e)
                break

            # Parse and validate incoming payload
            try:
                payload = AnalyseRequest.model_validate_json(raw_message)
            except ValidationError as val_err:
                logger.warning("Invalid payload received on WebSocket: %s", val_err)
                await websocket.send_json({
                    "type": "error",
                    "status": "error",
                    "message": "Invalid request payload format",
                    "detail": val_err.errors(),
                })
                continue
            except Exception as json_err:
                logger.warning("Malformed JSON received on WebSocket: %s", json_err)
                await websocket.send_json({
                    "type": "error",
                    "status": "error",
                    "message": "Malformed JSON payload",
                    "detail": str(json_err),
                })
                continue

            # Step 1: Immediately confirm receipt and start of processing
            await websocket.send_json({
                "type": "confirmation",
                "status": "confirmed",
                "message": f"Analysis request confirmed for {len(payload.emails)} email(s). Processing started.",
                "email_count": len(payload.emails),
                "model_name": payload.model.name,
            })
            logger.info("Confirmed analysis request for %d email(s)", len(payload.emails))

            # Step 2: Set up real-time log queue bound to this request context
            log_queue: asyncio.Queue = asyncio.Queue()
            token = current_log_queue.set(log_queue)

            async def stream_logs_to_client() -> None:
                """Stream queued log records live over the WebSocket."""
                try:
                    while True:
                        log_item = await log_queue.get()
                        if log_item is None:
                            # Sentinel indicating processing finished
                            log_queue.task_done()
                            break
                        await websocket.send_json(log_item)
                        log_queue.task_done()
                except (WebSocketDisconnect, RuntimeError):
                    # Connection closed by client during streaming
                    pass
                except Exception as stream_err:
                    logger.debug("Log streaming encountered error: %s", stream_err)

            log_streamer_task = asyncio.create_task(stream_logs_to_client())

            # Step 3: Execute the analysis workflow and stream logs
            try:
                with get_db_session() as db:
                    results = await execute_email_analysis(payload=payload, db=db)

                # Wait for all buffered logs to finish streaming
                await log_queue.put(None)
                await log_streamer_task

                # Step 4: Send the final completed analysis results
                await websocket.send_json({
                    "type": "complete",
                    "status": "completed",
                    "results": results,
                })
                logger.info(
                    "Completed and delivered analysis results for %d email(s) over WebSocket",
                    len(payload.emails),
                )

            except Exception as proc_err:
                logger.exception("Error executing email analysis on WebSocket: %s", proc_err)
                # Ensure streamer task cleanly completes
                await log_queue.put(None)
                if not log_streamer_task.done():
                    await log_streamer_task

                await websocket.send_json({
                    "type": "error",
                    "status": "error",
                    "message": "Failed to analyze emails",
                    "detail": str(proc_err),
                })
            finally:
                # Reset contextvar token to prevent queue leakage
                current_log_queue.reset(token)

    except WebSocketDisconnect:
        logger.info("WebSocket /analyse connection closed")
    except Exception as exc:
        logger.exception("Unexpected error in WebSocket /analyse handler: %s", exc)


@router.post("/analyse", response_model=AnalyseResponse, summary="Analyse a batch of emails (HTTP Fallback)")
async def analyse(payload: AnalyseRequest, db: Session = Depends(get_db)) -> AnalyseResponse:
    """
    HTTP POST fallback endpoint for analyzing emails.
    Maintains backward-compatibility with existing HTTP clients.
    For live real-time progress updates, use the WebSocket endpoint at ws://.../analyse.
    """
    try:
        results = await execute_email_analysis(payload=payload, db=db)
    except Exception:
        logger.exception("analyze_emails endpoint failed")
        raise HTTPException(status_code=500, detail="Failed to analyze emails")

    return AnalyseResponse(results=results)
