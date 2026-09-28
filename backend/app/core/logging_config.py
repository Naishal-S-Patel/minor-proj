"""
Structured logging setup.

Why not just use print()?
    print() statements can't be filtered by severity, can't be redirected to
    log aggregation tools (Datadog, CloudWatch, etc.), and give you no
    context (timestamp, module, log level) for free. In production, when
    something breaks at 3am, you want logs that tell you *when*, *where*,
    and *how severe* — not just a bare message.

This configures Python's built-in `logging` module once, at startup, with a
consistent format across the whole app. Every module gets its own named
logger via `logging.getLogger(__name__)`, which lets you trace exactly which
file/module emitted a given line.
"""

import logging
import sys

from app.core.config import settings


def configure_logging() -> None:
    """
    Call this once, at application startup (see main.py).

    Sets the root logger level based on environment: verbose (DEBUG) in
    development, quieter (INFO) in production to avoid noisy/expensive logs.
    """
    log_level = logging.DEBUG if settings.debug else logging.INFO

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Quiet down noisy third-party loggers so our own logs aren't drowned out.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)
