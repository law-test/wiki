#!/usr/bin/env python3
"""Restore missing CLAT mock atom article references with high-precision rules.

This tool is intentionally conservative.  It only fills an article reference
when the atom prompt itself contains a substantial part of the statute article
body.  Keyword-only guesses are reported as candidates but are not applied.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(r"C:\cowork\lawinus.org\01_공개배포_repo")
PRIVATE_ROOT = Path(r"C:\cowork\lawinus.org\02_비공개데이터")
DEFAULT_CURRENT = PRIVATE_ROOT / "private_problem_banks" / "current" / "ox_clat_unified_v001.json"
REPORT_ROOT = PRIVATE_ROOT / "reports"

ARTICLE_SOURCES = [
    REPO_ROOT / "migration_out" / "civil_law_legacy_sections.json",
    REPO_ROOT / "assets" / "civil_procedure_articles.json",
    REPO_ROOT / "assets" / "commercial_law_articles.json",
    PRIVATE_ROOT / "public_criminal_laws" / "law_subject_articles.json",
]

HANGUL_KEEP_RE = re.compile(r"[^0-9A-Za-z\uAC00-\uD7A3]")
ARTICLE_HEADING_RE = re.compile(r"^\s*제\s*\d+\s*조(?:의\s*\d+)?\s*(?:\([^)]*\))?")
BRACKET_NOTE_RE = re.compile(r"\[[^\]]+\]")
SENTENCE_SPLIT_RE = re.compile(r"[\n。.;]+|(?<=다)\s+")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    return re.sub(r"\s+", " ", text).strip()


def norm(value: Any) -> str:
    return HANGUL_KEEP_RE.sub("", clean(value)).lower()


def article_no_number(article_no: Any) -> int | None:
    match = re.search(r"\d+", str(article_no or ""))
    return int(match.group(0)) if match else None


def load_article_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in ARTICLE_SOURCES:
        payload = load_json(path)
        items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            continue
        rows.extend(row for row in items if isinstance(row, dict))
    return rows


def article_units(row: dict[str, Any]) -> list[str]:
    body = clean(row.get("body"))
    body = ARTICLE_HEADING_RE.sub("", body).strip()
    body = BRACKET_NOTE_RE.sub(" ", body)

    units: list[str] = []
    full = norm(body)
    if len(full) >= 24:
        units.append(full)

    for sentence in SENTENCE_SPLIT_RE.split(body):
        sentence_norm = norm(sentence)
        if len(sentence_norm) >= 24:
            units.append(sentence_norm)

    # A title-only match is too weak, so titles are not included as units.
    return sorted(set(units), key=len, reverse=True)


def build_article_index() -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in load_article_rows():
        subject = clean(row.get("subject"))
        if not subject:
            continue
        units = article_units(row)
        if not units:
            continue
        index[subject].append({"row": row, "units": units})
    return index


def is_target_mock(item: dict[str, Any]) -> bool:
    if item.get("sourceLayer") != "mock_expected_atom":
        return False
    return not item.get("art") and not item.get("articleRefs")


def find_body_match(item: dict[str, Any], article_index: dict[str, list[dict[str, Any]]]) -> tuple[dict[str, Any], str] | None:
    prompt_norm = norm(item.get("rep") or item.get("q"))
    if len(prompt_norm) < 24:
        return None

    matches: list[tuple[dict[str, Any], str]] = []
    for rec in article_index.get(clean(item.get("subject")), []):
        row = rec["row"]
        for unit in rec["units"]:
            # Statute-body matches only.  Short prompt contained in a long
            # article is accepted only when it is reasonably specific.
            if unit in prompt_norm or (len(prompt_norm) <= 130 and prompt_norm in unit):
                matches.append((row, unit))
                break

    if not matches:
        return None

    unique: dict[tuple[str, str], tuple[dict[str, Any], str]] = {}
    for row, unit in matches:
        unique[(clean(row.get("article_no")), clean(row.get("title")))] = (row, unit)
    if len(unique) != 1:
        return None
    return next(iter(unique.values()))


def apply_article(item: dict[str, Any], row: dict[str, Any]) -> None:
    law_name = clean(row.get("law_name") or row.get("subject"))
    article_no = clean(row.get("article_no"))
    ref = f"{law_name} {article_no}".strip()
    item["art"] = article_no
    item["artNo"] = article_no_number(article_no)
    item["ref"] = ref
    item["articleRefs"] = [ref]

    why = clean(item.get("why"))
    if why and ref not in why:
        item["why"] = f"{why} 근거 조문: {ref}."
    elif not why:
        item["why"] = f"근거 조문: {ref}."


def normalize_metadata(payload: dict[str, Any]) -> None:
    items = list(payload.get("items") or [])
    payload["items"] = items
    payload["count"] = len(items)
    payload["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    payload["subjects"] = dict(Counter(clean(item.get("subject")) for item in items if clean(item.get("subject"))))
    payload["answers"] = dict(Counter(clean(item.get("a")) for item in items if clean(item.get("a"))))
    payload["layers"] = dict(Counter(clean(item.get("sourceLayer")) or "unknown" for item in items))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument("--report-root", type=Path, default=REPORT_ROOT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    payload = load_json(args.current)
    items = list(payload.get("items") or [])
    article_index = build_article_index()

    matches: list[dict[str, Any]] = []
    unresolved_by_subject: Counter[str] = Counter()
    for index, item in enumerate(items):
        if not is_target_mock(item):
            continue
        result = find_body_match(item, article_index)
        if result is None:
            unresolved_by_subject[clean(item.get("subject"))] += 1
            continue
        row, unit = result
        matches.append(
            {
                "index": index,
                "pid": item.get("pid"),
                "subject": item.get("subject"),
                "answer": item.get("a"),
                "article": row.get("article_no"),
                "title": row.get("title"),
                "lawName": row.get("law_name"),
                "prompt": item.get("rep"),
                "matchedUnit": unit[:180],
            }
        )
        if args.apply:
            apply_article(item, row)

    if args.apply:
        backup = args.current.with_name(
            args.current.stem + f".article_ref_restore_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}" + args.current.suffix
        )
        shutil.copy2(args.current, backup)
        normalize_metadata(payload)
        write_json(args.current, payload)
    else:
        backup = None

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.report_root.mkdir(parents=True, exist_ok=True)
    report_json = args.report_root / f"clat_mock_article_ref_restore_{stamp}.json"
    report_md = args.report_root / f"clat_mock_article_ref_restore_{stamp}.md"

    report = {
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "apply": args.apply,
        "current": str(args.current),
        "backup": str(backup) if backup else None,
        "articleSourceCounts": {subject: len(rows) for subject, rows in sorted(article_index.items())},
        "matched": len(matches),
        "matchedBySubject": dict(Counter(match["subject"] for match in matches)),
        "unresolvedBySubject": dict(unresolved_by_subject),
        "samples": matches[:200],
    }
    write_json(report_json, report)

    lines = [
        "# CLAT Mock Article Reference Restore",
        "",
        f"- Created: {report['createdAt']}",
        f"- Apply: {args.apply}",
        f"- Matched: {len(matches):,}",
        f"- Backup: {report['backup'] or '-'}",
        "",
        "## Matched By Subject",
        "",
    ]
    for subject, count in Counter(match["subject"] for match in matches).most_common():
        lines.append(f"- {subject}: {count:,}")
    lines.extend(["", "## Still Unresolved By Subject", ""])
    for subject, count in unresolved_by_subject.most_common():
        lines.append(f"- {subject}: {count:,}")
    lines.extend(["", "## Samples", ""])
    for match in matches[:30]:
        prompt = clean(match["prompt"])
        if len(prompt) > 180:
            prompt = prompt[:177] + "..."
        lines.append(f"- {match['subject']} {match['pid']} -> {match['lawName']} {match['article']} ({match['title']})")
        lines.append(f"  - {prompt}")
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"article_ref_restore apply={args.apply} matched={len(matches)} report={report_md}")


if __name__ == "__main__":
    main()
