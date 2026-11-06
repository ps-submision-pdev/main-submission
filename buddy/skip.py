"""Skip known material, but only on evidence strong enough.

should_skip(profile, topic) -> {skip, why, fact_ids}
A topic is skipped only if its best supporting fact has trust >= skip_threshold (config/trust.yaml, 0.7).
A self-declared topic (0.4) is not enough: the student answers the check questions (buddy/checks.py),
and a pass adds a "tested" fact (0.7).
"""
from __future__ import annotations

import yaml

from buddy.profile import TRUST_FILE, supports


def should_skip(profile: dict, topic: str) -> dict:
    threshold = yaml.safe_load(TRUST_FILE.read_text(encoding="utf-8"))["skip_threshold"]
    found = supports(profile, topic)
    if not found["fact_ids"]:
        return {"skip": False, "why": "no fact supports this topic", "fact_ids": []}
    if found["best_trust"] >= threshold:
        return {"skip": True, "why": f"supported with trust {found['best_trust']} (at least {threshold})",
                "fact_ids": found["fact_ids"]}
    return {"skip": False, "why": "self-declared, not enough to skip: ask check questions",
            "fact_ids": found["fact_ids"]}
