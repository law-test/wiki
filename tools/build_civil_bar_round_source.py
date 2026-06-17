from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
REPORTS = ROOT / "reports"
LEXBANK_PATTERN = "lex-bank_*_2026-06-16/02_export/mc_questions.csv"

SUBJECT_CIVIL = "민사법"
MARKERS = tuple("ㄱㄴㄷㄹㅁㅂㅅ")
CHOICE_MARKERS = tuple("①②③④⑤")
INLINE_CHOICE_MAP = {
    "①": "①",
    "②": "②",
    "③": "③",
    "④": "④",
    "⑤": "⑤",
    "➀": "①",
    "➁": "②",
    "➂": "③",
    "➃": "④",
    "➄": "⑤",
}
SUBJECT_SLUGS = {
    "민법": "civil_law",
    "민사소송법": "civil_procedure",
    "상법": "commercial_law",
}
CASE_PARTY_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸]|(?<![A-Za-z])[A-E](?![A-Za-z])|(?<![A-Za-z])[X-Z](?![A-Za-z])")
LAW_REF_RE = re.compile(
    r"(민법|민사소송법|상법|민사집행법|어음법|수표법|집합건물의 소유 및 관리에 관한 법률|채무자회생법)"
    r"\s*제\s*\d+\s*조(?:의\s*\d+)?(?:\s*제\s*\d+\s*항)?"
)
ARTICLE_RE = re.compile(r"제\s*(\d+)\s*조(?:의\s*(\d+))?")
CASE_RE = re.compile(r"(?:대법원|대판|대결)\s*\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.?\s*(?:선고|자)?\s*[\w가-힣]+")


def clean_text(value: str) -> str:
    value = value or ""
    value = value.replace("\u3000", " ")
    value = re.sub(r"\+={5,}\+", " ", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\s*\n\s*", " ", value)
    return value.strip()


def find_lexbank_csv() -> Path:
    matches = list(Path(r"C:\cowork").glob(LEXBANK_PATTERN))
    if not matches:
        raise FileNotFoundError("lex-bank mc_questions.csv not found under C:\\cowork")
    return matches[0]


def year_for_round(round_no: int) -> int:
    return 2011 + round_no


def classify_subject(round_no: int, question_no: int) -> str:
    if round_no == 10:
        commercial = {*range(37, 53), 58, 61, 68, 69}
        civil_procedure = {53, 54, 55, 56, 57, 59, 60, 62, 63, 66, 67, 70}
        if question_no in commercial:
            return "상법"
        if question_no in civil_procedure:
            return "민사소송법"
        return "민법"
    if round_no == 11:
        commercial = {*range(37, 52), 54, 65, 68, 69, 70}
        civil_procedure = {52, 53, 55, 56, 57, 58, 59, 61, 62, 63, 64, 66, 67}
        if question_no in commercial:
            return "상법"
        if question_no in civil_procedure:
            return "민사소송법"
        return "민법"
    if round_no == 12:
        commercial = {*range(36, 53), 60, 63, 64}
        civil_procedure = {53, 54, 55, 57, 58, 62, 66, 68, 69, 70}
        if question_no in commercial:
            return "상법"
        if question_no in civil_procedure:
            return "민사소송법"
        return "민법"
    if round_no == 13:
        commercial = {32, 34, 35, 36, *range(40, 53)}
        civil_procedure = set(range(53, 71))
        if question_no in commercial:
            return "상법"
        if question_no in civil_procedure:
            return "민사소송법"
        return "민법"
    if round_no == 15:
        if question_no <= 35 or question_no in (46, 47):
            return "민법"
        if 36 <= question_no <= 45 or 48 <= question_no <= 51:
            return "민사소송법"
        return "상법"
    if round_no == 14:
        if question_no <= 35:
            return "민법"
        if question_no <= 49:
            return "민사소송법"
        return "상법"
    if question_no <= 35:
        return "민법"
    if question_no <= 49:
        return "민사소송법"
    return "상법"


def load_round_rows(path: Path, round_no: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if row.get("round") == str(round_no) and row.get("subject") == SUBJECT_CIVIL:
                rows.append(row)
    rows.sort(key=lambda row: int(row["number"]))
    return rows


def split_labeled_statements(sub_text: str) -> list[tuple[str, str]]:
    text = clean_text(sub_text)
    if not text:
        return []
    marker_class = "".join(MARKERS)
    pattern = re.compile(rf"(?s)([{marker_class}])\.\s*(.*?)(?=\s+[{marker_class}]\.\s*|\+={{5,}}|\Z)")
    out: list[tuple[str, str]] = []
    for match in pattern.finditer(text):
        body = clean_text(match.group(2))
        if body:
            out.append((match.group(1), body))
    return out


def choice_statements(row: dict[str, str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for index, marker in enumerate(CHOICE_MARKERS, start=1):
        text = clean_text(row.get(f"choice{index}") or "")
        if text:
            out.append((marker, text))
    return out


def inline_choice_statements(content: str) -> list[tuple[str, str]]:
    text = clean_text(content)
    if not text:
        return []
    marker_class = "".join(re.escape(marker) for marker in INLINE_CHOICE_MAP)
    pattern = re.compile(rf"(?s)([{marker_class}])\s*(.*?)(?=\s*[{marker_class}]\s*|\Z)")
    out: list[tuple[str, str]] = []
    for match in pattern.finditer(text):
        marker = INLINE_CHOICE_MAP[match.group(1)]
        body = clean_text(match.group(2))
        if body:
            out.append((marker, body))
    return out


def is_negative_question(content: str) -> bool:
    text = clean_text(content)
    return any(word in text for word in ("옳지 않은", "틀린", "잘못된", "타당하지 않은", "부당한"))


def extract_letters(text: str) -> set[str]:
    return {marker for marker in MARKERS if marker in text}


def correctness_map(row: dict[str, str], statements: list[tuple[str, str]]) -> tuple[dict[str, str], str]:
    answer = (row.get("answer") or "").strip()
    if not answer.isdigit():
        return {}, "answer_not_numeric"
    answer_index = int(answer)
    if answer_index < 1 or answer_index > 5:
        return {}, "answer_out_of_range"

    selected_choice = clean_text(row.get(f"choice{answer_index}") or "")
    negative = is_negative_question(row.get("content") or "")
    labels = [marker for marker, _ in statements]
    selected_letters = extract_letters(selected_choice)
    if selected_letters and all(marker in MARKERS for marker in labels):
        selected_value = "X" if negative else "O"
        other_value = "O" if negative else "X"
        return {
            marker: selected_value if marker in selected_letters else other_value
            for marker in labels
        }, "letter_combination_negative" if negative else "letter_combination_positive"

    selected_marker = CHOICE_MARKERS[answer_index - 1]
    selected_value = "X" if negative else "O"
    other_value = "O" if negative else "X"
    return {
        marker: selected_value if marker == selected_marker else other_value
        for marker in labels
    }, "choice_statement_negative" if negative else "choice_statement_positive"


def extract_refs(row: dict[str, str]) -> list[str]:
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
    for pattern in (LAW_REF_RE, CASE_RE):
        for match in pattern.finditer(text):
            ref = clean_text(match.group(0))
            if ref and ref not in seen:
                seen.add(ref)
                refs.append(ref)
            if len(refs) >= 6:
                return refs
    return refs


def first_article(refs: list[str]) -> str:
    for ref in refs:
        match = ARTICLE_RE.search(ref)
        if match:
            suffix = f"의{match.group(2)}" if match.group(2) else ""
            return f"제{match.group(1)}조{suffix}"
    return ""


def topic_from_row(row: dict[str, str]) -> str:
    for key in ("title_tags", "tags"):
        raw = row.get(key) or ""
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        if parts:
            return parts[0]
    return clean_text(row.get("content") or "")[:24]


def build_items(rows: list[dict[str, str]], round_no: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    year = year_for_round(round_no)
    for row in rows:
        question_no = int(row["number"])
        statements = split_labeled_statements(row.get("sub_text") or "")
        if not statements:
            statements = split_labeled_statements(row.get("content") or "")
        if not statements:
            statements = choice_statements(row)
        if not statements:
            statements = inline_choice_statements(row.get("content") or "")
        mapping, source_kind = correctness_map(row, statements)
        subject = classify_subject(round_no, question_no)
        refs = extract_refs(row)
        article = first_article(refs)
        topic = topic_from_row(row)
        for offset, (marker, statement) in enumerate(statements, start=1):
            answer = mapping.get(marker)
            if answer not in {"O", "X"}:
                issues.append(
                    {
                        "question": question_no,
                        "marker": marker,
                        "issue": "missing_ox_mapping",
                        "source_kind": source_kind,
                        "statement": statement,
                    }
                )
                continue
            source_label = f"변시{round_no} {question_no}번 {marker}"
            items.append(
                {
                    "id": round_no * 100000 + question_no * 100 + offset,
                    "round": round_no,
                    "year": year,
                    "question_no": question_no,
                    "choice": marker,
                    "subject": subject,
                    "topic": topic,
                    "q": statement,
                    "a": answer,
                    "tag": f"변시{round_no}",
                    "src": [source_label],
                    "refs": [source_label],
                    "trap": "정지문" if answer == "O" else "함정지문",
                    "why": f"제{round_no}회 변호사시험 민사법 선택형 {question_no}번 {marker} 지문은 정답표상 {answer}입니다.",
                    "ref": ", ".join(refs),
                    "art": article,
                    "needs_atomization": bool(CASE_PARTY_RE.search(statement)),
                    "source_kind": source_kind,
                    "note": "원문 지문 O/X 추출층입니다. 서비스 반영 전 최소 원리 atom으로 다시 정리해야 합니다.",
                }
            )
    return items, issues


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_report(
    round_no: int,
    rows: list[dict[str, str]],
    items: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    source_path: Path,
) -> str:
    subject_counts = Counter(item["subject"] for item in items)
    answer_counts = Counter(item["a"] for item in items)
    source_kind_counts = Counter(item["source_kind"] for item in items)
    per_question: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        per_question[item["question_no"]].append(item)
    missing = [number for number in range(1, 71) if number not in per_question]
    needs_atom = sum(1 for item in items if item["needs_atomization"])

    lines = [
        f"# 제{round_no}회 민사법 선택형 원문 지문층 검증",
        "",
        f"- 기준 자료: `{source_path}`",
        "- 작성일: 2026-06-17",
        "",
        "## 결론",
        "",
        f"- 원문 문항: {len(rows)}/70",
        f"- 추출 지문: {len(items)}개",
        f"- O/X: O {answer_counts.get('O', 0)}개 / X {answer_counts.get('X', 0)}개",
        "- 과목: " + " / ".join(f"{name} {subject_counts.get(name, 0)}개" for name in ("민법", "민사소송법", "상법")),
        f"- 누락 문항: {', '.join(map(str, missing)) if missing else '-'}",
        f"- O/X 매핑 문제: {len(issues)}개",
        f"- 최소 원리 atom 교정 필요 지문: {needs_atom}개",
        "",
        "## 판정 방식",
        "",
    ]
    for kind, count in source_kind_counts.most_common():
        lines.append(f"- {kind}: {count}개")
    lines.extend(["", "## 문항별 현황", "", "| 문항 | 과목 | 지문 수 | O | X |", "| ---: | --- | ---: | ---: | ---: |"])
    for number in range(1, 71):
        q_items = per_question.get(number, [])
        if not q_items:
            lines.append(f"| {number} | - | 0 | 0 | 0 |")
            continue
        counts = Counter(item["a"] for item in q_items)
        lines.append(f"| {number} | {q_items[0]['subject']} | {len(q_items)} | {counts.get('O', 0)} | {counts.get('X', 0)} |")
    if issues:
        lines.extend(["", "## 확인 필요", ""])
        for issue in issues[:30]:
            lines.append(f"- {issue['question']}번 {issue['marker']}: {issue['issue']} / {issue['statement'][:100]}")
    lines.extend(["", "## 다음 단계", "", "1. 이 원문 지문층을 해설 근거와 결합해 최소 원리 atom 초안으로 변환한다.", "2. 사례 인물·문제 전용 숫자·X/Y 토지 같은 표현을 제거한다.", "3. 15회 atom과 병합하면서 중복·상충을 검사한다.", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--suffix", default="source")
    args = parser.parse_args()

    source_path = find_lexbank_csv()
    rows = load_round_rows(source_path, args.round)
    items, issues = build_items(rows, args.round)
    year = year_for_round(args.round)
    base = f"ox_civil_bar{args.round}_{args.suffix}" if args.suffix else f"ox_civil_bar{args.round}"

    payload = {
        "source": "lex-bank transformed O/X statement layer; original source kept outside public app assets",
        "round": args.round,
        "year": year,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "items": items,
        "issues": issues,
    }
    ASSETS.mkdir(exist_ok=True)
    write_json(ASSETS / f"{base}.json", payload)

    by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_subject[item["subject"]].append(item)
    for subject, subject_items in by_subject.items():
        write_json(
            ASSETS / f"{base}_{SUBJECT_SLUGS[subject]}.json",
            {
                **{key: value for key, value in payload.items() if key not in {"items", "issues"}},
                "subject": subject,
                "count": len(subject_items),
                "items": subject_items,
                "issues": [issue for issue in issues if classify_subject(args.round, int(issue["question"])) == subject],
            },
        )

    REPORTS.mkdir(exist_ok=True)
    report_prefix = f"civil_bar{args.round}_{args.suffix}_atom_audit" if args.suffix else f"civil_bar{args.round}_atom_audit"
    (REPORTS / f"{report_prefix}.md").write_text(
        render_report(args.round, rows, items, issues, source_path),
        encoding="utf-8",
    )
    write_json(
        REPORTS / f"{report_prefix}.json",
        {
            "round": args.round,
            "year": year,
            "source_path": str(source_path),
            "count": len(items),
            "subject_counts": dict(Counter(item["subject"] for item in items)),
            "answer_counts": dict(Counter(item["a"] for item in items)),
            "source_kind_counts": dict(Counter(item["source_kind"] for item in items)),
            "needs_atomization": sum(1 for item in items if item["needs_atomization"]),
            "issues": issues,
        },
    )
    print(f"round={args.round} rows={len(rows)} items={len(items)} issues={len(issues)}")


if __name__ == "__main__":
    main()
