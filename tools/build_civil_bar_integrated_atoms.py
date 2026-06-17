from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
REPORTS = ROOT / "reports"
OUT_JSON = ASSETS / "ox_msa_bar_exam_integrated_draft_v001.json"
OUT_AUDIT_JSON = REPORTS / "civil_bar_integrated_atom_audit.json"
OUT_AUDIT_MD = REPORTS / "civil_bar_integrated_atom_audit.md"
ROUND_PATTERN = "ox_civil_bar{round}_minimal_atoms_draft.json"
SOURCE_RE = re.compile(r"변시(?P<round>\d{1,2})\s+(?P<question>\d{1,3})번\s+(?P<marker>.+)")


def load_round(round_no: int) -> list[dict[str, Any]]:
    path = ASSETS / ROUND_PATTERN.format(round=round_no)
    if not path.exists():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("items") or [])


def compact(text: str) -> str:
    text = str(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def key_for(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("subject") or ""),
        str(item.get("a") or ""),
        re.sub(r"\s+", "", str(item.get("rep") or "")),
    )


def parse_source(label: str) -> tuple[int, int, str, str]:
    match = SOURCE_RE.search(str(label or ""))
    if not match:
        return (0, 0, "", str(label or ""))
    return (
        int(match.group("round")),
        int(match.group("question")),
        match.group("marker").strip(),
        f"변시{int(match.group('round'))} {int(match.group('question'))}번 {match.group('marker').strip()}",
    )


def source_sort_key(label: str) -> tuple[int, int, str]:
    round_no, question_no, marker, _ = parse_source(label)
    return (-round_no, question_no, marker)


def unique_sorted_sources(values: list[str]) -> list[str]:
    normalized = []
    seen = set()
    for value in values:
        _, _, _, label = parse_source(value)
        label = compact(label)
        if label and label not in seen:
            seen.add(label)
            normalized.append(label)
    return sorted(normalized, key=source_sort_key)


def years_from_sources(src: list[str]) -> list[str]:
    years = []
    seen = set()
    for label in src:
        round_no, _, _, _ = parse_source(label)
        if round_no:
            year = f"변시{round_no}"
            if year not in seen:
                seen.add(year)
                years.append(year)
    return sorted(years, key=lambda value: -int(value.replace("변시", "")))


def grade_for(freq: int, base_grade: str = "A") -> str:
    if freq >= 7:
        return "S"
    if freq >= 5:
        return "A+"
    if freq >= 3:
        return "A"
    if freq == 2:
        return "B+"
    return base_grade or "A"


def weight_for(freq: int) -> float:
    return round(min(1.0, 0.55 + 0.08 * max(1, freq)), 4)


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    raw_items: list[dict[str, Any]] = []
    round_counts: Counter[int] = Counter()
    for round_no in range(15, 0, -1):
        items = load_round(round_no)
        raw_items.extend(items)
        round_counts[round_no] = len(items)

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in raw_items:
        grouped[key_for(item)].append(item)

    merged_items: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    duplicate_groups = 0
    repeated_source_groups = 0

    by_rep_subject: dict[tuple[str, str], set[str]] = defaultdict(set)
    for item in raw_items:
        by_rep_subject[(str(item.get("subject") or ""), re.sub(r"\s+", "", str(item.get("rep") or "")))].add(
            str(item.get("a") or "")
        )
    for (subject, rep_key), answers in by_rep_subject.items():
        if len(answers) > 1:
            conflicts.append({"subject": subject, "repKey": rep_key[:160], "answers": sorted(answers)})

    for index, (group_key, members) in enumerate(sorted(grouped.items(), key=lambda row: row[0]), start=1):
        subject, answer, _ = group_key
        head = members[0]
        src = unique_sorted_sources([s for item in members for s in (item.get("src") or [])])
        refs = unique_sorted_sources([s for item in members for s in (item.get("refs") or item.get("src") or [])])
        years = years_from_sources(src)
        freq = len(src) or len(members)
        if len(members) > 1:
            duplicate_groups += 1
        if freq > 1:
            repeated_source_groups += 1
        for source in src:
            source_counts[source] += 1
        ref_texts = [compact(item.get("ref") or "") for item in members if compact(item.get("ref") or "")]
        art_values = [compact(item.get("art") or "") for item in members if compact(item.get("art") or "")]
        topic_values = [compact(item.get("topic") or "") for item in members if compact(item.get("topic") or "")]
        base_grade = str(head.get("grade") or "A")
        merged_items.append(
            {
                "pid": f"civil-bar-integrated-{index:04d}",
                "subject": subject,
                "topic": topic_values[0] if topic_values else "",
                "rep": compact(head.get("rep") or ""),
                "a": answer,
                "why": compact(head.get("why") or head.get("rep") or ""),
                "ref": ref_texts[0] if ref_texts else "",
                "art": art_values[0] if art_values else "",
                "src": src,
                "refs": refs,
                "years": years,
                "sourceText": " · ".join(src),
                "freq": freq,
                "hot": freq >= 3,
                "twins": [],
                "ids": [item.get("pid") for item in members],
                "sourceAnswers": sorted({str(item.get("source_answer") or item.get("a") or "") for item in members}),
                "sourceStatements": [compact(item.get("source_statement") or "") for item in members[:5] if item.get("source_statement")],
                "grade": grade_for(freq, base_grade),
                "weight": weight_for(freq),
                "type": "civil_bar_integrated_minimal_atom_draft",
            }
        )

    merged_items.sort(key=lambda item: (item["subject"], -(item["freq"] or 0), item["pid"]))
    subject_counts = Counter(item["subject"] for item in merged_items)
    freq_counts = Counter(item["freq"] for item in merged_items)
    answer_counts = Counter(item["a"] for item in merged_items)

    payload = {
        "title": "변호사시험 민사법 선택형 1~15회 최소 원리 atom 통합 초안",
        "version": "civil-bar-integrated-draft-v001",
        "builtAt": datetime.now(timezone.utc).isoformat(),
        "source": "assets/ox_civil_bar{1..15}_minimal_atoms_draft.json",
        "count": len(merged_items),
        "rawCount": len(raw_items),
        "duplicateGroups": duplicate_groups,
        "repeatedSourceGroups": repeated_source_groups,
        "subjects": dict(subject_counts),
        "answerCounts": dict(answer_counts),
        "freqCounts": dict(sorted(freq_counts.items())),
        "conflictCount": len(conflicts),
        "items": merged_items,
    }
    audit = {
        "rawCount": len(raw_items),
        "mergedCount": len(merged_items),
        "duplicateGroups": duplicate_groups,
        "repeatedSourceGroups": repeated_source_groups,
        "subjectCounts": dict(subject_counts),
        "answerCounts": dict(answer_counts),
        "freqCounts": dict(sorted(freq_counts.items())),
        "roundCounts": dict(sorted(round_counts.items())),
        "conflictCount": len(conflicts),
        "conflicts": conflicts[:200],
        "multiSourceSamples": [
            {
                "pid": item["pid"],
                "subject": item["subject"],
                "freq": item["freq"],
                "src": item["src"],
                "rep": item["rep"],
            }
            for item in merged_items
            if item["freq"] > 1
        ][:40],
    }
    return payload, audit


def render_md(payload: dict[str, Any], audit: dict[str, Any]) -> str:
    lines = [
        "# 변호사시험 민사법 atom 통합 초안 검증",
        "",
        f"- 원자료 atom: {audit['rawCount']:,}개",
        f"- 통합 후 atom: {audit['mergedCount']:,}개",
        f"- 같은 문장 병합 그룹: {audit['duplicateGroups']:,}개",
        f"- 서로 다른 출처가 묶인 그룹: {audit['repeatedSourceGroups']:,}개",
        f"- O/X 충돌 후보: {audit['conflictCount']:,}개",
        f"- 출력 파일: `assets/{OUT_JSON.name}`",
        "",
        "## 과목별",
        "",
    ]
    for subject, count in sorted(audit["subjectCounts"].items()):
        lines.append(f"- {subject}: {count:,}개")
    lines.extend(["", "## 출제 빈도별", ""])
    for freq, count in sorted(audit["freqCounts"].items(), key=lambda row: int(row[0])):
        lines.append(f"- {freq}회 출처: {count:,}개")
    lines.extend(["", "## 회차별 원자료", ""])
    for round_no, count in sorted(audit["roundCounts"].items(), key=lambda row: int(row[0]), reverse=True):
        lines.append(f"- 변시{round_no}: {count:,}개")
    lines.extend(["", "## 여러 번 나온 atom 예시", ""])
    samples = audit.get("multiSourceSamples") or []
    if not samples:
        lines.append("- 아직 정확히 같은 문장으로 병합된 예시는 없습니다.")
    for sample in samples[:20]:
        lines.append(f"### {sample['pid']} · {sample['subject']} · {sample['freq']}회")
        lines.append(f"- 출처: {' · '.join(sample['src'])}")
        lines.append(f"- 문장: {sample['rep']}")
        lines.append("")
    if audit["conflictCount"]:
        lines.extend(["## O/X 충돌 후보", ""])
        for conflict in audit["conflicts"][:30]:
            lines.append(f"- {conflict['subject']} / {','.join(conflict['answers'])} / {conflict['repKey']}")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    payload, audit = build()
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_AUDIT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_AUDIT_MD.write_text(render_md(payload, audit), encoding="utf-8")
    print(
        f"raw={audit['rawCount']} merged={audit['mergedCount']} "
        f"duplicates={audit['duplicateGroups']} repeatedSources={audit['repeatedSourceGroups']} "
        f"conflicts={audit['conflictCount']}"
    )
    print(f"wrote {OUT_JSON.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
