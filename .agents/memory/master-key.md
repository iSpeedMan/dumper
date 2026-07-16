---
name: Master key auto-generation
description: How Dumper handles missing encryption master key on first run.
---

## Rule
In `lifespan()` (main.py), before `init_db()`, call `_ensure_master_key()`.
If `settings.encryption.master_key.startswith("CHANGE_ME")`, generate `os.urandom(32)` encoded as urlsafe_b64, write back to config.yaml by string replacement, and reset `app.crypto._KEY_CACHE = None` so the next call to `_get_key()` re-derives from the new value.

**Why:** Avoids the 500 crash on device edit (decrypt() raises RuntimeError if key not set). Lets the app boot without manual config edit.

**How to apply:** The replacement pattern in config.yaml must match exactly: `master_key: "CHANGE_ME_base64_encoded_32byte_key"`. Any change to that default string in config.yaml must update _ensure_master_key() too.
