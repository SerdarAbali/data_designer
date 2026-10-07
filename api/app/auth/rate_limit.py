from collections import deque
from threading import Lock
from time import monotonic

from app.config import settings


class LoginRateLimiter:
    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = {}
        self._lock = Lock()

    def consume(self, key: str) -> int | None:
        now = monotonic()
        window = settings.login_rate_window_seconds
        with self._lock:
            attempts = self._attempts.setdefault(key, deque())
            while attempts and now - attempts[0] >= window:
                attempts.popleft()
            if len(attempts) >= settings.login_rate_limit:
                return max(1, int(window - (now - attempts[0])))
            attempts.append(now)
            return None

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


login_rate_limiter = LoginRateLimiter()
