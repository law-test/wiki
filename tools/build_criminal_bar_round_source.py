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

SUBJECT_CRIMINAL = "형사법"
MARKERS = tuple("ㄱㄴㄷㄹㅁㅂㅅ가나다라마바사")
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
    "형법": "criminal_law",
    "형사소송법": "criminal_procedure",
    "혼합형사법": "mixed_criminal",
}
CASE_PARTY_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸]|(?<![A-Za-z])[A-E](?![A-Za-z])|(?<![A-Za-z])[P-Z](?![A-Za-z])")
LAW_REF_RE = re.compile(
    r"(형법|형사소송법|형사보상법|국민의 형사재판 참여에 관한 법률|국민참여재판법|"
    r"성폭력범죄의 처벌 등에 관한 특례법|아동ㆍ청소년의 성보호에 관한 법률|"
    r"아동·청소년의 성보호에 관한 법률|특정범죄 가중처벌 등에 관한 법률|"
    r"특정범죄가중처벌등에관한법률|특정경제범죄 가중처벌 등에 관한 법률|"
    r"특정경제범죄가중처벌법|폭력행위 등 처벌에 관한 법률|정보통신망법|"
    r"정보통신망 이용촉진 및 정보보호 등에 관한 법률|통신비밀보호법|도로교통법|"
    r"마약류 관리에 관한 법률|여신전문금융업법|부패방지법)"
    r"\s*제\s*\d+\s*조(?:의\s*\d+)?(?:\s*제\s*\d+\s*항)?"
)
ARTICLE_RE = re.compile(r"제\s*(\d+)\s*조(?:의\s*(\d+))?")
CASE_RE = re.compile(r"(?:대법원|대판|대결)\s*\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.?\s*(?:선고|자)?\s*[\w가-힣]+")

PROCEDURE_TERMS = {
    "형사소송법",
    "수사",
    "공판",
    "공소",
    "공소장",
    "재정신청",
    "불기소",
    "증거",
    "증거능력",
    "전문법칙",
    "자백",
    "보강증거",
    "보석",
    "구속",
    "체포",
    "압수",
    "수색",
    "영장",
    "재심",
    "상소",
    "항소",
    "상고",
    "약식",
    "국선변호인",
    "변호인",
    "피의자신문조서",
    "공동피고인",
    "증인",
    "증언",
    "진술거부권",
    "국민참여재판",
    "배심원",
    "관할",
    "면소판결",
    "공소기각",
}
SUBSTANTIVE_TERMS = {
    "형법",
    "죄형법정주의",
    "구성요건",
    "위법성",
    "책임",
    "고의",
    "과실",
    "미수",
    "공범",
    "공동정범",
    "교사범",
    "방조범",
    "상해",
    "폭행",
    "협박",
    "강도",
    "절도",
    "사기",
    "공갈",
    "횡령",
    "배임",
    "장물",
    "문서",
    "위조",
    "뇌물",
    "방화",
    "업무방해",
    "명예훼손",
    "모욕",
    "무고",
    "죄수",
    "형벌",
    "친족상도례",
}


def clean_text(value: str) -> str:
    value = value or ""
    value = value.replace("\u3000", " ").replace("\xa0", " ")
    value = re.sub(r"\+={5,}\+", " ", value)
    value = re.sub(r"-{5,}", " ", value)
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


def load_round_rows(path: Path, round_no: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if row.get("round") == str(round_no) and row.get("subject") == SUBJECT_CRIMINAL:
                rows.append(row)
    rows.sort(key=lambda row: int(row["number"]))
    return rows


def split_labeled_statements(text: str) -> list[tuple[str, str]]:
    text = clean_text(text)
    if not text:
        return []
    marker_class = "".join(MARKERS)
    pattern = re.compile(rf"(?s)(?:^|\s)([{marker_class}])\.\s+(.*?)(?=(?:\s[{marker_class}]\.\s+)|\+={{5,}}|\Z)")
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


def statements_too_short_for_atoms(statements: list[tuple[str, str]], *, max_len: int = 12) -> bool:
    if not statements:
        return False
    compact_lengths = [len(re.sub(r"[\s,·ㆍ.()（）]+", "", body)) for _, body in statements]
    return max(compact_lengths, default=0) <= max_len


def is_sentence_like_statement(statement: str) -> bool:
    text = clean_text(statement)
    compact_len = len(re.sub(r"[\s,·ㆍ.()（）]+", "", text))
    sentence_markers = (
        "다.",
        "한다",
        "된다",
        "있다",
        "없다",
        "아니다",
        "않다",
        "못한다",
        "수 있다",
        "수 없다",
        "아니하다",
    )
    has_sentence_marker = any(marker in text for marker in sentence_markers)
    if has_sentence_marker and compact_len >= 7:
        return True
    if compact_len < 14:
        return False
    return compact_len >= 35


def is_negative_question(content: str) -> bool:
    text = clean_text(content)
    return any(word in text for word in ("옳지 않은", "틀린", "아닌", "부적절", "타당하지 않은", "잘못된"))


def extract_letters(text: str) -> set[str]:
    found: set[str] = set()
    for marker in MARKERS:
        if marker in "가나다라마바사":
            if re.search(rf"(?<![가-힣]){marker}(?![가-힣])", text):
                found.add(marker)
        elif marker in text:
            found.add(marker)
    return found


def explicit_ox_map(text: str, labels: list[str]) -> dict[str, str]:
    value_map = {"○": "O", "〇": "O", "O": "O", "o": "O", "×": "X", "X": "X", "x": "X"}
    found: dict[str, str] = {}
    marker_class = "".join(MARKERS)
    pattern = re.compile(rf"([{marker_class}])\s*[\\(（]\s*([○〇Oo×Xx])\s*[\\)）]")
    for marker, value in pattern.findall(text):
        found[marker] = value_map[value]
    if labels and all(label in found for label in labels):
        return {label: found[label] for label in labels}
    return {}


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
    if labels and all(marker in MARKERS for marker in labels):
        explicit = explicit_ox_map(selected_choice, labels)
        if explicit:
            return explicit, "explicit_ox_combination"

        selected_letters = extract_letters(selected_choice)
        if selected_letters:
            selected_value = "X" if negative else "O"
            other_value = "O" if negative else "X"
            return {
                marker: selected_value if marker in selected_letters else other_value
                for marker in labels
            }, "letter_combination_negative" if negative else "letter_combination_positive"

        return {}, "cannot_infer_labeled_statement_ox"

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


def classify_subject(row: dict[str, str], statement: str) -> str:
    text = clean_text(
        " ".join(
            [
                row.get("content") or "",
                row.get("tags") or "",
                row.get("title_tags") or "",
                statement,
            ]
        )
    )
    proc_score = sum(1 for term in PROCEDURE_TERMS if term in text)
    law_score = sum(1 for term in SUBSTANTIVE_TERMS if term in text)
    if "형사소송법" in text:
        proc_score += 3
    if "형법" in text:
        law_score += 2

    if proc_score >= law_score + 2:
        return "형사소송법"
    if law_score >= proc_score + 2:
        return "형법"
    if proc_score and law_score:
        return "혼합형사법"

    question_no = int(row["number"])
    if question_no <= 18:
        return "형법"
    if question_no >= 21:
        return "형사소송법"
    return "혼합형사법"


def collect_statements(row: dict[str, str]) -> tuple[list[tuple[str, str]], str]:
    statements = split_labeled_statements(row.get("sub_text") or "")
    if statements:
        return statements, "sub_text_labels"
    statements = split_labeled_statements(row.get("content") or "")
    if statements:
        if statements_too_short_for_atoms(statements):
            return [], "content_labels_too_short"
        return statements, "content_labels"
    statements = choice_statements(row)
    if statements:
        if statements_too_short_for_atoms(statements):
            return [], "choice_cells_too_short"
        return statements, "choice_cells"
    statements = inline_choice_statements(row.get("content") or "")
    if statements:
        return statements, "inline_choices"
    return [], "no_statements"


def build_items(rows: list[dict[str, str]], round_no: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    year = year_for_round(round_no)
    for row in rows:
        question_no = int(row["number"])
        statements, statement_kind = collect_statements(row)
        if not statements:
            issues.append(
                {
                    "round": round_no,
                    "question": question_no,
                    "marker": "",
                    "issue": "no_statement_extracted",
                    "source_kind": statement_kind,
                    "statement": clean_text(row.get("content") or ""),
                }
            )
            continue

        mapping, source_kind = correctness_map(row, statements)
        refs = extract_refs(row)
        article = first_article(refs)
        topic = topic_from_row(row)
        selected_choice = ""
        answer = (row.get("answer") or "").strip()
        if answer.isdigit() and 1 <= int(answer) <= 5:
            selected_choice = clean_text(row.get(f"choice{int(answer)}") or "")

        for offset, (marker, statement) in enumerate(statements, start=1):
            if not is_sentence_like_statement(statement):
                issues.append(
                    {
                        "round": round_no,
                        "question": question_no,
                        "marker": marker,
                        "issue": "non_sentence_statement",
                        "source_kind": source_kind,
                        "statement_kind": statement_kind,
                        "statement": statement,
                        "selected_choice": selected_choice,
                    }
                )
                continue

            answer_value = mapping.get(marker)
            if answer_value not in {"O", "X"}:
                issues.append(
                    {
                        "round": round_no,
                        "question": question_no,
                        "marker": marker,
                        "issue": "missing_ox_mapping",
                        "source_kind": source_kind,
                        "statement_kind": statement_kind,
                        "statement": statement,
                        "selected_choice": selected_choice,
                    }
                )
                continue

            source_label = f"변시{round_no} {question_no}번 {marker}"
            subject = classify_subject(row, statement)
            items.append(
                {
                    "id": round_no * 100000 + question_no * 100 + offset,
                    "round": round_no,
                    "year": year,
                    "exam": "변호사시험",
                    "subject_group": SUBJECT_CRIMINAL,
                    "subject": subject,
                    "question_no": question_no,
                    "choice": marker,
                    "topic": topic,
                    "q": statement,
                    "a": answer_value,
                    "tag": f"변시{round_no}",
                    "src": [source_label],
                    "refs": [source_label],
                    "trap": "정지문" if answer_value == "O" else "함정지문",
                    "why": f"제{round_no}회 변호사시험 형사법 선택형 {question_no}번 {marker} 지문은 정답표상 {answer_value}입니다.",
                    "ref": ", ".join(refs),
                    "art": article,
                    "source_kind": source_kind,
                    "statement_kind": statement_kind,
                    "original_question": clean_text(row.get("content") or ""),
                    "original_answer": answer,
                    "answer_choice": selected_choice,
                    "needs_atomization": bool(CASE_PARTY_RE.search(statement)),
                }
            )
    return items, issues


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_round_report(
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
    missing = [number for number in range(1, 41) if number not in per_question]
    needs_atom = sum(1 for item in items if item["needs_atomization"])

    lines = [
        f"# 제{round_no}회 형사법 선택형 원문 지문층 검증",
        "",
        f"- 기준 자료: `{source_path}`",
        "- 작성일: 2026-06-18",
        "",
        "## 결론",
        "",
        f"- 원문 문항: {len(rows)}/40",
        f"- 추출 지문: {len(items)}개",
        f"- O/X: O {answer_counts.get('O', 0)}개 / X {answer_counts.get('X', 0)}개",
        "- 분류: " + " / ".join(f"{name} {subject_counts.get(name, 0)}개" for name in ("형법", "형사소송법", "혼합형사법")),
        f"- 누락 문항: {', '.join(map(str, missing)) if missing else '-'}",
        f"- O/X 매핑 문제: {len(issues)}개",
        f"- 최소 원리 atom 교정 필요 지문: {needs_atom}개",
        "",
        "## 판정 방식",
        "",
    ]
    for kind, count in source_kind_counts.most_common():
        lines.append(f"- {kind}: {count}개")
    lines.extend(["", "## 문항별 현황", "", "| 문항 | 분류 | 지문 수 | O | X |", "| ---: | --- | ---: | ---: | ---: |"])
    for number in range(1, 41):
        q_items = per_question.get(number, [])
        if not q_items:
            lines.append(f"| {number} | - | 0 | 0 | 0 |")
            continue
        counts = Counter(item["a"] for item in q_items)
        subjects = "·".join(sorted({item["subject"] for item in q_items}))
        lines.append(f"| {number} | {subjects} | {len(q_items)} | {counts.get('O', 0)} | {counts.get('X', 0)} |")
    if issues:
        lines.extend(["", "## 확인 필요", ""])
        for issue in issues[:40]:
            lines.append(
                f"- {issue['question']}번 {issue['marker']}: {issue['issue']} / "
                f"{clean_text(issue.get('statement', ''))[:100]}"
            )
    lines.extend(
        [
            "",
            "## 다음 단계",
            "",
            "1. 이 원문 지문층을 해설 근거와 결합해 최소 원리 atom 초안으로 변환한다.",
            "2. 사례 인물·문제 전용 숫자·특정 회사명 같은 표현을 제거한다.",
            "3. 회차별 atom을 병합하면서 중복·상충을 검사한다.",
            "",
        ]
    )
    return "\n".join(lines)


def render_all_report(
    per_round: dict[int, tuple[list[dict[str, str]], list[dict[str, Any]], list[dict[str, Any]]]],
    source_path: Path,
) -> str:
    all_items = [item for _, items, _ in per_round.values() for item in items]
    all_issues = [issue for _, _, issues in per_round.values() for issue in issues]
    subject_counts = Counter(item["subject"] for item in all_items)
    answer_counts = Counter(item["a"] for item in all_items)
    lines = [
        "# 변호사시험 형사법 선택형 1~15회 원문 지문층 검증",
        "",
        f"- 기준 자료: `{source_path}`",
        "- 작성일: 2026-06-18",
        "",
        "## 결론",
        "",
        f"- 원문 문항: {sum(len(rows) for rows, _, _ in per_round.values())}/600",
        f"- 추출 지문: {len(all_items)}개",
        f"- O/X: O {answer_counts.get('O', 0)}개 / X {answer_counts.get('X', 0)}개",
        "- 분류: " + " / ".join(f"{name} {subject_counts.get(name, 0)}개" for name in ("형법", "형사소송법", "혼합형사법")),
        f"- O/X 매핑 문제: {len(all_issues)}개",
        "",
        "## 회차별 현황",
        "",
        "| 회차 | 원문 문항 | 추출 지문 | O | X | 확인 필요 |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for round_no in sorted(per_round):
        rows, items, issues = per_round[round_no]
        counts = Counter(item["a"] for item in items)
        lines.append(
            f"| {round_no} | {len(rows)} | {len(items)} | {counts.get('O', 0)} | "
            f"{counts.get('X', 0)} | {len(issues)} |"
        )
    if all_issues:
        lines.extend(["", "## 확인 필요 상위 50건", ""])
        for issue in all_issues[:50]:
            lines.append(
                f"- 변시{issue['round']} {issue['question']}번 {issue['marker']}: "
                f"{issue['issue']} / {clean_text(issue.get('statement', ''))[:100]}"
            )
    return "\n".join(lines) + "\n"


def write_round_outputs(round_no: int, rows: list[dict[str, str]], items: list[dict[str, Any]], issues: list[dict[str, Any]], source_path: Path, suffix: str) -> None:
    year = year_for_round(round_no)
    base = f"ox_criminal_bar{round_no}_{suffix}" if suffix else f"ox_criminal_bar{round_no}"
    payload = {
        "source": "lex-bank transformed O/X statement layer; original source kept outside public app assets",
        "round": round_no,
        "year": year,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "items": items,
        "issues": issues,
    }
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
                "issues": [issue for issue in issues if issue.get("subject") == subject],
            },
        )

    report_prefix = f"criminal_bar{round_no}_{suffix}_atom_audit" if suffix else f"criminal_bar{round_no}_atom_audit"
    (REPORTS / f"{report_prefix}.md").write_text(
        render_round_report(round_no, rows, items, issues, source_path),
        encoding="utf-8",
    )
    write_json(
        REPORTS / f"{report_prefix}.json",
        {
            "round": round_no,
            "year": year,
            "source_path": str(source_path),
            "count": len(items),
            "subject_counts": dict(Counter(item["subject"] for item in items)),
            "answer_counts": dict(Counter(item["a"] for item in items)),
            "source_kind_counts": dict(Counter(item["source_kind"] for item in items)),
            "issues": issues,
        },
    )


def write_all_outputs(per_round: dict[int, tuple[list[dict[str, str]], list[dict[str, Any]], list[dict[str, Any]]]], source_path: Path, suffix: str) -> None:
    all_items = [item for _, items, _ in per_round.values() for item in items]
    all_issues = [issue for _, _, issues in per_round.values() for issue in issues]
    base = f"ox_criminal_bar_all_{suffix}" if suffix else "ox_criminal_bar_all"
    payload = {
        "source": "lex-bank transformed O/X statement layer; original source kept outside public app assets",
        "rounds": sorted(per_round),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(all_items),
        "items": all_items,
        "issues": all_issues,
    }
    write_json(ASSETS / f"{base}.json", payload)
    report_prefix = f"criminal_bar_all_{suffix}_atom_audit" if suffix else "criminal_bar_all_atom_audit"
    (REPORTS / f"{report_prefix}.md").write_text(render_all_report(per_round, source_path), encoding="utf-8")
    write_json(
        REPORTS / f"{report_prefix}.json",
        {
            "source_path": str(source_path),
            "rounds": sorted(per_round),
            "count": len(all_items),
            "subject_counts": dict(Counter(item["subject"] for item in all_items)),
            "answer_counts": dict(Counter(item["a"] for item in all_items)),
            "issues": all_issues,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--suffix", default="source")
    args = parser.parse_args()
    if not args.all and not args.round:
        parser.error("--round or --all is required")

    ASSETS.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    source_path = find_lexbank_csv()
    round_numbers = range(1, 16) if args.all else [args.round]
    per_round: dict[int, tuple[list[dict[str, str]], list[dict[str, Any]], list[dict[str, Any]]]] = {}
    for round_no in round_numbers:
        rows = load_round_rows(source_path, int(round_no))
        items, issues = build_items(rows, int(round_no))
        write_round_outputs(int(round_no), rows, items, issues, source_path, args.suffix)
        per_round[int(round_no)] = (rows, items, issues)
    if args.all:
        write_all_outputs(per_round, source_path, args.suffix)

    total_items = sum(len(items) for _, items, _ in per_round.values())
    total_issues = sum(len(issues) for _, _, issues in per_round.values())
    print(f"criminal source extraction done: rounds={len(per_round)} items={total_items} issues={total_issues}")


if __name__ == "__main__":
    main()
