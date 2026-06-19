from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz
import numpy as np
from PIL import Image

from build_mock15_choice_sources import (
    CIRCLED_TO_NO,
    SUBJECTS,
    classify_law,
    clean_text,
    dedupe_question_lines,
    document_paragraphs,
    parse_questions,
)


DEFAULT_SOURCE_ROOT = Path(r"C:\cowork\law-test-private\source_downloads\akls_2011_2012_mocks")
DEFAULT_OUT_ROOT = Path(r"C:\cowork\law-test-private\private_problem_banks")

SUBJECT_PAGE_INDEX = {
    "공법": 0,
    "형사법": 1,
    "민사법": 2,
}

SOURCE_MONTHS = {
    1: 7,
    2: 8,
    3: 10,
}

KNOWN_2012_ROUND2_PUBLIC_ANSWERS = {
    1: 4,
    2: 3,
    3: 5,
    4: 4,
    5: 3,
    6: 4,
    7: 1,
    8: 1,
    9: 2,
    10: 5,
    11: 5,
    12: 1,
    13: 0,
    14: 2,
    15: 2,
    16: 2,
    17: 3,
    18: 5,
    19: 3,
    20: 2,
    21: 5,
    22: 5,
    23: 2,
    24: 4,
    25: 4,
    26: 3,
    27: 5,
    28: 4,
    29: 3,
    30: 1,
    31: 2,
    32: 5,
    33: 1,
    34: 4,
    35: 4,
    36: 3,
    37: 3,
    38: 1,
    39: 5,
    40: 3,
}


def pdf_text(path: Path, page_index: int = 0) -> str:
    try:
        doc = fitz.open(path)
        return clean_text(doc[page_index].get_text())
    except Exception:
        return ""


def sort_key(path: Path) -> tuple[int, str]:
    match = re.match(r"\s*(\d+)", path.name)
    return (int(match.group(1)) if match else 999, path.name)


def find_dir_by_prefix(root: Path, prefix: str) -> Path:
    matches = [path for path in root.iterdir() if path.is_dir() and path.name.startswith(prefix)]
    if len(matches) != 1:
        raise FileNotFoundError(f"expected one directory starting {prefix!r}, found {len(matches)}")
    return matches[0]


def find_pdf_by_prefix(root: Path, prefix: str) -> Path:
    matches = [path for path in root.glob(f"{prefix}*.pdf") if path.is_file()]
    if len(matches) != 1:
        raise FileNotFoundError(f"expected one pdf starting {prefix!r}, found {len(matches)}")
    return matches[0]


def find_choice_question_pdf(base_dir: Path, subject_area: str) -> Path:
    normalized_subject = subject_area.replace(" ", "")
    candidates: list[tuple[int, Path, str]] = []
    for path in base_dir.rglob("*.pdf"):
        if path.stat().st_size < 80_000:
            continue
        text = pdf_text(path, 0)
        compact = re.sub(r"\s+", "", text)
        if "선택형" not in compact:
            continue
        if f"시험과목{normalized_subject}" not in compact:
            continue
        page_count = fitz.open(path).page_count
        candidates.append((page_count, path, text))
    if not candidates:
        raise FileNotFoundError(f"choice question pdf not found: {base_dir} / {subject_area}")

    # Prefer the shortest 선택형 question booklet, not the longer statute booklets.
    candidates.sort(key=lambda row: (sort_key(row[1])[0], row[0], row[1].stat().st_size))
    return candidates[0][1]


def render_page(path: Path, page_index: int, zoom: float = 3.0) -> Image.Image:
    doc = fitz.open(path)
    page = doc[page_index]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def group_positions(values: list[int], tolerance: int = 8) -> list[int]:
    grouped: list[list[int]] = []
    for value in values:
        if not grouped or value - grouped[-1][-1] > tolerance:
            grouped.append([value])
        else:
            grouped[-1].append(value)
    return [int(round(sum(group) / len(group))) for group in grouped]


def detect_answer_table_lines(image: Image.Image) -> tuple[list[int], list[int]]:
    gray = np.array(image.convert("L"))
    height, width = gray.shape
    y0 = int(height * 0.15)
    y1 = int(height * 0.95)

    vertical_dark = gray < 110
    vertical_counts = vertical_dark[y0:y1, :].sum(axis=0)
    verticals = group_positions(
        np.where(vertical_counts > (y1 - y0) * 0.35)[0].tolist(),
        8,
    )

    horizontal_counts = (gray < 110).sum(axis=1)
    horizontals = group_positions(
        np.where(horizontal_counts > width * 0.30)[0].tolist(),
        8,
    )
    horizontals = [line for line in horizontals if line > int(height * 0.18)]
    if len(verticals) < 3 or len(horizontals) < 4:
        raise ValueError("answer table line detection failed")
    return verticals, horizontals


def answer_cells(image: Image.Image) -> list[tuple[int, Image.Image]]:
    verticals, horizontals = detect_answer_table_lines(image)
    blocks = (len(verticals) - 1) // 2
    rows = len(horizontals) - 2
    cells: list[tuple[int, Image.Image]] = []
    for block_index in range(blocks):
        for row_index in range(rows):
            question_no = block_index * rows + row_index + 1
            x0 = verticals[block_index * 2 + 1] + 5
            x1 = verticals[block_index * 2 + 2] - 5
            y0 = horizontals[row_index + 1] + 5
            y1 = horizontals[row_index + 2] - 5
            cells.append((question_no, image.crop((x0, y0, x1, y1))))
    return cells


def answer_feature(cell: Image.Image) -> tuple[np.ndarray | None, float | None]:
    gray = np.array(cell.convert("L"))
    mask = gray < 180
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None, None
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    box_width = x1 - x0
    box_height = y1 - y0
    cropped = cell.crop(
        (
            max(0, x0 - 2),
            max(0, y0 - 2),
            min(cell.width, x1 + 2),
            min(cell.height, y1 + 2),
        )
    )
    resized = cropped.convert("L").resize((64, 64))
    array = (255 - np.array(resized)).astype("float32") / 255.0
    norm = np.linalg.norm(array)
    if norm:
        array = array / norm
    return array, box_width / max(1, box_height)


class ImageAnswerReader:
    def __init__(self, template_pdf: Path) -> None:
        image = render_page(template_pdf, 0)
        cells = answer_cells(image)
        templates: dict[int, list[np.ndarray]] = {answer_no: [] for answer_no in range(1, 6)}
        for question_no, cell in cells:
            answer_no = KNOWN_2012_ROUND2_PUBLIC_ANSWERS.get(question_no, 0)
            if answer_no <= 0:
                continue
            feature, _ratio = answer_feature(cell)
            if feature is not None:
                templates[answer_no].append(feature)
        if any(not values for values in templates.values()):
            raise ValueError("image answer templates are incomplete")
        self.templates = templates

    def classify(self, cell: Image.Image) -> int:
        feature, ratio = answer_feature(cell)
        if feature is None:
            return 0
        if ratio is not None and ratio > 1.45:
            return 0
        best_answer = 0
        best_score = -1.0
        for answer_no, templates in self.templates.items():
            for template in templates:
                score = float((feature * template).sum())
                if score > best_score:
                    best_answer = answer_no
                    best_score = score
        if best_score < 0.80:
            return 0
        return best_answer

    def read_page(self, pdf_path: Path, page_index: int, expected_count: int) -> dict[int, int]:
        image = render_page(pdf_path, page_index)
        parsed: dict[int, int] = {}
        for question_no, cell in answer_cells(image):
            if question_no > expected_count:
                continue
            parsed[question_no] = self.classify(cell)
        missing = sorted(set(range(1, expected_count + 1)) - set(parsed))
        if missing:
            raise ValueError(f"image answer parse missing={missing}")
        return parsed


def parse_text_answers(answer_pdf: Path, expected_count: int) -> dict[int, int]:
    doc = fitz.open(answer_pdf)
    text = "\n".join(doc[page].get_text() for page in range(doc.page_count))
    tokens = re.findall(
        r"\d{1,3}|[\u2460-\u2464\u2776-\u277a\u2780-\u2784]",
        text,
    )
    answers: dict[int, int] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.isdigit():
            index += 1
            continue
        number = int(token)
        if not (1 <= number <= expected_count):
            index += 1
            continue
        index += 1
        answer_tokens: list[str] = []
        while index < len(tokens) and tokens[index] in CIRCLED_TO_NO:
            answer_tokens.append(tokens[index])
            index += 1
        if not answer_tokens:
            continue
        answers[number] = CIRCLED_TO_NO[answer_tokens[0]] if len(answer_tokens) == 1 else 0

    missing = sorted(set(range(1, expected_count + 1)) - set(answers))
    if missing:
        raise ValueError(f"text answer parse missing={missing}")
    return answers


def parse_early_questions(paragraphs: list[str], expected_count: int) -> dict[int, str]:
    questions: dict[int, list[str]] = {}
    current_no: int | None = None
    pending_question_marker = False

    for paragraph in paragraphs:
        para = clean_text(paragraph)
        if not para:
            continue
        if re.fullmatch(r"문", para):
            pending_question_marker = True
            continue

        explicit = re.match(r"^문\s*(\d{1,3})\s*\.?\s*(.*)$", para)
        plain = re.match(r"^(\d{1,3})\s*\.\s*(.*)$", para)
        prefixed_after_marker = re.search(r"(\d{1,3})\s*\.\s*(.*)$", para) if pending_question_marker else None
        number: int | None = None
        rest = ""
        marker_is_question = False
        if explicit:
            number = int(explicit.group(1))
            rest = clean_text(explicit.group(2))
            marker_is_question = current_no is None and number == 1 or current_no is not None and number == current_no + 1
        elif plain:
            number = int(plain.group(1))
            rest = clean_text(plain.group(2))
            marker_is_question = (
                (pending_question_marker and (current_no is None and number == 1 or current_no is not None and number == current_no + 1))
                or (current_no is not None and number == current_no + 1)
            )
        elif prefixed_after_marker:
            number = int(prefixed_after_marker.group(1))
            rest = clean_text(prefixed_after_marker.group(2))
            marker_is_question = current_no is not None and number == current_no + 1

        if marker_is_question and number is not None and 1 <= number <= expected_count:
            current_no = number
            questions[current_no] = []
            if rest:
                questions[current_no].append(rest)
            pending_question_marker = False
            continue

        pending_question_marker = False
        if current_no is not None:
            questions[current_no].append(para)

    parsed = {
        number: clean_text("\n".join(dedupe_question_lines(lines)))
        for number, lines in questions.items()
        if 1 <= number <= expected_count
    }
    missing = sorted(set(range(1, expected_count + 1)) - set(parsed))
    if missing:
        raise ValueError(f"early question parse mismatch: missing={missing}")
    return parsed


def find_2011_answer_pdfs(base_dir: Path) -> dict[str, Path]:
    answer_files: dict[str, Path] = {}
    for path in base_dir.rglob("*.pdf"):
        if path.stat().st_size >= 80_000:
            continue
        text = re.sub(r"\s+", "", pdf_text(path, 0))
        for subject_area, _expected_count in SUBJECTS:
            if f"과목명:{subject_area}" in text:
                answer_files[subject_area] = path
    missing = [subject_area for subject_area, _expected_count in SUBJECTS if subject_area not in answer_files]
    if missing:
        raise FileNotFoundError(f"2011 answer pdfs missing: {missing}")
    return answer_files


def build_round_items(
    *,
    exam_year: int,
    bar_round: int,
    mock_round: int,
    public_label: str,
    source_root: Path,
    image_reader: ImageAnswerReader | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if exam_year == 2012:
        prefix = "102_" if mock_round == 2 else "116_"
        source_dir = find_dir_by_prefix(source_root, prefix)
        answer_pdf = find_pdf_by_prefix(source_root, "102_2330" if mock_round == 2 else "116_2326")
        if image_reader is None:
            raise ValueError("image_reader is required for 2012")
        answer_by_subject = {
            subject_area: image_reader.read_page(answer_pdf, SUBJECT_PAGE_INDEX[subject_area], expected_count)
            for subject_area, expected_count in SUBJECTS
        }
    elif exam_year == 2011:
        source_dir = find_dir_by_prefix(source_root, "87_")
        answer_pdf_by_subject = find_2011_answer_pdfs(source_dir)
        answer_by_subject = {
            subject_area: parse_text_answers(answer_pdf_by_subject[subject_area], expected_count)
            for subject_area, expected_count in SUBJECTS
        }
    else:
        raise ValueError(f"unsupported early mock year: {exam_year}")

    month = SOURCE_MONTHS[mock_round]
    items: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    for subject_area, expected_count in SUBJECTS:
        question_pdf = find_choice_question_pdf(source_dir, subject_area)
        answers = answer_by_subject[subject_area]
        paragraphs = document_paragraphs(question_pdf)
        questions = (
            parse_early_questions(paragraphs, expected_count)
            if exam_year == 2011
            else parse_questions(paragraphs, expected_count)
        )
        answer_file = (
            find_pdf_by_prefix(source_root, "102_2330" if mock_round == 2 else "116_2326")
            if exam_year == 2012
            else find_2011_answer_pdfs(source_dir)[subject_area]
        )
        for question_no in range(1, expected_count + 1):
            law_name = classify_law(subject_area, question_no)
            answer_no = answers[question_no]
            items.append(
                {
                    "id": f"mock{bar_round}_{exam_year}_r{mock_round:02d}_{subject_area}_q{question_no:03d}",
                    "publicSource": public_label,
                    "displaySource": public_label,
                    "displayQuestionNo": None,
                    "subjectArea": subject_area,
                    "lawName": law_name,
                    "originalQuestionText": questions[question_no],
                    "answerNo": answer_no,
                    "answerChoice": "복수정답/판독제외" if answer_no == 0 else list(CIRCLED_TO_NO)[answer_no - 1],
                    "source": {
                        "examYear": exam_year,
                        "mockRound": mock_round,
                        "sourceMonth": month,
                        "questionNo": question_no,
                        "subjectArea": subject_area,
                        "questionFile": str(question_pdf),
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
                "mockRound": mock_round,
                "sourceMonth": month,
                "subjectArea": subject_area,
                "questionCount": len(questions),
                "answerCount": len(answers),
                "questionFile": str(question_pdf),
                "answerFile": str(answer_file),
                "excludedAnswerCount": sum(1 for value in answers.values() if value == 0),
            }
        )
    return items, summary


def write_payload(
    *,
    out: Path,
    exam_year: int,
    bar_round: int,
    public_label: str,
    items: list[dict[str, Any]],
    summary: list[dict[str, Any]],
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": f"mock{bar_round}_{exam_year}_choice_sources_v001",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "publicSourceLabel": public_label,
        "publicDisplayRule": f"Do not display {exam_year} mock month, round, or question number.",
        "items": items,
        "summary": summary,
        "missingSources": [],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--exam-year", type=int, required=True, choices=[2011, 2012])
    parser.add_argument("--bar-round", type=int, required=True)
    parser.add_argument("--public-label", required=True)
    args = parser.parse_args()

    image_reader = None
    if args.exam_year == 2012:
        image_reader = ImageAnswerReader(find_pdf_by_prefix(args.source_root, "102_2330"))
        mock_rounds = [2, 3]
    else:
        mock_rounds = [1]

    items: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    for mock_round in mock_rounds:
        round_items, round_summary = build_round_items(
            exam_year=args.exam_year,
            bar_round=args.bar_round,
            mock_round=mock_round,
            public_label=args.public_label,
            source_root=args.source_root,
            image_reader=image_reader,
        )
        items.extend(round_items)
        summary.extend(round_summary)

    out = args.out_root / f"mock{args.bar_round}" / f"mock{args.bar_round}_{args.exam_year}_choice_sources_v001.json"
    write_payload(
        out=out,
        exam_year=args.exam_year,
        bar_round=args.bar_round,
        public_label=args.public_label,
        items=items,
        summary=summary,
    )
    print(f"wrote {len(items)} questions to {out}")
    for row in summary:
        print(
            f"round={row['mockRound']} month={row['sourceMonth']} "
            f"subject={row['subjectArea']} questions={row['questionCount']} "
            f"answers={row['answerCount']} excluded={row['excludedAnswerCount']}"
        )


if __name__ == "__main__":
    main()
