from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
REPORTS = ROOT / "reports"

UNIFIED_BANK = ASSETS / "ox_msa_unified_v001.json"
LEGACY_CIVIL_BANK = ASSETS / "ox_civil_unified_full_v002.json"
PER_ROUND_PATTERN = "ox_civil_bar{round}.json"

EXPECTED_ROUNDS = range(1, 16)
EXPECTED_QUESTIONS = set(range(1, 71))
SUBJECTS = ("민법", "민사소송법", "상법")


@dataclass(frozen=True)
class ParsedSource:
    round_no: int
    question_no: int | None = None
    choice: str | None = None
    raw: str = ""


SOURCE_PATTERNS = (
    # 변시15 민사법 선택형 문23 보기ㄱ / 변시15 문23 ㄱ
    re.compile(
        r"변시\s*(?P<round>\d{1,2})\s*"
        r"(?:민사법|민법|민사소송법|상법)?\s*"
        r"(?:선택형)?\s*"
        r"(?:문제|문항|문)\s*(?P<question>\d{1,2})\s*(?:번)?\s*"
        r"(?:보기|선지)?\s*(?P<choice>[ㄱ-ㅎ①-⑤])?"
    ),
    # 변시15 23번 ㄱ
    re.compile(
        r"변시\s*(?P<round>\d{1,2})\s+"
        r"(?P<question>\d{1,2})\s*번\s*(?:보기|선지)?\s*(?P<choice>[ㄱ-ㅎ①-⑤])?"
    ),
    # 변시15
    re.compile(r"변시\s*(?P<round>\d{1,2})"),
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def parse_source(raw_value: Any) -> list[ParsedSource]:
    raw = stringify(raw_value).strip()
    if not raw:
        return []
    parsed: list[ParsedSource] = []
    for pattern in SOURCE_PATTERNS:
        for match in pattern.finditer(raw):
            round_no = int(match.group("round"))
            if round_no not in EXPECTED_ROUNDS:
                continue
            question_text = match.groupdict().get("question")
            question_no = int(question_text) if question_text else None
            choice = match.groupdict().get("choice") or None
            parsed.append(ParsedSource(round_no, question_no, choice, raw))
        if parsed:
            break
    return parsed


def collect_sources(record: dict[str, Any]) -> list[ParsedSource]:
    parsed: list[ParsedSource] = []
    for key in ("src", "years", "refs", "ref", "tag", "source"):
        for value in as_list(record.get(key)):
            parsed.extend(parse_source(value))
    unique = {(p.round_no, p.question_no, p.choice, p.raw): p for p in parsed}
    return list(unique.values())


def record_text(record: dict[str, Any]) -> str:
    for key in ("rep", "q", "statement", "text"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def item_atom_records(item: dict[str, Any]) -> list[tuple[str, dict[str, Any], list[ParsedSource]]]:
    records: list[tuple[str, dict[str, Any], list[ParsedSource]]] = []
    item_sources = collect_sources(item)
    records.append(("대표", item, item_sources))
    for index, twin in enumerate(as_list(item.get("twins")), start=1):
        if not isinstance(twin, dict):
            continue
        twin_sources = collect_sources(twin) or item_sources
        records.append((f"쌍둥이{index}", twin, twin_sources))
    return records


def source_sort_key(source: ParsedSource) -> tuple[int, int, str]:
    return (source.round_no, source.question_no or 0, source.choice or "")


def render_missing(missing: set[int]) -> str:
    if not missing:
        return "-"
    values = sorted(missing)
    ranges: list[str] = []
    start = prev = values[0]
    for value in values[1:]:
        if value == prev + 1:
            prev = value
            continue
        ranges.append(f"{start}" if start == prev else f"{start}-{prev}")
        start = prev = value
    ranges.append(f"{start}" if start == prev else f"{start}-{prev}")
    return ", ".join(ranges)


def available_source_files() -> dict[int, Path]:
    files: dict[int, Path] = {}
    for round_no in EXPECTED_ROUNDS:
        path = ASSETS / PER_ROUND_PATTERN.format(round=round_no)
        if path.exists():
            files[round_no] = path
    return files


def scan_external_pdfs() -> list[Path]:
    source_dir = Path(r"C:\cowork\0gichul_법과목_기출\민사법")
    if not source_dir.exists():
        return []
    return sorted(
        path
        for path in source_dir.glob("*변호사시험_민사법*.pdf")
        if "(사례형)" not in path.name
    )


def main() -> None:
    REPORTS.mkdir(exist_ok=True)

    data = load_json(UNIFIED_BANK)
    items: list[dict[str, Any]] = data["items"]

    subject_total = Counter(item.get("subject") or "분류없음" for item in items)
    per_round_files = available_source_files()
    external_pdfs = scan_external_pdfs()

    round_atom_count: Counter[int] = Counter()
    round_subject_count: dict[int, Counter[str]] = defaultdict(Counter)
    round_question_refs: dict[int, set[int]] = defaultdict(set)
    round_choice_refs: dict[int, set[tuple[int, str | None]]] = defaultdict(set)
    round_only_refs: Counter[int] = Counter()
    raw_source_samples: dict[int, set[str]] = defaultdict(set)
    detailed_samples: dict[int, list[str]] = defaultdict(list)
    unparsed_source_values: Counter[str] = Counter()

    for item in items:
        subject = item.get("subject") or "분류없음"
        for atom_kind, record, sources in item_atom_records(item):
            if not sources:
                for key in ("src", "years", "refs", "ref", "tag", "source"):
                    for value in as_list(record.get(key)):
                        text = stringify(value).strip()
                        if text:
                            unparsed_source_values[text] += 1
                continue

            counted_rounds: set[int] = set()
            for source in sorted(sources, key=source_sort_key):
                counted_rounds.add(source.round_no)
                if source.raw:
                    raw_source_samples[source.round_no].add(source.raw)
                if source.question_no is None:
                    round_only_refs[source.round_no] += 1
                    continue
                round_question_refs[source.round_no].add(source.question_no)
                round_choice_refs[source.round_no].add((source.question_no, source.choice))
                if len(detailed_samples[source.round_no]) < 8:
                    text = record_text(record)
                    detail = f"{subject} / {atom_kind} / 문{source.question_no}"
                    if source.choice:
                        detail += f" {source.choice}"
                    if text:
                        detail += f" / {text[:80]}"
                    detailed_samples[source.round_no].append(detail)

            for round_no in counted_rounds:
                round_atom_count[round_no] += 1
                round_subject_count[round_no][subject] += 1

    lines: list[str] = []
    lines.append("# 민사법 변호사시험 atom 파이프라인 검증")
    lines.append("")
    lines.append("- 기준 파일: `assets/ox_msa_unified_v001.json`")
    lines.append("- 검증일: 2026-06-17")
    lines.append("- 검증 목적: 회차별 원문/해설에서 만든 atom이 통합본에서 회차·문항 단위로 추적되는지 확인")
    lines.append("")

    lines.append("## 결론")
    lines.append("")
    lines.append(
        f"- 통합 민사법 atom 은 현재 {len(items):,}개입니다: "
        + " / ".join(f"{subject} {subject_total.get(subject, 0):,}개" for subject in SUBJECTS)
        + "."
    )
    lines.append(
        "- 저장소 안에 별도 회차 파일로 남아 있는 것은 "
        + (
            ", ".join(f"{round_no}회" for round_no in sorted(per_round_files))
            if per_round_files
            else "없음"
        )
        + "입니다."
    )
    lines.append(
        "- `C:\\cowork\\0gichul_법과목_기출\\민사법`에는 변호사시험 민사법 PDF가 "
        f"{len(external_pdfs)}개 발견되었습니다. 이 폴더가 원문 재검증의 기준 자료입니다."
    )
    lines.append(
        "- 현재 통합본에는 1회부터 15회까지 출처 표시는 있으나, 모든 atom이 `몇 회 몇 번 몇 지문`까지 "
        "완전하게 남아 있는 상태는 아닙니다. 아래 표의 `문항 추적`이 그 정도를 보여줍니다."
    )
    lines.append("")

    lines.append("## 회차별 추적 현황")
    lines.append("")
    lines.append(
        "| 회차 | atom 수 | 문항 추적 | 보기 추적 | 미추적 문항 | 민법 | 민사소송법 | 상법 | 단순 회차표시 | 저장소 회차파일 |"
    )
    lines.append(
        "| ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |"
    )
    for round_no in sorted(EXPECTED_ROUNDS, reverse=True):
        questions = round_question_refs.get(round_no, set())
        missing = EXPECTED_QUESTIONS - questions
        file_mark = "있음" if round_no in per_round_files else "-"
        lines.append(
            f"| {round_no} | {round_atom_count.get(round_no, 0):,} | "
            f"{len(questions)}/70 | {len(round_choice_refs.get(round_no, set())):,} | "
            f"{render_missing(missing)} | "
            f"{round_subject_count[round_no].get('민법', 0):,} | "
            f"{round_subject_count[round_no].get('민사소송법', 0):,} | "
            f"{round_subject_count[round_no].get('상법', 0):,} | "
            f"{round_only_refs.get(round_no, 0):,} | {file_mark} |"
        )
    lines.append("")

    lines.append("## 15회·14회 상세")
    lines.append("")
    for round_no in (15, 14):
        questions = sorted(round_question_refs.get(round_no, set()))
        lines.append(f"### {round_no}회")
        lines.append("")
        lines.append(f"- atom 수: {round_atom_count.get(round_no, 0):,}")
        lines.append(
            "- 과목 분포: "
            + " / ".join(
                f"{subject} {round_subject_count[round_no].get(subject, 0):,}"
                for subject in SUBJECTS
            )
        )
        lines.append(f"- 문항 추적: {len(questions)}/70")
        lines.append(f"- 추적 문항: {', '.join(map(str, questions)) if questions else '-'}")
        lines.append(f"- 미추적 문항: {render_missing(EXPECTED_QUESTIONS - set(questions))}")
        lines.append("- 샘플:")
        if detailed_samples.get(round_no):
            for sample in detailed_samples[round_no]:
                lines.append(f"  - {sample}")
        else:
            lines.append("  - 상세 문항 출처 샘플 없음")
        lines.append("")

    lines.append("## 원문 파일 후보")
    lines.append("")
    if external_pdfs:
        for path in external_pdfs:
            lines.append(f"- `{path}`")
    else:
        lines.append("- 원문 PDF 후보를 찾지 못했습니다.")
    lines.append("")

    if unparsed_source_values:
        lines.append("## 파싱하지 못한 출처 샘플")
        lines.append("")
        for value, count in unparsed_source_values.most_common(20):
            lines.append(f"- {count}회: `{value}`")
        lines.append("")

    lines.append("## 다음 검증 순서")
    lines.append("")
    lines.append("1. 15회 원문 PDF와 해설을 기준으로 1~70번 원문·정답·해설 테이블을 복원한다.")
    lines.append("2. 15회 atom을 민법·민사소송법·상법으로 재분류하고, 각 atom에 `변시15 N번 보기` 출처를 붙인다.")
    lines.append("3. 14회에 같은 작업을 한 뒤, 15회+14회 통합 atom에서 중복·상충·법령변경 필요 항목을 검토한다.")
    lines.append("4. 같은 방식으로 1회까지 내려가며 통합본을 갱신한다.")
    lines.append("")

    report_path = REPORTS / "civil_bar_pipeline_audit.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    machine_path = REPORTS / "civil_bar_pipeline_audit.json"
    machine_data = {
        "bank": str(UNIFIED_BANK.relative_to(ROOT)),
        "count": len(items),
        "subject_total": dict(subject_total),
        "per_round_files": {str(k): str(v.relative_to(ROOT)) for k, v in per_round_files.items()},
        "external_pdfs": [str(path) for path in external_pdfs],
        "rounds": {
            str(round_no): {
                "atom_count": round_atom_count.get(round_no, 0),
                "subject_count": dict(round_subject_count[round_no]),
                "question_count": len(round_question_refs.get(round_no, set())),
                "questions": sorted(round_question_refs.get(round_no, set())),
                "missing_questions": sorted(EXPECTED_QUESTIONS - round_question_refs.get(round_no, set())),
                "choice_ref_count": len(round_choice_refs.get(round_no, set())),
                "round_only_refs": round_only_refs.get(round_no, 0),
            }
            for round_no in EXPECTED_ROUNDS
        },
        "unparsed_source_values": unparsed_source_values.most_common(100),
    }
    machine_path.write_text(
        json.dumps(machine_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {report_path}")
    print(f"Wrote {machine_path}")


if __name__ == "__main__":
    main()
