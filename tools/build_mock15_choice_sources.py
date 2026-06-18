from __future__ import annotations

import argparse
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pdfplumber


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = (
    Path("C:/cowork")
    / "\ubcc0\ud638\uc0ac\uc2dc\ud5d8_2026_06_15"
    / "\ubcc0\ubaa8\ubaa8\uc74c"
    / "1. 2025\ud559\ub144\ub3c4 \ubcc0\uc2dc\ubaa8\uc7581-3\ucc28 hwp"
    / "2025\ud559\ub144\ub3c4 \ubcc0\uc2dc \ubaa8\uc758"
)
DEFAULT_OUT = (
    Path("C:/cowork/law-test-private")
    / "private_problem_banks"
    / "mock15"
    / "mock15_2025_choice_sources_v001.json"
)
HWP5PROC = (
    Path.home()
    / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/Scripts/hwp5proc.exe"
)

PUBLIC_SOURCE_LABEL = "\ubcc0\ud638\uc0ac\uc2dc\ud5d8 15\ud68c \uc608\uc0c1"
ROUND_MONTHS = {1: 6, 2: 8, 3: 10}
SUBJECTS = [
    ("\uacf5\ubc95", 40),
    ("\ud615\uc0ac\ubc95", 40),
    ("\ubbfc\uc0ac\ubc95", 70),
]
CIRCLED_TO_NO = {
    "\u2460": 1,
    "\u2461": 2,
    "\u2462": 3,
    "\u2463": 4,
    "\u2464": 5,
}
QUESTION_RE = re.compile(r"^\s*" + "\ubb38" + r"\s*(\d{1,3})\.\s*(.*)$")
QUESTION_INSIDE_RE = re.compile(r"^(.+?)\s+(\ubb38\s*\d{1,3}\.\s*.*)$")
JAMO_TRANSLATION = str.maketrans(
    {
        "\u1100": "\u3131",
        "\u1102": "\u3134",
        "\u1103": "\u3137",
        "\u1105": "\u3139",
        "\u1106": "\u3141",
        "\u1107": "\u3142",
    }
)


def clean_text(value: str) -> str:
    value = (value or "").replace("\u3000", " ").replace("\u00a0", " ")
    value = value.replace("\xad", "")
    value = value.translate(JAMO_TRANSLATION)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def find_one(directory: Path, marker: str) -> Path:
    matches = sorted(
        path
        for path in directory.iterdir()
        if marker in path.name
        and path.suffix.lower() in {".hwp", ".pdf"}
        and "\uc0ac\ub840\ud615" not in path.name
        and "\uae30\ub85d\ud615" not in path.name
    )
    if len(matches) != 1:
        names = ", ".join(path.name for path in matches) or "none"
        raise FileNotFoundError(f"{directory}: expected 1 {marker!r} file, found {names}")
    return matches[0]


def find_round_dir(source_root: Path, exam_year: int, round_no: int) -> Path:
    marker = f"{exam_year} \ubc95\uc804\ud611 {round_no}\ucc28 \ubaa8\uc758\uace0\uc0ac"
    matches = sorted(path for path in source_root.iterdir() if path.is_dir() and marker in path.name)
    if len(matches) != 1:
        names = ", ".join(path.name for path in matches) or "none"
        raise FileNotFoundError(f"{source_root}: expected round {round_no} dir, found {names}")
    return matches[0]


def find_subject_dir(round_directory: Path, subject_area: str) -> Path:
    matches = sorted(
        path
        for path in round_directory.iterdir()
        if path.is_dir() and subject_area in path.name and "\uc120\ud0dd" not in path.name
    )
    if len(matches) != 1:
        names = ", ".join(path.name for path in matches) or "none"
        raise FileNotFoundError(f"{round_directory}: expected {subject_area} dir, found {names}")
    return matches[0]


def hwp_xml_paragraphs(path: Path) -> list[str]:
    if not HWP5PROC.exists():
        raise FileNotFoundError(f"hwp5proc not found: {HWP5PROC}")
    proc = subprocess.run(
        [str(HWP5PROC), "xml", "--no-validate-wellformed", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=True,
    )
    root = ET.fromstring(proc.stdout)
    paragraphs: list[str] = []
    for element in root.iter():
        if local_name(element.tag) != "Paragraph":
            continue
        pieces: list[str] = []
        for child in element.iter():
            name = local_name(child.tag)
            if name == "Text" and child.text:
                pieces.append(child.text)
            elif name == "ControlChar":
                pieces.append("\n" if child.attrib.get("code") in {"10", "13"} else " ")
        text = clean_text("".join(pieces))
        if text:
            paragraphs.append(text)
    return paragraphs


def pdf_column_paragraphs(path: Path) -> list[str]:
    paragraphs: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            width = float(page.width)
            height = float(page.height)
            split = width / 2
            # Korean bar-exam PDFs are commonly two-column layouts. A small
            # overlap prevents question markers at the column edge from being cut.
            boxes = [
                (0, 0, min(width, split + 12), height),
                (max(0, split - 12), 0, width, height),
            ]
            for box in boxes:
                text = page.crop(box).extract_text(x_tolerance=1, y_tolerance=3) or ""
                for line in text.splitlines():
                    line = clean_text(line)
                    if not line:
                        continue
                    if re.fullmatch(r"\ubb38\s*\d{1,3}", line):
                        continue
                    marker = QUESTION_INSIDE_RE.match(line)
                    if marker:
                        before, after = clean_text(marker.group(1)), clean_text(marker.group(2))
                        if before:
                            paragraphs.append(before)
                        paragraphs.append(after)
                    else:
                        paragraphs.append(line)
    return paragraphs


def document_paragraphs(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return pdf_column_paragraphs(path)
    return hwp_xml_paragraphs(path)


def dedupe_question_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        normalized = re.sub(r"\s+", " ", line).strip()
        if len(normalized) >= 20 and normalized in seen:
            continue
        if len(normalized) >= 20:
            seen.add(normalized)
        out.append(line)
    return out


def parse_questions(paragraphs: list[str], expected_count: int) -> dict[int, str]:
    questions: dict[int, list[str]] = {}
    current_no: int | None = None
    for para in paragraphs:
        match = QUESTION_RE.match(para)
        if match:
            current_no = int(match.group(1))
            questions[current_no] = []
            rest = clean_text(match.group(2))
            if rest:
                questions[current_no].append(rest)
            continue
        if current_no is not None:
            questions[current_no].append(para)

    parsed = {
        number: clean_text("\n".join(dedupe_question_lines(lines)))
        for number, lines in questions.items()
        if 1 <= number <= expected_count
    }
    expected = set(range(1, expected_count + 1))
    missing = sorted(expected - set(parsed))
    extra = sorted(set(parsed) - expected)
    if missing or extra:
        raise ValueError(f"question parse mismatch: missing={missing}, extra={extra}")
    return parsed


def parse_answers(paragraphs: list[str], expected_count: int) -> dict[int, int]:
    text = "\n".join(paragraphs)
    tokens = re.findall(r"\d{1,3}|[\u2460\u2461\u2462\u2463\u2464]", text)
    answers: dict[int, int] = {}
    idx = 0
    while idx + 1 < len(tokens):
        number_token, answer_token = tokens[idx], tokens[idx + 1]
        if number_token.isdigit() and answer_token in CIRCLED_TO_NO:
            number = int(number_token)
            if 1 <= number <= expected_count:
                answers[number] = CIRCLED_TO_NO[answer_token]
                idx += 2
                continue
        idx += 1

    expected = set(range(1, expected_count + 1))
    missing = sorted(expected - set(answers))
    extra = sorted(set(answers) - expected)
    if missing or extra:
        raise ValueError(f"answer parse mismatch: missing={missing}, extra={extra}")
    return answers


def classify_law(subject_area: str, question_no: int) -> str:
    if subject_area == "\uacf5\ubc95":
        return "\ud5cc\ubc95" if question_no <= 20 else "\ud589\uc815\ubc95"
    if subject_area == "\ud615\uc0ac\ubc95":
        return "\ud615\ubc95" if question_no <= 20 else "\ud615\uc0ac\uc18c\uc1a1\ubc95"
    if question_no <= 35 or question_no in (46, 47):
        return "\ubbfc\ubc95"
    if 36 <= question_no <= 45 or 48 <= question_no <= 51:
        return "\ubbfc\uc0ac\uc18c\uc1a1\ubc95"
    return "\uc0c1\ubc95"


def build_items(
    *,
    source_root: Path,
    exam_year: int,
    bar_round: int,
    public_label: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not source_root.exists():
        raise FileNotFoundError(f"source root not found: {source_root}")

    items: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    for round_no, month in ROUND_MONTHS.items():
        round_directory = find_round_dir(source_root, exam_year, round_no)
        for subject_area, expected_count in SUBJECTS:
            directory = find_subject_dir(round_directory, subject_area)
            question_file = find_one(directory, "\uc120\ud0dd\ud615 \ubb38\uc81c")
            answer_file = find_one(directory, "\uc120\ud0dd\ud615 \uc815\ub2f5\ud45c")
            questions = parse_questions(document_paragraphs(question_file), expected_count)
            answers = parse_answers(document_paragraphs(answer_file), expected_count)
            for question_no in range(1, expected_count + 1):
                law_name = classify_law(subject_area, question_no)
                items.append(
                    {
                        "id": f"mock{bar_round}_{exam_year}_r{round_no:02d}_{subject_area}_q{question_no:03d}",
                        "publicSource": public_label,
                        "displaySource": public_label,
                        "displayQuestionNo": None,
                        "subjectArea": subject_area,
                        "lawName": law_name,
                        "originalQuestionText": questions[question_no],
                        "answerNo": answers[question_no],
                        "answerChoice": list(CIRCLED_TO_NO)[answers[question_no] - 1],
                        "source": {
                            "examYear": exam_year,
                            "mockRound": round_no,
                            "sourceMonth": month,
                            "questionNo": question_no,
                            "subjectArea": subject_area,
                            "questionFile": str(question_file),
                            "answerFile": str(answer_file),
                        },
                        "copyrightHandling": {
                            "publicLabelOnly": True,
                            "rewriteForPublicUse": True,
                            "doNotDisplayMonthRoundOrQuestionNo": True,
                        },
                    }
                )
            summary.append(
                {
                    "mockRound": round_no,
                    "sourceMonth": month,
                    "subjectArea": subject_area,
                    "questionCount": len(questions),
                    "answerCount": len(answers),
                    "questionFile": str(question_file),
                    "answerFile": str(answer_file),
                }
            )
    return items, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--exam-year", type=int, default=2025)
    parser.add_argument("--bar-round", type=int, default=15)
    parser.add_argument("--public-label", default=PUBLIC_SOURCE_LABEL)
    args = parser.parse_args()

    items, summary = build_items(
        source_root=args.source_root,
        exam_year=args.exam_year,
        bar_round=args.bar_round,
        public_label=args.public_label,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": f"mock{args.bar_round}_{args.exam_year}_choice_sources_v001",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "publicSourceLabel": args.public_label,
        "publicDisplayRule": f"Do not display {args.exam_year} mock month, round, or question number.",
        "items": items,
        "summary": summary,
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(items)} questions to {args.out}")
    for row in summary:
        print(
            f"round={row['mockRound']} month={row['sourceMonth']} "
            f"subject={row['subjectArea']} questions={row['questionCount']} answers={row['answerCount']}"
        )


if __name__ == "__main__":
    main()
