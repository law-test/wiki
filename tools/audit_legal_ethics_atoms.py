from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILES = [ROOT / "assets" / f"ox_legal_ethics_exam{n}.json" for n in range(1, 16)]

CASE_HANJA = re.compile(r"[\u7532\u4e59\u4e19\u4e01\u620a\u5df1]")
CASE_ALPHA = re.compile(r"(?<![A-Za-z])[A-D](?![A-Za-z+])")
CASE_HANGUL = re.compile(
    r"(?<![\uac00-\ud7a3])(?:\uac11|\uc744|\ubcd1|\uc815)(?:\uc740|\ub294|\uc774|\uac00|\uc758|\uc5d0\uac8c|\uc744|\ub97c|\uacfc|\uc640)"
)
CASE_LIKE = [
    "\uc774 \uc0ac\ub840",
    "\uc704 \uc0ac\ub840",
    "\ud574\ub2f9 \uc0ac\ub840",
    "\uc774 \uc0ac\uc548",
    "\uc704 \uc0ac\uc548",
    "\ud574\ub2f9 \uc0ac\uc548",
    "\uc774 \uacbd\uc6b0",
    "\ub2e4\uc74c \uc911",
    "\uc637\uc740 \uac83\uc740",
    "\uc637\uc9c0 \uc54a\uc740 \uac83\uc740",
    "\ubb34\uc5c7\uc778\uac00",
]
MOJIBAKE = ["\ufffd", "???", "蹂", "踰", "誘", "寃", "媛", "諛", "쨌"]


def text_fields(item: dict):
    base = [
        ("topic", item.get("topic", "")),
        ("rep", item.get("rep", "")),
        ("why", item.get("why", "")),
        ("ref", item.get("ref", "")),
    ]
    for i, twin in enumerate(item.get("twins", [])):
        base.extend(
            [
                (f"twins.{i}.q", twin.get("q", "")),
                (f"twins.{i}.trap", twin.get("trap", "")),
                (f"twins.{i}.why", twin.get("why", "")),
                (f"twins.{i}.corrected", twin.get("corrected", "")),
                (f"twins.{i}.ref", twin.get("ref", "")),
            ]
        )
    return base


def audit():
    issues: dict[str, list[tuple]] = defaultdict(list)
    stats = []
    for path in FILES:
        data = json.loads(path.read_text(encoding="utf-8"))
        per_question = Counter()
        for item in data.get("items", []):
            pid = item.get("pid", "")
            per_question[item.get("sourceQuestionId")] += 1
            if item.get("subject") != "\ubc95\uc870\uc724\ub9ac":
                issues["subject"].append((path.name, pid, item.get("subject")))
            if item.get("answer") not in ("O", None) or item.get("a") not in ("O", None):
                issues["answer"].append((path.name, pid, item.get("answer"), item.get("a")))
            if not item.get("twins"):
                issues["no_twin"].append((path.name, pid))
            for name, text in text_fields(item):
                if name.endswith(".ref") and not text:
                    continue
                if text is None:
                    issues["none_field"].append((path.name, pid, name))
                    continue
                if not isinstance(text, str):
                    issues["non_string"].append((path.name, pid, name, type(text).__name__))
                    continue
                if any(token in text for token in MOJIBAKE):
                    issues["mojibake"].append((path.name, pid, name, text[:220]))
                if "?" in text:
                    issues["question_mark"].append((path.name, pid, name, text[:220]))
                if CASE_HANJA.search(text):
                    issues["case_hanja"].append((path.name, pid, name, text[:220]))
                if CASE_ALPHA.search(text):
                    issues["case_alpha"].append((path.name, pid, name, text[:220]))
                if CASE_HANGUL.search(text) and not any(ok in text for ok in ["\uc815\uc758", "\uc815\uac00", "\ubcd1\uacfc"]):
                    issues["case_hangul"].append((path.name, pid, name, text[:220]))
                if any(token in text for token in CASE_LIKE) and "\uc0ac\ub840\ube44" not in text:
                    issues["case_like"].append((path.name, pid, name, text[:220]))
                if name in ("rep", "twins.0.q") and text and not text.endswith("."):
                    issues["not_sentence"].append((path.name, pid, name, text[:220]))
                if name in ("rep", "twins.0.q") and len(text) > 210:
                    issues["long"].append((path.name, pid, name, len(text), text[:220]))
                if name in ("rep", "twins.0.q"):
                    joints = sum(text.count(token) for token in ["고 ", "며 ", "거나 ", "면서 ", " 또는 ", " 및 "])
                    if joints >= 3:
                        issues["compound_candidate"].append((path.name, pid, name, joints, text[:260]))
        bad_counts = {qid: c for qid, c in per_question.items() if c not in (4, 5)}
        if bad_counts:
            issues["per_question_count"].append((path.name, bad_counts))
        stats.append((path.name, len(data.get("items", [])), len(per_question), min(per_question.values()), max(per_question.values())))
    return stats, issues


def main():
    stats, issues = audit()
    print("STATS")
    for row in stats:
        print(row)
    print("ISSUES")
    for key in sorted(issues):
        rows = issues[key]
        print(f"{key}: {len(rows)}")
        for row in rows[:30]:
            print(" ", row)
    if not issues:
        print("no issues")


if __name__ == "__main__":
    main()
