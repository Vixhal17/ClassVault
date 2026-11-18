import logging
import sys

class SensitiveDataFilter(logging.Filter):
    """Filter out tokens, passwords, and secrets from logs."""
    SENSITIVE_KEYS = ("password", "token", "secret", "authorization", "api_key", "access_key")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            lower_msg = record.msg.lower()
            for key in self.SENSITIVE_KEYS:
                if f"{key}=" in lower_msg or f'"{key}"' in lower_msg:
                    record.msg = "[REDACTED_SENSITIVE_LOG]"
                    break
        return True

def setup_logging():
    logger = logging.getLogger("classvault")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        handler.addFilter(SensitiveDataFilter())
        logger.addHandler(handler)

    return logger

logger = setup_logging()
