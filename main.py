#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
BOOTSTRAP_RETRIES = 5


def setup_logging(level: str) -> None:
    from logs_buffer import BufferHandler

    logging.basicConfig(level=level, format=LOG_FORMAT, datefmt=DATE_FORMAT)
    buffer_handler = BufferHandler()
    buffer_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    logging.getLogger().addHandler(buffer_handler)


def main() -> None:
    from telegram import Update

    from app import build_application
    from config import config

    setup_logging(config.log_level)
    logging.getLogger(__name__).info("bot starting")
    build_application().run_polling(
        allowed_updates=Update.ALL_TYPES,
        bootstrap_retries=BOOTSTRAP_RETRIES,
        poll_interval=config.poll_interval,
    )


if __name__ == "__main__":
    main()
