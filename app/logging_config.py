import asyncio
import contextvars
from datetime import datetime, timezone
import logging
import sys
from typing import Optional

# Context variable that holds an asyncio.Queue for the active WebSocket request in the current async context
current_log_queue: contextvars.ContextVar[Optional[asyncio.Queue]] = contextvars.ContextVar(
    "current_log_queue", default=None
)


class WebSocketLogHandler(logging.Handler):
    """
    Custom logging handler that intercepts log records and forwards them
    as structured payloads to an asyncio.Queue associated with the current
    WebSocket connection via contextvars.
    """

    def emit(self, record: logging.LogRecord) -> None:
        queue = current_log_queue.get()
        if queue is not None:
            try:
                # Format log message as a structured event for the frontend
                log_item = {
                    "type": "log",
                    "status": "processing",
                    "level": record.levelname,
                    "name": record.name,
                    "message": record.getMessage(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                queue.put_nowait(log_item)
            except Exception:
                # Never allow logging errors to break application execution
                pass


def setup_logging(level: int = logging.INFO) -> None:
    """
    Configure the root logger once, at application startup.

    Every other module just does `logger = logging.getLogger(__name__)`
    and inherits this configuration - no per-file setup needed.
    """
    root_logger = logging.getLogger()

    # Ensure root logger captures at least INFO level messages
    if root_logger.level == logging.NOTSET or root_logger.level > level:
        root_logger.setLevel(level)

    # Attach WebSocketLogHandler so all module logs are captured for active WebSocket requests
    has_ws_handler = any(isinstance(h, WebSocketLogHandler) for h in root_logger.handlers)
    if not has_ws_handler:
        ws_handler = WebSocketLogHandler()
        ws_handler.setLevel(level)
        root_logger.addHandler(ws_handler)

    # Standard console handler (keeps printing to console)
    has_stream_handler = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, WebSocketLogHandler)
        for h in root_logger.handlers
    )
    if not has_stream_handler:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
