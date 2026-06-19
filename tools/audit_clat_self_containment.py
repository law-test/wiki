#!/usr/bin/env python3
"""Audit the private CLAT bank for self-contained O/X atom quality.

The script only reads the private current CLAT JSON and writes private reports.
It does not expose or move the question bank into the public repository.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


PRIVATE_ROOT = Path(r"C:\cowork\law-test-private")
DEFAULT_CURRENT = PRIVATE_ROOT / "private_problem_banks" / "current" / "ox_clat_unified_v001.json"
REPORT_ROOT = PRIVATE_ROOT / "reports"

DEPENDENT_STARTS = (
    "의 ",
    "에 ",
    "에서 ",
    "으로 ",
    "로 ",
    "또한,",
    "다만,",
    "그러나 ",
    "그러면 ",
    "이는 ",
    "이러한 ",
    "위 ",
    "해당 ",
    "같은 ",
    "동법 ",
)

QUESTION_MARKERS = (
    "?",
    "인가",
    "있는가",
    "없는가",
    "어떠한가",
    "가능한가",
    "타당한가",
)

GOOD_ENDS = (
    "다.",
    "한다.",
    "된다.",
    "없다.",
    "있다.",
    "아니다.",
    "못한다.",
    "가능하다.",
    "불가능하다.",
)

EXPLICIT_WRONG_MARKERS = (
    "진술은 틀렸다",
    "진술은 옳지 않다",
    "설문은 틀렸다",
    "설문은 옳지 않다",
    "설명은 틀렸다",
    "설명은 옳지 않다",
    "정답표상 X",
    "정답은 X",
)

EXPLICIT_RIGHT_MARKERS = (
    "진술은 옳다",
    "설문은 옳다",
    "설명은 옳다",
    "정답표상 O",
    "정답은 O",
)

CASE_PARTY_MARKERS = tuple("甲乙丙丁")
META_ANSWER_MARKERS = (
    "지문은 X",
    "지문은 O",
    "본 지문은 X",
    "본 지문은 O",
    "설문은 X",
    "설문은 O",
    "정답은 X",
    "정답은 O",
    "설문은 틀렸다",
    "설문은 옳지 않다",
    "진술은 틀렸다",
    "진술은 옳지 않다",
    "설명은 틀렸다",
    "설명은 옳지 않다",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").replace("\u3000", " ").split())


def strip_trailing_parentheticals(value: str) -> str:
    text = value.strip()
    while True:
        stripped = re.sub(r"\s*\([^()]*\)\s*\.$", ".", text)
        if stripped == text:
            return text
        text = stripped.strip()


def has_good_declarative_end(value: str) -> bool:
    text = value.strip()
    return text.endswith(GOOD_ENDS) or strip_trailing_parentheticals(text).endswith(GOOD_ENDS)


def has_article_ref(item: dict[str, Any]) -> bool:
    return bool(clean(item.get("art")) or item.get("articleRefs") or clean(item.get("ref")))


def private_source_id(item: dict[str, Any]) -> str:
    sources = item.get("privateSources") or []
    if sources and isinstance(sources[0], dict):
        return clean(sources[0].get("id"))
    return ""


def issue_reasons(item: dict[str, Any]) -> list[str]:
    prompt = clean(item.get("rep"))
    why = clean(item.get("why"))
    answer = clean(item.get("a"))
    reasons: list[str] = []

    if not prompt:
        reasons.append("empty_prompt")
    if len(prompt) > 260:
        reasons.append("long_over_260")
    if len(prompt) > 420:
        reasons.append("very_long_over_420")
    if prompt.startswith(DEPENDENT_STARTS):
        reasons.append("dependent_start")
    if any(marker in prompt for marker in QUESTION_MARKERS) or prompt.endswith("?"):
        reasons.append("question_like")
    if prompt.count(".") >= 3 or prompt.count("다.") >= 3:
        reasons.append("multi_sentence")
    if any(marker in prompt for marker in CASE_PARTY_MARKERS):
        reasons.append("case_party_marker")
    if any(marker in prompt for marker in META_ANSWER_MARKERS):
        reasons.append("meta_answer_leak")
    if prompt and not has_good_declarative_end(prompt):
        reasons.append("non_declarative_end")
    if answer == "O" and any(marker in why for marker in EXPLICIT_WRONG_MARKERS):
        reasons.append("answer_o_but_explanation_says_wrong")
    if answer == "X" and any(marker in why for marker in EXPLICIT_RIGHT_MARKERS):
        reasons.append("answer_x_but_explanation_says_right")
    if item.get("sourceLayer") == "mock_expected_atom" and not has_article_ref(item):
        reasons.append("mock_missing_article_ref")

    return reasons


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument("--report-root", type=Path, default=REPORT_ROOT)
    parser.add_argument("--sample-limit", type=int, default=80)
    args = parser.parse_args()

    payload = load_json(args.current)
    items = list(payload.get("items") or [])
    reason_counts: Counter[str] = Counter()
    by_subject: dict[str, Counter[str]] = defaultdict(Counter)
    by_layer: dict[str, Counter[str]] = defaultdict(Counter)
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for index, item in enumerate(items):
        reasons = issue_reasons(item)
        subject = clean(item.get("subject")) or "(none)"
        layer = clean(item.get("sourceLayer")) or "(none)"
        for reason in reasons:
            reason_counts[reason] += 1
            by_subject[subject][reason] += 1
            by_layer[layer][reason] += 1
            if len(samples[reason]) < args.sample_limit:
                samples[reason].append(
                    {
                        "index": index,
                        "pid": item.get("pid"),
                        "subject": subject,
                        "sourceLayer": layer,
                        "answer": item.get("a"),
                        "art": item.get("art"),
                        "sourceId": private_source_id(item),
                        "prompt": clean(item.get("rep")),
                        "why": clean(item.get("why"))[:500],
                    }
                )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.report_root.mkdir(parents=True, exist_ok=True)
    report_json = args.report_root / f"clat_self_containment_audit_{stamp}.json"
    report_md = args.report_root / f"clat_self_containment_audit_{stamp}.md"

    report = {
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "current": str(args.current),
        "totalItems": len(items),
        "reasonCounts": dict(reason_counts),
        "bySubject": {subject: dict(counter) for subject, counter in by_subject.items()},
        "byLayer": {layer: dict(counter) for layer, counter in by_layer.items()},
        "samples": samples,
    }
    write_json(report_json, report)

    lines = [
        "# CLAT Self-Contained Atom Audit",
        "",
        f"- Created: {report['createdAt']}",
        f"- Total items: {len(items):,}",
        "",
        "## Reason Counts",
        "",
    ]
    for reason, count in reason_counts.most_common():
        lines.append(f"- {reason}: {count:,}")

    lines.extend(["", "## By Subject", ""])
    for subject, counter in sorted(by_subject.items()):
        detail = ", ".join(f"{reason}={count:,}" for reason, count in counter.most_common())
        lines.append(f"- {subject}: {detail}")

    lines.extend(["", "## Samples", ""])
    for reason, rows in samples.items():
        lines.append(f"### {reason}")
        for row in rows[:20]:
            prompt = row["prompt"]
            lines.append(f"- {row['subject']} / {row['pid']} / {row['answer']}: {prompt[:220]}")
        lines.append("")
    report_md.write_text("\n".join(lines), encoding="utf-8")

    print(f"self_containment_audit total={len(items)} issues={sum(reason_counts.values())} report={report_md}")


if __name__ == "__main__":
    main()
