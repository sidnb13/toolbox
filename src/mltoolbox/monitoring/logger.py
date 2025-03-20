import logging
import os

from dotenv import load_dotenv

load_dotenv(override=True)


logging.basicConfig(level=logging.INFO)


def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())

    return logger
