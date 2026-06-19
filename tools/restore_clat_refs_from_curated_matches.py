#!/usr/bin/env python3
"""Restore CLAT mock references from very close curated atom matches.

This is deliberately stricter than a general semantic matcher.  It only copies
article/case references when a mock atom is almost the same sentence as an
already curated CLAT atom in the same subject with the same O/X answer.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


PRIVATE_ROOT = Path(r"C:\cowork\law-test-private")
DEFAULT_CURRENT = PRIVATE_ROOT / "private_problem_banks" / "current" / "ox_clat_unified_v001.json"
REPORT_ROOT = PRIVATE_ROOT / "reports"

KEEP_RE = re.compile(r"[^0-9A-Za-z\uAC00-\uD7A3]")

LAW_NAMES = [
    "\uBBFC\uC0AC\uC18C\uC1A1\uBC95",
    "\uD615\uC0AC\uC18C\uC1A1\uBC95",
    "\uD5CC\uBC95\uC7AC\uD310\uC18C\uBC95",
    "\uD589\uC815\uC18C\uC1A1\uBC95",
    "\uD589\uC815\uC808\uCC28\uBC95",
    "\uD589\uC815\uAE30\uBCF8\uBC95",
    "\uD589\uC815\uC2EC\uD310\uBC95",
    "\uAD6D\uAC00\uBC30\uC0C1\uBC95",
    "\uD1B5\uC2E0\uBE44\uBC00\uBCF4\uD638\uBC95",
    "\uBBFC\uBC95",
    "\uC0C1\uBC95",
    "\uC5B4\uC74C\uBC95",
    "\uC218\uD45C\uBC95",
    "\uD615\uBC95",
    "\uD5CC\uBC95",
    "\uAC74\uCD95\uBC95",
    "\uACF5\uC9C1\uC120\uAC70\uBC95",
    "\uC131\uD3ED\uB825\uBC94\uC8C4\uC758 \uCC98\uBC8C \uB4F1\uC5D0 \uAD00\uD55C \uD2B9\uB840\uBC95",
    "\uAD6D\uBBFC\uC758 \uD615\uC0AC\uC7AC\uD310 \uCC38\uC5EC\uC5D0 \uAD00\uD55C \uBC95\uB960",
    "\uC9C8\uC11C\uC704\uBC18\uD589\uC704\uADDC\uC81C\uBC95",
]

ALLOWED_LAWS_BY_SUBJECT = {
    "\uBBFC\uBC95": [
        "\uBBFC\uBC95",
        "\uC8FC\uD0DD\uC784\uB300\uCC28\uBCF4\uD638\uBC95",
        "\uC9D1\uD569\uAC74\uBB3C",
        "\uAC00\uB4F1\uAE30\uB2F4\uBCF4",
        "\uBD80\uB3D9\uC0B0\uC2E4\uBA85",
        "\uC0C1\uAC00\uAC74\uBB3C",
    ],
    "\uBBFC\uC0AC\uC18C\uC1A1\uBC95": ["\uBBFC\uC0AC\uC18C\uC1A1\uBC95", "\uBBFC\uC0AC\uC9D1\uD589\uBC95", "\uC18C\uC1A1\uCD09\uC9C4"],
    "\uC0C1\uBC95": ["\uC0C1\uBC95", "\uC5B4\uC74C\uBC95", "\uC218\uD45C\uBC95", "\uBCF4\uD5D8\uC5C5\uBC95", "\uC790\uBCF8\uC2DC\uC7A5"],
    "\uD615\uBC95": ["\uD615\uBC95", "\uD3ED\uB825\uD589\uC704", "\uC131\uD3ED\uB825", "\uC544\uB3D9\uCCAD\uC18C\uB144", "\uD2B9\uC815\uBC94\uC8C4", "\uD2B9\uC815\uACBD\uC81C"],
    "\uD615\uC0AC\uC18C\uC1A1\uBC95": [
        "\uD615\uC0AC\uC18C\uC1A1\uBC95",
        "\uD1B5\uC2E0\uBE44\uBC00\uBCF4\uD638\uBC95",
        "\uAD6D\uBBFC\uC758 \uD615\uC0AC\uC7AC\uD310 \uCC38\uC5EC",
        "\uAD6D\uBBFC\uC758 \uD615\uC0AC\uC7AC\uD310 \uCC38\uC5EC\uC5D0 \uAD00\uD55C \uBC95\uB960",
        "\uAD70\uC0AC\uBC95\uC6D0\uBC95",
    ],
    "\uD5CC\uBC95": ["\uD5CC\uBC95", "\uD5CC\uBC95\uC7AC\uD310\uC18C\uBC95", "\uAD6D\uD68C\uBC95", "\uACF5\uC9C1\uC120\uAC70\uBC95", "\uC815\uB2F9\uBC95"],
    "\uD589\uC815\uBC95": [
        "\uD589\uC815\uC18C\uC1A1\uBC95",
        "\uD589\uC815\uC808\uCC28\uBC95",
        "\uD589\uC815\uAE30\uBCF8\uBC95",
        "\uD589\uC815\uC2EC\uD310\uBC95",
        "\uAD6D\uAC00\uBC30\uC0C1\uBC95",
        "\uACF5\uACF5\uAE30\uAD00\uC758 \uC815\uBCF4\uACF5\uAC1C",
        "\uAC74\uCD95\uBC95",
        "\uC9C0\uBC29\uC790\uCE58\uBC95",
        "\uAD6D\uC138\uAE30\uBCF8\uBC95",
        "\uAD6D\uC138\uC9D5\uC218\uBC95",
        "\uB3C4\uB85C\uAD50\uD1B5\uBC95",
        "\uACF5\uC775\uC0AC\uC5C5",
    ],
}

PRIMARY_REF_PREFIX_BY_SUBJECT = {
    "\uBBFC\uBC95": [
        "\uBBFC\uBC95",
        "\uC8FC\uD0DD\uC784\uB300\uCC28\uBCF4\uD638\uBC95",
        "\uC9D1\uD569\uAC74\uBB3C",
        "\uAC00\uB4F1\uAE30\uB2F4\uBCF4",
        "\uBD80\uB3D9\uC0B0\uC2E4\uBA85",
        "\uC0C1\uAC00\uAC74\uBB3C",
    ],
    "\uBBFC\uC0AC\uC18C\uC1A1\uBC95": ["\uBBFC\uC0AC\uC18C\uC1A1\uBC95", "\uBBFC\uC0AC\uC9D1\uD589\uBC95", "\uC18C\uC1A1\uCD09\uC9C4"],
    "\uC0C1\uBC95": ["\uC0C1\uBC95", "\uC5B4\uC74C\uBC95", "\uC218\uD45C\uBC95"],
    "\uD615\uBC95": ["\uD615\uBC95"],
    "\uD615\uC0AC\uC18C\uC1A1\uBC95": [
        "\uD615\uC0AC\uC18C\uC1A1\uBC95",
        "\uD1B5\uC2E0\uBE44\uBC00\uBCF4\uD638\uBC95",
        "\uAD6D\uBBFC\uC758 \uD615\uC0AC\uC7AC\uD310 \uCC38\uC5EC",
        "\uAD6D\uBBFC\uC758 \uD615\uC0AC\uC7AC\uD310 \uCC38\uC5EC\uC5D0 \uAD00\uD55C \uBC95\uB960",
    ],
    "\uD5CC\uBC95": ["\uD5CC\uBC95", "\uD5CC\uBC95\uC7AC\uD310\uC18C\uBC95", "\uACF5\uC9C1\uC120\uAC70\uBC95"],
    "\uD589\uC815\uBC95": [
        "\uD589\uC815\uC18C\uC1A1\uBC95",
        "\uD589\uC815\uC808\uCC28\uBC95",
        "\uD589\uC815\uAE30\uBCF8\uBC95",
        "\uD589\uC815\uC2EC\uD310\uBC95",
        "\uAD6D\uAC00\uBC30\uC0C1\uBC95",
        "\uACF5\uACF5\uAE30\uAD00\uC758 \uC815\uBCF4\uACF5\uAC1C",
        "\uAC74\uCD95\uBC95",
        "\uC9C0\uBC29\uC790\uCE58\uBC95",
        "\uAD6D\uC138\uAE30\uBCF8\uBC95",
        "\uAD6D\uC138\uC9D5\uC218\uBC95",
        "\uC9C8\uC11C\uC704\uBC18\uD589\uC704\uADDC\uC81C\uBC95",
    ],
}

NEGATION_MARKERS = [
    "\uC54A",
    "\uC544\uB2C8",
    "\uC5C6",
    "\uBABB",
    "\uBD88\uAC00",
    "\uD560\uC218\uC5C6",
    "\uC218\uC5C6",
    "\uC778\uC815\uB418\uC9C0",
    "\uD5C8\uC6A9\uB418\uC9C0",
    "\uC704\uBC18\uB418\uC9C0",
    "\uCE68\uD574\uD558\uC9C0",
    "\uC801\uBC95\uD558\uC9C0",
    "\uC704\uBC95\uD558\uC9C0",
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ").replace("\u3000", " ")).strip()


def norm(value: Any) -> str:
    return KEEP_RE.sub("", clean(value)).lower()


def grams(value: Any, size: int = 2) -> set[str]:
    text = norm(value)
    if len(text) < size:
        return set()
    return {text[index : index + size] for index in range(len(text) - size + 1)}


def words(value: Any) -> set[str]:
    return {norm(part) for part in re.split(r"\s+", str(value or "")) if len(norm(part)) >= 3}


def article_no_number(article_no: Any) -> int | None:
    match = re.search(r"\d+", str(article_no or ""))
    return int(match.group(0)) if match else None


def answer(item: dict[str, Any]) -> str:
    return clean(item.get("a") or item.get("answer"))


def prompt(item: dict[str, Any]) -> str:
    return clean(item.get("rep") or item.get("q") or item.get("prompt"))


def is_missing_mock(item: dict[str, Any]) -> bool:
    return item.get("sourceLayer") == "mock_expected_atom" and not item.get("art") and not item.get("articleRefs")


def has_reference(item: dict[str, Any]) -> bool:
    return bool(item.get("art") or item.get("articleRefs") or item.get("ref"))


def mentioned_laws(text: str) -> list[str]:
    return [law for law in LAW_NAMES if law in text]


def first_mentioned_law(text: str) -> str | None:
    positions = [(text.find(law), law) for law in LAW_NAMES if law in text]
    if not positions:
        return None
    return min(positions, key=lambda pair: pair[0])[1]


def plausible_reference(subject: str, ref: str, art: str) -> bool:
    if not art or not str(art).startswith("\uC81C"):
        return False
    first_law = first_mentioned_law(ref)
    if first_law and first_law not in PRIMARY_REF_PREFIX_BY_SUBJECT.get(subject, []):
        return False
    mentioned = mentioned_laws(ref)
    if not mentioned:
        return True
    allowed = ALLOWED_LAWS_BY_SUBJECT.get(subject, [])
    return any(law in allowed for law in mentioned)


def negation_signature(text: str) -> tuple[int, ...]:
    compact = norm(text)
    return tuple(compact.count(norm(marker)) for marker in NEGATION_MARKERS)


def candidate_targets(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        if item.get("sourceLayer") == "mock_expected_atom" or not has_reference(item):
            continue
        subject = clean(item.get("subject"))
        if not plausible_reference(subject, clean(item.get("ref")), clean(item.get("art"))):
            continue
        text = prompt(item)
        if len(norm(text)) < 20:
            continue
        grouped[subject].append(
            {
                "item": item,
                "norm": norm(text),
                "grams": grams(text),
                "words": words(text),
                "answer": answer(item),
                "negation": negation_signature(text),
            }
        )
    return grouped


def best_match(item: dict[str, Any], targets: dict[str, list[dict[str, Any]]], threshold: float) -> dict[str, Any] | None:
    subject = clean(item.get("subject"))
    item_prompt = prompt(item)
    item_norm = norm(item_prompt)
    item_grams = grams(item_prompt)
    item_words = words(item_prompt)
    item_answer = answer(item)
    item_negation = negation_signature(item_prompt)

    best: dict[str, Any] | None = None
    for record in targets.get(subject, []):
        target = record["item"]
        if item_answer != record["answer"]:
            continue
        if item_negation != record["negation"]:
            continue
        union = len(item_grams | record["grams"]) or 1
        jaccard = len(item_grams & record["grams"]) / union
        if jaccard < 0.78:
            continue
        sequence = difflib.SequenceMatcher(None, item_norm, record["norm"]).ratio()
        word_overlap = len(item_words & record["words"]) / max(1, min(len(item_words), len(record["words"])))
        score = 0.55 * sequence + 0.30 * jaccard + 0.15 * word_overlap
        if score < threshold:
            continue
        match = {
            "score": score,
            "sequence": sequence,
            "jaccard": jaccard,
            "wordOverlap": word_overlap,
            "target": target,
        }
        if best is None or score > best["score"]:
            best = match
    return best


def apply_match(item: dict[str, Any], match: dict[str, Any]) -> None:
    target = match["target"]
    item["art"] = target.get("art") or item.get("art")
    item["artNo"] = target.get("artNo") or article_no_number(item.get("art"))
    item["ref"] = target.get("ref") or item.get("ref") or ""
    if target.get("articleRefs"):
        item["articleRefs"] = target.get("articleRefs")
    if not item.get("topic") and target.get("topic"):
        item["topic"] = target.get("topic")
    item.setdefault("restoredRefs", [])
    item["restoredRefs"].append(
        {
            "method": "curated_near_exact",
            "sourcePid": target.get("pid"),
            "score": round(float(match["score"]), 4),
            "createdAt": datetime.now().isoformat(timespec="seconds"),
        }
    )


def normalize_metadata(payload: dict[str, Any]) -> None:
    items = list(payload.get("items") or [])
    payload["items"] = items
    payload["count"] = len(items)
    payload["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    payload["subjects"] = dict(Counter(clean(item.get("subject")) for item in items if clean(item.get("subject"))))
    payload["answers"] = dict(Counter(answer(item) for item in items if answer(item)))
    payload["layers"] = dict(Counter(clean(item.get("sourceLayer")) or "unknown" for item in items))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument("--report-root", type=Path, default=REPORT_ROOT)
    parser.add_argument("--threshold", type=float, default=0.90)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    payload = load_json(args.current)
    items = list(payload.get("items") or [])
    targets = candidate_targets(items)

    matches: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not is_missing_mock(item):
            continue
        match = best_match(item, targets, args.threshold)
        if match is None:
            continue
        target = match["target"]
        matches.append(
            {
                "index": index,
                "pid": item.get("pid"),
                "subject": item.get("subject"),
                "answer": answer(item),
                "prompt": prompt(item),
                "targetPid": target.get("pid"),
                "targetPrompt": prompt(target),
                "art": target.get("art"),
                "ref": target.get("ref"),
                "targetYears": target.get("years") or target.get("src"),
                "score": round(float(match["score"]), 4),
                "sequence": round(float(match["sequence"]), 4),
                "jaccard": round(float(match["jaccard"]), 4),
                "wordOverlap": round(float(match["wordOverlap"]), 4),
            }
        )
        if args.apply:
            apply_match(item, match)

    if args.apply:
        backup = args.current.with_name(
            args.current.stem
            + f".curated_ref_restore_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            + args.current.suffix
        )
        shutil.copy2(args.current, backup)
        normalize_metadata(payload)
        write_json(args.current, payload)
    else:
        backup = None

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.report_root.mkdir(parents=True, exist_ok=True)
    report_json = args.report_root / f"clat_curated_ref_restore_{stamp}.json"
    report_md = args.report_root / f"clat_curated_ref_restore_{stamp}.md"
    report = {
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "apply": args.apply,
        "threshold": args.threshold,
        "current": str(args.current),
        "backup": str(backup) if backup else None,
        "matched": len(matches),
        "matchedBySubject": dict(Counter(match["subject"] for match in matches)),
        "samples": matches[:200],
    }
    write_json(report_json, report)

    lines = [
        "# CLAT Curated Reference Restore",
        "",
        f"- Created: {report['createdAt']}",
        f"- Apply: {args.apply}",
        f"- Threshold: {args.threshold}",
        f"- Matched: {len(matches):,}",
        f"- Backup: {report['backup'] or '-'}",
        "",
        "## Matched By Subject",
        "",
    ]
    for subject, count in Counter(match["subject"] for match in matches).most_common():
        lines.append(f"- {subject}: {count:,}")
    lines.extend(["", "## Samples", ""])
    for match in matches[:30]:
        lines.append(
            f"- {match['subject']} {match['pid']} -> {match['art']} / {match['targetPid']} "
            f"(score {match['score']})"
        )
        lines.append(f"  - {match['prompt'][:180]}")
        lines.append(f"  - ref: {match['ref']}")
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"curated_ref_restore apply={args.apply} matched={len(matches)} report={report_md}")


if __name__ == "__main__":
    main()
