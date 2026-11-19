"""
=============================================================================
                     LOGGING & AUDITING INFRASTRUCTURE
=============================================================================

Production-grade logging:
  - Formatted console stream for real-time visibility.
  - Persistent file handler (`agent_audit.log`) for production audit trails.
=============================================================================
"""

import logging
import sys


def setup_logger(name: str = "agentic_arena", log_file: str = "agent_audit.log") -> logging.Logger:
    """Configures a thread-safe, structured logger with console and file handlers."""
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.INFO)

    # 1. File Handler: Comprehensive audit log with timestamps
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_format)
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    # 2. Console Handler: Clean, user-friendly real-time output
    console_handler = logging.StreamHandler(sys.stdout)
    console_format = logging.Formatter("[%(levelname)s] %(message)s")
    console_handler.setFormatter(console_format)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    return logger


# Global application logger
log = setup_logger()
