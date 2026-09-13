import logging
from collections import deque

LOG_BUFFER: deque[str] = deque(maxlen=100)

TELEGRAM_MAX_MESSAGE_LENGTH = 4000


class BufferHandler(logging.Handler):
    def emit(self, record):
        try:
            LOG_BUFFER.append(self.format(record))
        except Exception:
            self.handleError(record)


def get_recent_logs(lines: int = 100, max_chars: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> str:
    recent = list(LOG_BUFFER)[-lines:]
    text = "\n".join(recent)
    if len(text) <= max_chars:
        return text
    truncated = text[-max_chars:]
    index = truncated.find("\n")
    return "...\n" + truncated[index + 1 :] if index >= 0 else "..." + truncated
