#!/usr/bin/env python3
"""Build a public article-to-atom count index from the private CLAT bank.

The output intentionally contains only subject, law name, article number, and
counts. It must not include prompts, answers, explanations, or references.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(r"C:\cowork\lawinus.org\02_비공개데이터\private_problem_banks\current\ox_clat_unified_v001.json")
DEFAULT_OUT = REPO_ROOT / "assets" / "article_atom_counts.json"
ARTICLE_RE = re.compile(r"\uc81c\s*(\d+)\s*\uc870(?:\s*\uc758\s*(\d+)|\uc758\s*(\d+))?")


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_article_no(value: str) -> str:
    value = re.sub(r"\s+", "", value or "")
    match = ARTICLE_RE.search(value)
    if not match:
        return ""
    sub = match.group(2) or match.group(3)
    return f"\uc81c{match.group(1)}\uc870\uc758{sub}" if sub else f"\uc81c{match.group(1)}\uc870"


def article_norms(*values: Any) -> list[str]:
    out: list[str] = []
    for value in values:
        text = clean_text(value)
        for match in ARTICLE_RE.finditer(text):
            sub = match.group(2) or match.group(3)
            norm = f"\uc81c{match.group(1)}\uc870\uc758{sub}" if sub else f"\uc81c{match.group(1)}\uc870"
            if norm not in out:
                out.append(norm)
    return out


def law_name_from_article(article: str, subject: str) -> str:
    article = clean_text(article)
    subject = clean_text(subject)
    split = ARTICLE_RE.split(article, maxsplit=1)
    prefix = clean_text(split[0] if split else "")
    prefix = re.sub(r"[\u00b7,;:>\-]\s*$", "", prefix).strip()
    return prefix or subject


def primary_article_refs(item: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return only article refs that should place an atom on an article page.

    Do not scan explanatory references here. For example, a 민법 atom can cite
    "가등기담보법 제1조" in its reference text, but that should not make the
    atom badge appear on 민법 제1조.
    """
    subject = clean_text(item.get("subject"))
    refs: list[tuple[str, str, str]] = []

    for raw in item.get("articleRefs") or []:
        if isinstance(raw, dict):
            law_name = clean_text(raw.get("lawName") or raw.get("law_name") or subject)
            article_no = normalize_article_no(clean_text(raw.get("articleNo") or raw.get("article_no") or raw.get("article")))
            if subject and law_name and article_no:
                refs.append((subject, law_name, article_no))
        else:
            text = clean_text(raw)
            law_name = law_name_from_article(text, subject)
            for article_no in article_norms(text):
                if subject and law_name and article_no:
                    refs.append((subject, law_name, article_no))

    if refs:
        return list(dict.fromkeys(refs))

    article = clean_text(item.get("art") or item.get("article"))
    if not subject or not article:
        return []
    law_name = law_name_from_article(article, subject)
    return [(subject, law_name, article_no) for article_no in article_norms(article)]


def atom_weight(item: dict[str, Any]) -> int:
    count = 1 if clean_text(item.get("rep")) else 0
    for twin in item.get("twins") or []:
        if clean_text(twin.get("q")):
            count += 1
    return max(count, 1)


def build_counts(source: Path) -> dict[str, Any]:
    data = json.loads(source.read_text(encoding="utf-8"))
    counts: Counter[tuple[str, str, str]] = Counter()
    skipped = 0

    for item in data.get("items") or []:
        if item.get("active") is False:
            skipped += 1
            continue
        refs = primary_article_refs(item)
        if not refs:
            skipped += 1
            continue
        weight = atom_weight(item)
        for subject, law_name, article_no in refs:
            counts[(subject, law_name, article_no)] += weight

    rows = [
        {
            "subject": subject,
            "law_name": law_name,
            "article_no": article_no,
            "count": count,
        }
        for (subject, law_name, article_no), count in counts.items()
    ]
    rows.sort(key=lambda r: (r["subject"], r["law_name"], int(re.search(r"\d+", r["article_no"]).group(0)), r["article_no"]))

    return {
        "schemaVersion": 1,
        "source": source.name,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceUpdatedAt": data.get("updatedAt"),
        "itemCount": len(data.get("items") or []),
        "mappedArticleCount": len(rows),
        "skippedItemCount": skipped,
        "totalAtomRefs": sum(r["count"] for r in rows),
        "items": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    payload = build_counts(args.source)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ["itemCount", "mappedArticleCount", "skippedItemCount", "totalAtomRefs"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
