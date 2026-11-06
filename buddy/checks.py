"""Check questions for a known topic, graded in code. No model is involved.

A check file (data/checks/<topic>.json): {"topic", "pass_mark", "questions": [{question, options, answer}]}
where answer is the index of the right option. grade(check, answers) counts correct answers; a pass is
score >= pass_mark. record_check() grades and, on a pass, adds a "tested" fact (trust 0.7) for the topic.
A check whose questions are not written yet (empty question or options) refuses to grade, so an empty
stub can never produce a pass.
"""
from __future__ import annotations

import json
from pathlib import Path

from buddy.profile import add_fact


class CheckError(ValueError):
    pass


def load_check(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def grade(check: dict, answers: list) -> dict:
    questions = check["questions"]
    if not questions or any(not q["question"].strip() or len(q["options"]) < 2 for q in questions):
        raise CheckError(f"the check for {check['topic']!r} has no written questions yet")
    if len(answers) != len(questions):
        raise CheckError(f"expected {len(questions)} answers, got {len(answers)}")
    score = sum(a == q["answer"] for a, q in zip(answers, questions))
    return {"topic": check["topic"], "score": score, "total": len(questions), "passed": score >= check["pass_mark"]}


def record_check(profile: dict, check: dict, answers: list, now: str | None = None) -> dict:
    result = grade(check, answers)
    if result["passed"]:
        result["fact"] = add_fact(profile, "known_topic", check["topic"], "tested", now)
    return result
