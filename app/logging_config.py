import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """
    Configure the root logger once, at application startup.

    Every other module just does `logger = logging.getLogger(__name__)`
    and inherits this configuration - no per-file setup needed.
    """
    root_logger = logging.getLogger()

    if root_logger.handlers:
        # Already configured - avoid attaching duplicate handlers if this
        # gets imported/called more than once (e.g. under a test runner/reload).
        return

    root_logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)