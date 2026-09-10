import asyncio
from contextlib import contextmanager
import json
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


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Origin check against ANTHOSWEB_URL
# ─────────────────────────────────────────────────────────────────────────────
def is_origin_allowed(origin: str | None) -> bool:
    """
    Check whether the WebSocket client's Origin header is allowed.
    If origin is absent (CLI tools, tests), it is allowed.
    If present, it must match one of the settings.cors_origins entries.
    """
    if not origin:
        return True
    allowed = settings.cors_origins
    if "*" in allowed:
        return True
    return origin.strip().rstrip("/") in allowed


# ─────────────────────────────────────────────────────────────────────────────
# Helper: safe send that swallows errors if the connection is already closed
# ─────────────────────────────────────────────────────────────────────────────
async def safe_send_json(websocket: WebSocket, data: dict) -> bool:
    """
    Attempt to send JSON over WebSocket. Returns True on success, False if
    the connection is already closed (swallows RuntimeError / disconnect).
    This prevents the 'Cannot call send once a close message has been sent' crash.
    """
    try:
        await websocket.send_json(data)
        return True
    except (RuntimeError, WebSocketDisconnect):
        # Connection already closed — nothing to send to
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Helper: database session for WebSocket (cannot use FastAPI Depends)
# ─────────────────────────────────────────────────────────────────────────────
@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for a database session outside of FastAPI Depends.
    Guarantees the session is closed when the block exits.
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


# ─────────────────────────────────────────────────────────────────────────────
# Shared analysis logic used by both WebSocket and HTTP POST
# ─────────────────────────────────────────────────────────────────────────────
async def execute_email_analysis(payload: AnalyseRequest, db: Session) -> list[dict]:
    """
    Core business logic — fetches categories from DB, resolves the model,
    and runs the LangGraph workflow.  Shared by WS and HTTP handlers.
    """
    # Fetch all user-defined categories from the database
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

    # Look up the model in the database (by id or name)
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

    # Run the multi-agent LangGraph workflow
    results = await workflow.gather_emails(
        incoming_emails=payload.emails,
        incoming_user_defined_categories=categories,
        model_type=model_info,
    )
    return results


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket endpoint — ONE request per connection, no looping
# ─────────────────────────────────────────────────────────────────────────────
@router.websocket("/analyse")
@router.websocket("/analyze")
async def websocket_analyse(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time email analysis on /analyse.

    Lifecycle (exactly ONE request per connection):
      1. Origin check against ANTHOSWEB_URL → reject with 1008 if unauthorized.
      2. Accept the handshake.
      3. Wait for exactly ONE JSON message (AnalyseRequest).
      4. Send immediate confirmation.
      5. Stream real-time log messages as the LangGraph pipeline runs.
      6. Send final results (type: "complete").
      7. Close the WebSocket cleanly.
    """

    # ── Step 0: origin verification ──────────────────────────────────────
    origin = websocket.headers.get("origin")
    if not is_origin_allowed(origin):
        logger.warning("Rejected WS from unauthorized origin: %s", origin)
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Origin not allowed"
        )
        return

    # ── Step 1: accept connection ────────────────────────────────────────
    await websocket.accept()
    logger.info("WebSocket /analyse accepted (origin: %s)", origin or "direct")

    try:
        # ── Step 2: receive exactly ONE request ──────────────────────────
        try:
            raw_message = await websocket.receive_text()
        except WebSocketDisconnect:
            logger.info("Client disconnected before sending payload")
            return

        # ── Step 3: validate the payload ─────────────────────────────────
        try:
            payload = AnalyseRequest.model_validate_json(raw_message)
        except (ValidationError, ValueError, json.JSONDecodeError) as err:
            logger.warning("Invalid payload on WebSocket: %s", err)
            await safe_send_json(websocket, {
                "type": "error",
                "status": "error",
                "message": "Invalid request payload",
                "detail": str(err),
            })
            return

        # ── Step 4: immediate confirmation ───────────────────────────────
        sent = await safe_send_json(websocket, {
            "type": "confirmation",
            "status": "confirmed",
            "message": f"Analysis confirmed for {len(payload.emails)} email(s). Processing started.",
            "email_count": len(payload.emails),
            "model_name": payload.model.name,
        })
        if not sent:
            logger.info("Client disconnected right after sending payload")
            return

        logger.info("Confirmed analysis for %d email(s)", len(payload.emails))

        # ── Step 5: bind log queue + start log streamer ──────────────────
        log_queue: asyncio.Queue = asyncio.Queue()
        token = current_log_queue.set(log_queue)

        # Flag to track if connection is still alive
        connection_alive = True

        async def stream_logs() -> None:
            """Forward queued log items to the WebSocket until sentinel None."""
            nonlocal connection_alive
            try:
                while True:
                    item = await log_queue.get()
                    if item is None:
                        # Sentinel — processing is done
                        log_queue.task_done()
                        break
                    if connection_alive:
                        ok = await safe_send_json(websocket, item)
                        if not ok:
                            connection_alive = False
                    log_queue.task_done()
            except Exception:
                # Silently stop streaming if anything goes wrong
                connection_alive = False

        log_task = asyncio.create_task(stream_logs())

        # ── Step 6: run the analysis ─────────────────────────────────────
        try:
            with get_db_session() as db:
                results = await execute_email_analysis(payload=payload, db=db)

            # Signal the log streamer to finish and wait for it
            await log_queue.put(None)
            await log_task

            # ── Step 7: send final results ───────────────────────────────
            if connection_alive:
                await safe_send_json(websocket, {
                    "type": "complete",
                    "status": "completed",
                    "results": results,
                })
                logger.info("Delivered results for %d email(s) over WS", len(payload.emails))

        except Exception as exc:
            logger.exception("Analysis failed on WebSocket: %s", exc)
            # Stop log streamer
            await log_queue.put(None)
            if not log_task.done():
                await log_task
            # Try to notify the client
            if connection_alive:
                await safe_send_json(websocket, {
                    "type": "error",
                    "status": "error",
                    "message": "Failed to analyze emails",
                    "detail": str(exc),
                })
        finally:
            # Always reset the context var to avoid leaking the queue
            current_log_queue.reset(token)

    except WebSocketDisconnect:
        logger.info("WebSocket /analyse connection closed by client")
    except Exception as exc:
        logger.exception("Unexpected error in WS /analyse: %s", exc)
    finally:
        # ── Step 8: close the connection from server side ────────────────
        # This ensures the frontend knows the transaction is done and
        # prevents it from thinking the connection is still open.
        try:
            await websocket.close()
        except Exception:
            pass  # Already closed — that's fine


# ─────────────────────────────────────────────────────────────────────────────
# HTTP POST endpoint — fallback for non-WebSocket clients
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/analyze",
    response_model=AnalyseResponse,
    summary="Analyze a batch of emails",
)
@router.post(
    "/analyse",
    response_model=AnalyseResponse,
    summary="Analyse a batch of emails",
    include_in_schema=False,
)
async def analyze(
    payload: AnalyseRequest, db: Session = Depends(get_db)
) -> AnalyseResponse:
    """
    HTTP POST endpoint for email analysis.
    Serves as fallback when WebSocket is unavailable.
    """
    try:
        results = await execute_email_analysis(payload=payload, db=db)
        return AnalyseResponse(results=results)
    except Exception as exc:
        logger.exception("Analysis failed on HTTP POST: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(exc)}",
        )



