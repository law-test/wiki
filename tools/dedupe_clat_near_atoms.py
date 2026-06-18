#!/usr/bin/env python3
"""Merge highly similar CLAT atoms so repeated sources are listed together."""

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


DEFAULT_BANK = Path(r"C:\cowork\law-test-private\private_problem_banks\current\ox_clat_unified_v001.json")
REPORT_DIR = Path(r"C:\cowork\law-test-private\private_problem_banks\current")
EXPECTED_WORD = "예상"


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def source_values(item: dict[str, Any]) -> list[str]:
    src = item.get("src") or []
    if isinstance(src, str):
        return [src]
    return [clean_text(value) for value in src if clean_text(value)]


def norm_prompt(text: str) -> str:
    text = clean_text(text)
    return re.sub(r"[\s,.;:·ㆍ･「」『』\[\](){}]", "", text)


def grams(text: str, n: int = 5) -> set[str]:
    if len(text) <= n:
        return {text}
    return {text[idx : idx + n] for idx in range(len(text) - n + 1)}


def push_unique(values: list[Any], incoming: list[Any]) -> list[Any]:
    seen = {json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values}
    for value in incoming:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            values.append(value)
            seen.add(key)
    return values


def merge_atom(target: dict[str, Any], source: dict[str, Any]) -> None:
    target["freq"] = int(target.get("freq") or 1) + int(source.get("freq") or 1)
    for key in ("src", "years", "articleRefs", "ids", "xref"):
        target[key] = push_unique(list(target.get(key) or []), list(source.get(key) or []))
    target["privateSources"] = push_unique(
        list(target.get("privateSources") or []),
        list(source.get("privateSources") or []),
    )
    if not target.get("ref") and source.get("ref"):
        target["ref"] = source["ref"]
    if not target.get("art") and source.get("art"):
        target["art"] = source["art"]
        target["artNo"] = source.get("artNo")
    target["hot"] = bool(target.get("hot") or source.get("hot"))


def target_score(item: dict[str, Any]) -> tuple[int, int, int, int]:
    src = source_values(item)
    has_expected = int(any(EXPECTED_WORD in value for value in src))
    # Prefer the richer source carrier, then the shorter prompt as display text.
    return (has_expected, len(src), int(item.get("freq") or 1), -len(clean_text(item.get("rep"))))


def find_pairs(items: list[dict[str, Any]], threshold: float, min_overlap: float) -> list[tuple[float, dict[str, Any], dict[str, Any]]]:
    index: dict[tuple[str, str, str], list[tuple[dict[str, Any], str, set[str]]]] = defaultdict(list)
    prepared: list[tuple[dict[str, Any], str, set[str]]] = []
    for item in items:
        prompt = norm_prompt(item.get("rep"))
        if len(prompt) < 35:
            continue
        gram_set = grams(prompt)
        entry = (item, prompt, gram_set)
        prepared.append(entry)
        for gram in gram_set:
            index[(clean_text(item.get("subject")), clean_text(item.get("a")), gram)].append(entry)

    pairs: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    seen: set[tuple[int, int]] = set()
    for item, prompt, gram_set in prepared:
        counts: Counter[int] = Counter()
        refs: dict[int, tuple[dict[str, Any], str, set[str]]] = {}
        for gram in gram_set:
            for entry in index.get((clean_text(item.get("subject")), clean_text(item.get("a")), gram), []):
                other = entry[0]
                if other is item:
                    continue
                key = tuple(sorted((id(item), id(other))))
                if key in seen:
                    continue
                counts[id(other)] += 1
                refs[id(other)] = entry
        for other_id, overlap in counts.most_common(60):
            other, other_prompt, other_grams = refs[other_id]
            if abs(len(prompt) - len(other_prompt)) / max(len(prompt), len(other_prompt)) > 0.35:
                continue
            if overlap / max(1, min(len(gram_set), len(other_grams))) < min_overlap:
                continue
            ratio = difflib.SequenceMatcher(None, prompt, other_prompt, autojunk=False).ratio()
            if ratio >= threshold:
                seen.add(tuple(sorted((id(item), id(other)))))
                pairs.append((ratio, item, other))
    pairs.sort(key=lambda item: -item[0])
    return pairs


def dedupe(bank_path: Path, threshold: float, min_overlap: float, backup: bool) -> dict[str, Any]:
    data = json.loads(bank_path.read_text(encoding="utf-8"))
    items = list(data.get("items") or [])
    pairs = find_pairs(items, threshold, min_overlap)
    removed: set[int] = set()
    merges: list[dict[str, Any]] = []
    for ratio, left, right in pairs:
        if id(left) in removed or id(right) in removed:
            continue
        target, source = (left, right) if target_score(left) >= target_score(right) else (right, left)
        merge_atom(target, source)
        removed.add(id(source))
        merges.append(
            {
                "ratio": round(ratio, 6),
                "target": target.get("pid"),
                "removed": source.get("pid"),
                "subject": target.get("subject"),
                "targetSrc": source_values(target),
                "removedSrc": source_values(source),
            }
        )

    if backup and merges:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = bank_path.with_name(bank_path.stem + f".dedupe_backup_{stamp}" + bank_path.suffix)
        shutil.copy2(bank_path, backup_path)

    if merges:
        data["items"] = [item for item in items if id(item) not in removed]
        data["count"] = len(data["items"])
        data["updatedAt"] = datetime.now().isoformat(timespec="seconds")
        data["subjects"] = dict(Counter(clean_text(item.get("subject")) for item in data["items"] if clean_text(item.get("subject"))))
        data["answers"] = dict(Counter(clean_text(item.get("a")) for item in data["items"] if clean_text(item.get("a"))))
        data["layers"] = dict(Counter(clean_text(item.get("sourceLayer")) or "unknown" for item in data["items"]))
        bank_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "bank": str(bank_path),
        "threshold": threshold,
        "minOverlap": min_overlap,
        "merged": len(merges),
        "finalCount": data.get("count"),
        "merges": merges,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "clat_near_atom_dedupe_report_v001.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--threshold", type=float, default=0.982)
    parser.add_argument("--min-overlap", type=float, default=0.75)
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()
    report = dedupe(args.bank, args.threshold, args.min_overlap, backup=not args.no_backup)
    print(f"bank={report['bank']}")
    print(f"merged={report['merged']}")
    print(f"final_count={report['finalCount']}")


if __name__ == "__main__":
    main()
