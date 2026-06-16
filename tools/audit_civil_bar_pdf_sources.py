from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pdfplumber


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
SOURCE_DIR = Path(r"C:\cowork\0gichul_법과목_기출\민사법")
EXPECTED_QUESTIONS = set(range(1, 71))


@dataclass(frozen=True)
class RoundSource:
    round_no: int
    year: int
    question_pdf: Path | None
    commentary_pdfs: tuple[Path, ...]


def round_for_year(year: int) -> int:
    # 제1회 변호사시험은 2012년에 시행되었으므로 2026년은 제15회다.
    return year - 2011


def year_for_round(round_no: int) -> int:
    return round_no + 2011


def normalize_text(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_columns(page: pdfplumber.page.Page) -> str:
    midpoint = page.width / 2
    left = page.crop((0, 0, midpoint, page.height)).extract_text() or ""
    right = page.crop((midpoint, 0, page.width, page.height)).extract_text() or ""
    return f"{left}\n{right}"


def extract_question_texts(pdf_path: Path) -> dict[int, str]:
    chunks: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            chunks.append(extract_columns(page))
    text = normalize_text("\n".join(chunks))
    matches = list(re.finditer(r"문\s*(\d{1,2})\.", text))
    questions: dict[int, str] = {}
    for index, match in enumerate(matches):
        question_no = int(match.group(1))
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        if question_no in EXPECTED_QUESTIONS:
            questions[question_no] = normalize_text(text[match.start() : end])
    return questions


def find_sources() -> list[RoundSource]:
    sources: list[RoundSource] = []
    for round_no in range(1, 16):
        year = year_for_round(round_no)
        question_pdf = SOURCE_DIR / f"{year}_변호사시험_민사법.pdf"
        if not question_pdf.exists():
            question_pdf = None
        commentary = tuple(
            sorted(
                path
                for path in SOURCE_DIR.glob(f"{year}_변호사시험_민사법_해설*.pdf")
            )
        )
        sources.append(RoundSource(round_no, year, question_pdf, commentary))
    return sources


def question_excerpt(questions: dict[int, str], question_no: int) -> str:
    text = questions.get(question_no, "")
    text = re.sub(r"\s+", " ", text)
    return text[:420]


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    source_rows: list[dict[str, Any]] = []
    lines: list[str] = []
    lines.append("# 민사법 변호사시험 원문 PDF 추출 검증")
    lines.append("")
    lines.append("- 기준 폴더: `C:\\cowork\\0gichul_법과목_기출\\민사법`")
    lines.append("- 검증일: 2026-06-17")
    lines.append("- 목적: 각 회차 민사법 선택형 PDF에서 1~70번 문제 원문을 자동 추출할 수 있는지 확인")
    lines.append("")
    lines.append("## 회차별 원문 추출")
    lines.append("")
    lines.append("| 회차 | 연도 | 문제 PDF | 해설 PDF | 추출 문항 | 누락 문항 |")
    lines.append("| ---: | ---: | --- | ---: | ---: | --- |")

    for source in sorted(find_sources(), key=lambda row: row.round_no, reverse=True):
        questions: dict[int, str] = {}
        error = ""
        if source.question_pdf:
            try:
                questions = extract_question_texts(source.question_pdf)
            except Exception as exc:  # noqa: BLE001 - report extraction failure in audit output
                error = f"{type(exc).__name__}: {exc}"
        missing = sorted(EXPECTED_QUESTIONS - set(questions))
        source_rows.append(
            {
                "round": source.round_no,
                "year": source.year,
                "question_pdf": str(source.question_pdf) if source.question_pdf else None,
                "commentary_pdfs": [str(path) for path in source.commentary_pdfs],
                "question_count": len(questions),
                "questions": sorted(questions),
                "missing_questions": missing,
                "error": error,
                "sample_q1": question_excerpt(questions, 1),
                "sample_q36": question_excerpt(questions, 36),
                "sample_q70": question_excerpt(questions, 70),
            }
        )
        pdf_mark = "있음" if source.question_pdf else "없음"
        commentary_count = len(source.commentary_pdfs)
        missing_text = "-" if not missing else ", ".join(map(str, missing[:30])) + (" ..." if len(missing) > 30 else "")
        if error:
            missing_text = f"추출 오류: {error}"
        lines.append(
            f"| {source.round_no} | {source.year} | {pdf_mark} | {commentary_count} | "
            f"{len(questions)}/70 | {missing_text} |"
        )

    lines.append("")
    lines.append("## 15회 샘플")
    lines.append("")
    latest = next(row for row in source_rows if row["round"] == 15)
    for key, title in (("sample_q1", "문 1"), ("sample_q36", "문 36"), ("sample_q70", "문 70")):
        lines.append(f"### {title}")
        lines.append("")
        lines.append(latest[key] or "추출 없음")
        lines.append("")

    lines.append("## 판정")
    lines.append("")
    lines.append("- 문제 원문 PDF는 2단 편집이라 좌우 단을 따로 잘라 읽어야 한다.")
    lines.append("- 현재 로컬 원문 폴더에는 2회~15회 문제 PDF가 있고, 1회(2012년) 문제 PDF는 이 폴더에서 발견되지 않았다.")
    lines.append("- 해설 PDF는 회차별로 모두 있는 상태가 아니다. 15회·14회는 공기출 해설 PDF가 있고, 일부 과거 회차는 과목별 해설만 있다.")
    lines.append("- 따라서 원문 기준 재검증은 15회부터 내려가되, 1회와 해설 누락분은 다른 폴더 또는 사용자의 추가 자료에서 보충해야 한다.")
    lines.append("")

    (REPORTS / "civil_bar_pdf_source_audit.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    (REPORTS / "civil_bar_pdf_source_audit.json").write_text(
        json.dumps(source_rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Wrote reports/civil_bar_pdf_source_audit.md")
    print("Wrote reports/civil_bar_pdf_source_audit.json")


if __name__ == "__main__":
    main()
