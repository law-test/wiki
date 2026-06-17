from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
REPORTS = ROOT / "reports"
LEXBANK_PATTERN = "lex-bank_*_2026-06-16/02_export/mc_questions.csv"

ROUND_NO = 15
ROUND_YEAR = 2026
CIVIL_SUBJECT = "민사법"

MARKERS = ("ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅅ")
CHOICE_MARKERS = ("①", "②", "③", "④", "⑤")
SUBJECT_SLUGS = {
    "민법": "civil_law",
    "민사소송법": "civil_procedure",
    "상법": "commercial_law",
}

LEGAL_REF_RE = re.compile(
    r"(민법|민사소송법|상법|어음법|보험업법|보험법|민사집행법|법원조직법|"
    r"부동산실권리자명의등기에관한법률|부동산 실권리자명의 등기에 관한 법률|"
    r"상가건물 임대차보호법|주택임대차보호법)"
    r"\s*제\s*\d+(?:조의\d+|조)?(?:\s*제\s*\d+\s*항)?"
)
ARTICLE_RE = re.compile(r"제\s*(\d+)(?:조의\d+|조)")
CASE_PARTY_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸]|(?<![A-Za-z])[A-E](?![A-Za-z])")


@dataclass(frozen=True)
class Statement:
    marker: str
    text: str


def clean_text(value: str) -> str:
    value = (value or "").replace("\u3000", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\s*\n\s*", " ", value)
    return value.strip()


def find_lexbank_csv() -> Path:
    matches = list(Path(r"C:\cowork").glob(LEXBANK_PATTERN))
    if not matches:
        raise FileNotFoundError("lex-bank mc_questions.csv not found under C:\\cowork")
    return matches[0]


def load_round_rows(path: Path, round_no: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if row.get("round") == str(round_no) and row.get("subject") == CIVIL_SUBJECT:
                rows.append(row)
    rows.sort(key=lambda row: int(row["number"]))
    return rows


def split_labeled_statements(sub_text: str) -> list[Statement]:
    text = (sub_text or "").strip()
    if not text:
        return []
    marker_class = "".join(MARKERS)
    pattern = re.compile(
        rf"(?ms)^\s*([{marker_class}])\.\s*(.*?)(?=^\s*[{marker_class}]\.\s*|\Z)"
    )
    statements: list[Statement] = []
    for match in pattern.finditer(text):
        body = clean_text(match.group(2))
        if body:
            statements.append(Statement(match.group(1), body))
    return statements


def choice_statements(row: dict[str, str]) -> list[Statement]:
    statements: list[Statement] = []
    for index, marker in enumerate(CHOICE_MARKERS, start=1):
        text = clean_text(row.get(f"choice{index}") or "")
        if text:
            statements.append(Statement(marker, text))
    return statements


def extract_letters(text: str) -> set[str]:
    return {marker for marker in MARKERS if marker in text}


def parse_explicit_ox(choice_text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for marker, sign in re.findall(rf"([{''.join(MARKERS)}])\s*\((○|×)\)", choice_text):
        mapping[marker] = "O" if sign == "○" else "X"
    return mapping


def classify_subject(question_no: int) -> str:
    # 제15회 민사법 선택형의 통상 배열: 1~35 민법, 36~45 민사소송법,
    # 46~47 민법, 48~51 민사소송법, 52~70 상법.
    if question_no <= 35 or question_no in (46, 47):
        return "민법"
    if 36 <= question_no <= 45 or 48 <= question_no <= 51:
        return "민사소송법"
    return "상법"


def correctness_map(row: dict[str, str], statements: list[Statement]) -> tuple[dict[str, str], str]:
    answer_text = (row.get("answer") or "").strip()
    if not answer_text.isdigit():
        return {}, "answer_not_numeric"
    answer_index = int(answer_text)
    if answer_index < 1 or answer_index > 5:
        return {}, "answer_out_of_range"

    selected = row.get(f"choice{answer_index}") or ""
    selected_clean = clean_text(selected)
    explicit = parse_explicit_ox(selected_clean)
    if explicit:
        return explicit, "explicit_ox_choice"

    markers = [statement.marker for statement in statements]
    selected_letters = extract_letters(selected_clean)
    if selected_letters and all(marker in MARKERS for marker in markers):
        negative = "옳지 않은" in row.get("content", "")
        selected_value = "X" if negative else "O"
        other_value = "O" if negative else "X"
        return {
            marker: selected_value if marker in selected_letters else other_value
            for marker in markers
        }, "letter_combination_negative" if negative else "letter_combination_positive"

    # If choices themselves are the statements, the answer choice alone is O or X.
    negative = "옳지 않은" in row.get("content", "")
    selected_marker = CHOICE_MARKERS[answer_index - 1]
    selected_value = "X" if negative else "O"
    other_value = "O" if negative else "X"
    return {
        marker: selected_value if marker == selected_marker else other_value
        for marker in markers
    }, "choice_statement_negative" if negative else "choice_statement_positive"


def extract_refs(row: dict[str, str], subject: str) -> list[str]:
    text = "\n".join(
        [
            row.get("ai_explanation") or "",
            row.get("tags") or "",
            row.get("title_tags") or "",
            row.get("content") or "",
        ]
    )
    refs: list[str] = []
    seen: set[str] = set()
    for match in LEGAL_REF_RE.finditer(text):
        ref = clean_text(match.group(0))
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)
        if len(refs) >= 4:
            break
    return refs


def first_article(refs: list[str]) -> str:
    for ref in refs:
        match = ARTICLE_RE.search(ref)
        if match:
            return f"제{match.group(1)}조"
    return ""


def topic_from_row(row: dict[str, str]) -> str:
    for key in ("title_tags", "tags"):
        raw = row.get(key) or ""
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        if parts:
            return parts[0]
    content = clean_text(row.get("content") or "")
    content = re.sub(r"에 관한 설명.*$", "", content)
    content = re.sub(r"중 옳.*$", "", content)
    return content[:24] or "민사법"


def explanation_snippet(row: dict[str, str], marker: str, answer: str, refs: list[str]) -> str:
    ref_text = ", ".join(refs[:2])
    base = f"제{ROUND_NO}회 변호사시험 민사법 선택형 {row['number']}번 {marker} 지문은 정답표상 {answer}입니다."
    if ref_text:
        base += f" 주요 근거는 {ref_text}입니다."
    else:
        base += " lex-bank 해설과 정답표를 기준으로 분류했습니다."
    return base


def trap_name(answer: str, source_kind: str) -> str:
    if answer == "O":
        return "대표 지문"
    if source_kind.startswith("letter_combination"):
        return "조합형 함정"
    if source_kind.startswith("choice_statement"):
        return "선택지 함정"
    return "OX 조합 함정"


def build_items(rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for row in rows:
        question_no = int(row["number"])
        subject = classify_subject(question_no)
        statements = split_labeled_statements(row.get("sub_text") or "")
        if not statements:
            statements = choice_statements(row)
        mapping, source_kind = correctness_map(row, statements)
        refs = extract_refs(row, subject)
        article = first_article(refs)
        topic = topic_from_row(row)
        for offset, statement in enumerate(statements, start=1):
            answer = mapping.get(statement.marker)
            if answer not in {"O", "X"}:
                issues.append(
                    {
                        "question": question_no,
                        "marker": statement.marker,
                        "issue": "missing_ox_mapping",
                        "source_kind": source_kind,
                        "statement": statement.text,
                    }
                )
                continue
            source_label = f"변시{ROUND_NO} {question_no}번 {statement.marker}"
            item = {
                "id": ROUND_NO * 100000 + question_no * 100 + offset,
                "round": ROUND_NO,
                "year": ROUND_YEAR,
                "question_no": question_no,
                "choice": statement.marker,
                "subject": subject,
                "topic": topic,
                "q": statement.text,
                "a": answer,
                "tag": f"변시{ROUND_NO}",
                "src": [source_label],
                "refs": [source_label],
                "trap": trap_name(answer, source_kind),
                "why": explanation_snippet(row, statement.marker, answer, refs),
                "ref": ", ".join(refs),
                "art": article,
                "needs_atomization": bool(CASE_PARTY_RE.search(statement.text)),
                "source_kind": source_kind,
                "note": "원문 선지 O/X 추출층입니다. 최종 서비스용 최소 원리 atom으로 쓰려면 사례 인물과 복합 사실관계를 제거해야 합니다.",
            }
            items.append(item)
    return items, issues


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_report(items: list[dict[str, Any]], issues: list[dict[str, Any]], rows: list[dict[str, str]], source_path: Path) -> str:
    subject_counts = Counter(item["subject"] for item in items)
    answer_counts = Counter(item["a"] for item in items)
    source_kind_counts = Counter(item["source_kind"] for item in items)
    per_question = defaultdict(list)
    needs_atomization = [item for item in items if item["needs_atomization"]]
    for item in items:
        per_question[item["question_no"]].append(item)

    missing_questions = [number for number in range(1, 71) if number not in per_question]
    lines: list[str] = []
    lines.append("# 제15회 변호사시험 민사법 선택형 O/X 지문 추출 검증")
    lines.append("")
    lines.append(f"- 기준 자료: `{source_path}`")
    lines.append("- 검증일: 2026-06-17")
    lines.append("- 목적: 15회 민사법 1~70번의 지문별 O/X, 과목 분류, 출처 라벨을 완성")
    lines.append("")
    lines.append("## 결론")
    lines.append("")
    lines.append(f"- 원문 문항: {len(rows)}/70")
    lines.append(f"- 추출 지문: {len(items)}개")
    lines.append(f"- O/X: O {answer_counts.get('O', 0)}개 / X {answer_counts.get('X', 0)}개")
    lines.append(
        "- 과목: "
        + " / ".join(
            f"{subject} {subject_counts.get(subject, 0)}개"
            for subject in ("민법", "민사소송법", "상법")
        )
    )
    lines.append(f"- 문항 누락: {', '.join(map(str, missing_questions)) if missing_questions else '-'}")
    lines.append(f"- O/X 매핑 문제: {len(issues)}개")
    lines.append(f"- 사례 인물 등이 남아 있어 최소 atom 교정이 필요한 지문: {len(needs_atomization)}개")
    lines.append("")

    lines.append("## 판정 방식")
    lines.append("")
    for kind, count in source_kind_counts.most_common():
        lines.append(f"- {kind}: {count}개")
    lines.append("")

    lines.append("## 문항별 현황")
    lines.append("")
    lines.append("| 문항 | 과목 | 지문 수 | O | X | 출처 예 |")
    lines.append("| ---: | --- | ---: | ---: | ---: | --- |")
    for number in range(1, 71):
        q_items = per_question.get(number, [])
        if not q_items:
            lines.append(f"| {number} | - | 0 | 0 | 0 | - |")
            continue
        counts = Counter(item["a"] for item in q_items)
        lines.append(
            f"| {number} | {q_items[0]['subject']} | {len(q_items)} | "
            f"{counts.get('O', 0)} | {counts.get('X', 0)} | {q_items[0]['refs'][0]} |"
        )
    lines.append("")

    if issues:
        lines.append("## O/X 매핑 문제")
        lines.append("")
        for issue in issues[:30]:
            lines.append(
                f"- {issue['question']}번 {issue['marker']}: {issue['issue']} / {issue['statement'][:120]}"
            )
        lines.append("")

    lines.append("## 다음 단계")
    lines.append("")
    lines.append("1. `assets/ox_civil_bar15.json`을 기준으로 15회 원문 지문층은 닫혔다.")
    lines.append("2. 다음 작업은 사례 인물이 남은 지문을 `making_atom_v001.md` 기준에 맞춰 최소 원리 atom으로 고치는 것이다.")
    lines.append("3. 그 뒤 15회 최소 atom을 기존 `assets/ox_msa_unified_v001.json`과 병합하면서 중복·상충을 검사한다.")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    source_path = find_lexbank_csv()
    rows = load_round_rows(source_path, ROUND_NO)
    items, issues = build_items(rows)

    payload = {
        "source": "lex-bank transformed O/X statement layer; original source kept outside public app assets",
        "round": ROUND_NO,
        "year": ROUND_YEAR,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "items": items,
        "issues": issues,
    }
    write_json(ASSETS / "ox_civil_bar15.json", payload)

    by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_subject[item["subject"]].append(item)
    for subject, subject_items in by_subject.items():
        slug = SUBJECT_SLUGS[subject]
        write_json(
            ASSETS / f"ox_civil_bar15_{slug}.json",
            {
                **{key: value for key, value in payload.items() if key not in {"items", "issues"}},
                "subject": subject,
                "count": len(subject_items),
                "items": subject_items,
                "issues": [
                    issue for issue in issues if classify_subject(int(issue["question"])) == subject
                ],
            },
        )

    REPORTS.mkdir(exist_ok=True)
    report = render_report(items, issues, rows, source_path)
    (REPORTS / "civil_bar15_atom_audit.md").write_text(report, encoding="utf-8")
    write_json(
        REPORTS / "civil_bar15_atom_audit.json",
        {
            "round": ROUND_NO,
            "year": ROUND_YEAR,
            "source_path": str(source_path),
            "count": len(items),
            "subject_counts": dict(Counter(item["subject"] for item in items)),
            "answer_counts": dict(Counter(item["a"] for item in items)),
            "source_kind_counts": dict(Counter(item["source_kind"] for item in items)),
            "needs_atomization": sum(1 for item in items if item["needs_atomization"]),
            "issues": issues,
        },
    )
    print(f"items={len(items)} issues={len(issues)}")


if __name__ == "__main__":
    main()
