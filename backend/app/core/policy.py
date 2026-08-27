from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from app.schemas.policy import PolicyRead

POLICY_PATH = Path(__file__).resolve().parents[2] / "policies" / "authorized-use.md"
POLICY_VERSION = "1.0.0"


@lru_cache
def load_policy() -> PolicyRead:
    text = POLICY_PATH.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return PolicyRead(version=POLICY_VERSION, sha256=digest, text=text)
