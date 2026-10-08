from collections import deque
from time import monotonic

_requests = {}
_last_cleanup = 0.0


def is_rate_limited(user_id, scope, limit, window_seconds):
    global _last_cleanup
    now = monotonic()

    if now - _last_cleanup >= 60:
        cutoff = now - 60
        for key, timestamps in list(_requests.items()):
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if not timestamps:
                del _requests[key]
        _last_cleanup = now

    key = (str(user_id), scope)
    timestamps = _requests.setdefault(key, deque())
    cutoff = now - window_seconds
    while timestamps and timestamps[0] <= cutoff:
        timestamps.popleft()

    if len(timestamps) >= limit:
        return True
    timestamps.append(now)
    return False
