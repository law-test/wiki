# -*- coding: utf-8 -*-
"""First-pass audit for civil-law OX atom explanations.

This script intentionally does not decide hard legal merits. It catches
mechanical risk patterns and writes a review list for human/legal checking.
"""

from __future__ import annotations

import difflib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "assets" / "ox_msa_unified_v001.json"
REPORT = ROOT / "reports" / "civil_ox_audit.md"
CIVIL_SUBJECTS = {"민법", "상법", "민사소송법", "민사특별법"}


def squash(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def one_line(text: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def source_values(item: dict[str, Any], twin: dict[str, Any] | None = None) -> list[str]:
    values: list[str] = []
    for obj in [item, twin or {}]:
        for key in ("src", "years", "refs", "ref"):
            value = obj.get(key)
            if isinstance(value, list):
                values.extend(str(x) for x in value)
            elif value:
                values.append(str(value))
    return values


def flag(rows: list[dict[str, Any]], kind: str, item: dict[str, Any], detail: str, twin: dict[str, Any] | None = None) -> None:
    rows.append(
        {
            "kind": kind,
            "subject": item.get("subject", ""),
            "pid": item.get("pid", ""),
            "art": item.get("art", ""),
            "grade": item.get("grade", ""),
            "src": " · ".join(source_values(item, twin)[:5]),
            "statement": one_line((twin or item).get("q") or item.get("rep")),
            "why": one_line((twin or item).get("why") or item.get("why")),
            "detail": detail,
        }
    )


def main() -> None:
    data = json.loads(BANK.read_text(encoding="utf-8"))
    items = [x for x in data.get("items", []) if x.get("subject") in CIVIL_SUBJECTS]
    rows: list[dict[str, Any]] = []
    subject_counts = Counter(x.get("subject", "") for x in items)
    twin_count = 0

    for item in items:
        rep = item.get("rep", "")
        why = item.get("why", "")
        if item.get("a") not in (None, "O", "X"):
            flag(rows, "answer_value", item, f"대표 정답값이 O/X가 아님: {item.get('a')!r}")
        if "?" in rep or "？" in rep:
            flag(rows, "question_form", item, "대표 문장이 의문문 형태입니다.")
        if not item.get("ref") and not item.get("refs"):
            flag(rows, "missing_ref", item, "근거 ref/refs가 비어 있습니다.")
        if squash(rep) and squash(rep) == squash(why):
            flag(rows, "explanation_same_as_statement", item, "해설이 대표 문장과 거의 같습니다.")
        if re.search(r"변호사시험\s*변시|법원직\s*법원직|\s기출\b", " ".join(source_values(item))):
            flag(rows, "source_label_unclean", item, "출처 표기가 길거나 중복됩니다.")
        if re.search(r"[�ÃãÂ]|\?\?\?", json.dumps(item, ensure_ascii=False)):
            flag(rows, "mojibake", item, "문자 깨짐 의심 문자열이 있습니다.")

        for twin in item.get("twins", []) or []:
            twin_count += 1
            q = twin.get("q", "")
            trap = str(twin.get("trap") or "").strip()
            corrected = str(twin.get("corrected") or "").strip()
            if "?" in q or "？" in q:
                flag(rows, "question_form", item, "쌍둥이 문장이 의문문 형태입니다.", twin)
            if not trap or trap in {"-", "—", "없음"}:
                flag(rows, "twin_without_trap", item, "현재 화면 구조상 X 함정으로 출제되면 위험합니다.", twin)
            if not corrected and trap:
                flag(rows, "twin_missing_corrected", item, "X 함정에 옳은 문장(corrected)이 없습니다.", twin)
            sim = difflib.SequenceMatcher(None, squash(rep), squash(q)).ratio() if rep and q else 0
            if sim >= 0.86:
                flag(rows, "twin_near_duplicate", item, f"대표 O 문장과 매우 유사합니다. similarity={sim:.2f}", twin)
            if re.search(r"변호사시험\s*변시|법원직\s*법원직|\s기출\b", " ".join(source_values(item, twin))):
                flag(rows, "source_label_unclean", item, "쌍둥이 출처 표기가 길거나 중복됩니다.", twin)

    by_kind = Counter(r["kind"] for r in rows)
    by_subject_kind: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        by_subject_kind[row["subject"]][row["kind"]] += 1

    REPORT.parent.mkdir(exist_ok=True)
    lines = [
        "# 민사법 OX/해설 1차 전수조사",
        "",
        f"- 대상 파일: `{BANK.relative_to(ROOT)}`",
        f"- 대상 atom: {len(items)}개",
        f"- 쌍둥이 atom: {twin_count}개",
        f"- 자동 점검 플래그: {len(rows)}건",
        "",
        "## 과목별 대상",
    ]
    for subject, count in sorted(subject_counts.items()):
        lines.append(f"- {subject}: {count}개")
    lines += ["", "## 유형별 플래그"]
    for kind, count in by_kind.most_common():
        lines.append(f"- {kind}: {count}건")
    lines += ["", "## 과목별 플래그"]
    for subject in sorted(by_subject_kind):
        joined = ", ".join(f"{k} {v}" for k, v in by_subject_kind[subject].most_common())
        lines.append(f"- {subject}: {joined}")
    lines += [
        "",
        "## 우선 검수 목록",
        "",
        "아래 항목은 자동으로 법리 판단을 확정하지 않고, 사람이 먼저 봐야 하는 후보입니다.",
        "",
    ]
    priority = {
        "twin_without_trap": 0,
        "twin_near_duplicate": 1,
        "explanation_same_as_statement": 2,
        "twin_missing_corrected": 3,
        "source_label_unclean": 4,
    }
    rows.sort(key=lambda r: (priority.get(r["kind"], 9), r["subject"], r["pid"]))
    for i, row in enumerate(rows[:300], 1):
        lines += [
            f"### {i}. {row['kind']} · {row['subject']} · {row['pid']}",
            f"- 조문: {row['art']}",
            f"- 출처: {row['src'] or '(없음)'}",
            f"- 지문: {row['statement']}",
            f"- 해설: {row['why'] or '(없음)'}",
            f"- 메모: {row['detail']}",
            "",
        ]

    REPORT.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"items={len(items)} twins={twin_count} flags={len(rows)} report={REPORT}")
    for kind, count in by_kind.most_common(12):
        print(f"{kind}: {count}")


if __name__ == "__main__":
    main()
