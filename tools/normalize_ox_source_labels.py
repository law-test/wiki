# -*- coding: utf-8 -*-
"""Normalize compact exam source labels in OX JSON banks.

Target display examples:
- 변시15 5번 ㄱ
- 법원직25 10번 ㄹ
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets"
OX_FILES = [
    ASSET_DIR / "ox_civil_unified_full_v002.json",
    ASSET_DIR / "ox_msa_unified_v001.json",
]

SOURCE_KEYS = {"source", "src", "years", "refs", "ref"}


def _year_short(year: str) -> str:
    year = str(year or "").strip()
    return year[-2:] if len(year) == 4 and year.startswith("20") else year


def _space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_source_label(value: str) -> str:
    text = str(value or "")
    if not text:
        return text

    text = re.sub(r"변호사시험\s+변시", "변시", text)
    text = re.sub(r"법원직\s+법원직", "법원직", text)

    def repl_bar_long(m: re.Match[str]) -> str:
        round_no, q_no, mark = m.group(1), m.group(2), m.group(3) or ""
        return _space(f"변시{round_no} {q_no}번 {mark}")

    text = re.sub(
        r"(?:변호사시험\s*)?변시\s*(\d{1,2})\s*"
        r"(?:민사법|민법|상법|민사소송법)?\s*"
        r"(?:선택형)?\s*(?:문제|문항|문)\s*(\d{1,3})\s*"
        r"(?:번)?\s*(?:보기)?\s*([ㄱ-ㅎ①-⑤])?",
        repl_bar_long,
        text,
    )
    text = re.sub(
        r"(?:변호사시험\s*)?변시\s*(\d{1,2})\s+(\d{1,3})\s*번\s*([ㄱ-ㅎ①-⑤])?",
        repl_bar_long,
        text,
    )
    text = re.sub(r"변호사시험\s*(?=변시)", "", text)

    def repl_court(m: re.Match[str]) -> str:
        year, q_no, mark = _year_short(m.group(1)), m.group(2), m.group(3) or ""
        return _space(f"법원직{year} {q_no}번 {mark}")

    text = re.sub(
        r"법원직\s*(\d{2,4})\s*년?\s*(\d{1,3})\s*번\s*([ㄱ-ㅎ①-⑤])?\s*(?:기출)?",
        repl_court,
        text,
    )
    text = re.sub(r"\s*기출\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_obj(obj: Any, key: str | None = None) -> tuple[Any, int]:
    changed = 0
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            out[k], delta = normalize_obj(v, k)
            changed += delta
        return out, changed
    if isinstance(obj, list):
        out = []
        seen = set()
        for v in obj:
            nv, delta = normalize_obj(v, key)
            changed += delta
            if key in SOURCE_KEYS and isinstance(nv, str):
                if nv in seen:
                    changed += 1
                    continue
                seen.add(nv)
            out.append(nv)
        return out, changed
    if isinstance(obj, str) and key in SOURCE_KEYS:
        normalized = normalize_source_label(obj)
        return normalized, changed + int(normalized != obj)
    return obj, changed


def main() -> None:
    total = 0
    for path in OX_FILES:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        normalized, changed = normalize_obj(data)
        if changed:
            compact = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")) + "\n"
            path.write_text(compact, encoding="utf-8")
        print(f"{path.relative_to(ROOT)}: {changed} source label changes")
        total += changed
    print(f"total: {total}")


if __name__ == "__main__":
    main()
