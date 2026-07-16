---
name: Ping NoneType bug
description: consecutive_failures can be None despite column default=0.
---

## Rule
In `_check_device` (ping_engine.py), when incrementing consecutive_failures, always guard:
```python
current_failures = ping_status.consecutive_failures or 0
ping_status.consecutive_failures = current_failures + 1
```

**Why:** SQLAlchemy Column(default=0) applies when inserting via `db.add()` only after flush/commit. If you create PingStatus in memory and immediately read the field before the first commit, it returns None.

**How to apply:** Any new code that reads PingStatus.consecutive_failures before a DB round-trip should use `or 0`.
