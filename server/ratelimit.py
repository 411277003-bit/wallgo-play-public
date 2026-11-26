"""簡單的失敗次數限制（防止暴力猜密碼、猜救援碼）。存在記憶體，伺服器重啟就清空。"""
import time


class FailureLimiter:
    def __init__(self, max_failures, window_seconds):
        self.max_failures = max_failures
        self.window = window_seconds
        self._fails = {}   # key → [失敗時間, ...]

    def _recent(self, key):
        now = time.monotonic()
        recent = [t for t in self._fails.get(key, []) if now - t < self.window]
        if recent:
            self._fails[key] = recent
        else:
            self._fails.pop(key, None)
        return recent

    def blocked(self, key):
        return len(self._recent(key)) >= self.max_failures

    def fail(self, key):
        self._recent(key)
        self._fails.setdefault(key, []).append(time.monotonic())

    def reset(self, key=None):
        if key is None:
            self._fails.clear()
        else:
            self._fails.pop(key, None)


# 同一個帳號 10 分鐘內最多錯 5 次
login_limiter = FailureLimiter(5, 600)
reset_limiter = FailureLimiter(5, 600)
