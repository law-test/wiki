from __future__ import annotations

import json
import re
import sys
import zlib
from pathlib import Path
from typing import Any

try:
    import olefile
except ImportError as exc:  # pragma: no cover - local setup guard
    raise SystemExit(
        "olefile is required to read .hwp files. Install it with: python -m pip install olefile"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT.parent / "법조윤리_기출_1-15" / "10_by_round"
OUT_JSON = ROOT / "assets" / "legal_ethics_exam_questions.json"

LAW_AS_OF = "2026-06-17"
VERIFIED_AT = "2026-06-17"
ANSWER_MARKS = {"1": "①", "2": "②", "3": "③", "4": "④"}
CHOICE_MARKS = "①②③④⑤"

ROUND_CONFIG = {
    **{
        round_no: {
            "year": 2009 + round_no,
            "roundName": f"제{round_no:02d}회",
            "questionFile": f"제{round_no:02d}회_법조윤리시험_문제.hwp",
            "answerFile": f"제{round_no:02d}회_법조윤리시험_최종정답.hwp",
            "answerMemo": f"제{round_no:02d}회_정답확정_메모.txt",
            "answerStatus": "final",
        }
        for round_no in range(1, 14)
    },
    14: {
        "year": 2023,
        "roundName": "제14회",
        "questionFile": "제14회_법조윤리시험_문제.hwp",
        "answerFile": "제14회_법조윤리시험_정답가안.hwp",
        "answerMemo": "제14회_정답확정_메모.txt",
        "answerStatus": "final_same_as_draft",
    },
    15: {
        "year": 2024,
        "roundName": "제15회",
        "questionFile": "제15회_법조윤리시험_문제.hwp",
        "answerFile": "제15회_법조윤리시험_정답가안.hwp",
        "answerMemo": "제15회_정답확정_메모.txt",
        "answerStatus": "final_same_as_draft",
    }
}

# HWP extraction can surface private control text as readable-looking junk.
# Keep the list narrow so legal person labels such as 甲, 乙, 丙, 丁 remain intact.
ARTIFACT_CHARS = set("՚ĀלΘƘƤ氠瑢捤獥汤捯慤桥潴景湯쪽")
DROP_LINES = {
    "법 조 윤 리",
    "이하부터는 여백입니다",
}


def hwp_body_text(path: Path) -> str:
    ole = olefile.OleFileIO(path)
    compressed = bool(ole.openstream("FileHeader").read()[36] & 1)
    sections = sorted(
        entry
        for entry in ole.listdir(streams=True, storages=False)
        if len(entry) == 2 and entry[0] == "BodyText" and entry[1].startswith("Section")
    )
    pieces: list[str] = []
    for section in sections:
        data = ole.openstream(section).read()
        if compressed:
            data = zlib.decompress(data, -15)
        offset = 0
        while offset + 4 <= len(data):
            header = int.from_bytes(data[offset : offset + 4], "little")
            tag_id = header & 0x3FF
            size = (header >> 20) & 0xFFF
            offset += 4
            if size == 0xFFF:
                if offset + 4 > len(data):
                    break
                size = int.from_bytes(data[offset : offset + 4], "little")
                offset += 4
            payload = data[offset : offset + size]
            offset += size
            if tag_id == 67:
                pieces.append(payload.decode("utf-16le", errors="ignore"))
    return "\n".join(pieces)


def clean_line(value: str) -> str:
    cleaned = "".join(" " if ch in ARTIFACT_CHARS else ch for ch in value)
    cleaned = cleaned.replace("\u00a0", " ").replace("\u3000", " ").replace("\u2ce0", " ")
    cleaned = re.sub(r"[\x00-\x1f]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def clean_lines(text: str, *, keep_numeric: bool = False) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = clean_line(raw)
        if not line or line in DROP_LINES:
            continue
        if not keep_numeric and re.fullmatch(r"[0-9. ]+", line):
            continue
        lines.append(line)
    return lines


def append_text(values: list[str], line: str) -> None:
    if line:
        values.append(line)


def choice_segments(line: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(rf"[{CHOICE_MARKS}]", line))
    if not matches or matches[0].start() != 0:
        return []
    segments: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(line)
        segments.append((match.group(0), line[match.end() : end].strip()))
    return segments


def parse_questions(question_path: Path) -> list[dict[str, Any]]:
    lines = clean_lines(hwp_body_text(question_path))
    questions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    stem_lines: list[str] = []
    active_choice: str | None = None

    def flush() -> None:
        nonlocal current, stem_lines, active_choice
        if current is None:
            return
        current["stem"] = " ".join(stem_lines).strip()
        questions.append(current)
        current = None
        stem_lines = []
        active_choice = None

    for line in lines:
        match_question = re.match(r"^문\s*(\d+)\.\s*(.*)$", line)
        if match_question:
            flush()
            current = {
                "number": int(match_question.group(1)),
                "stem": "",
                "choices": {},
            }
            stem_lines = []
            active_choice = None
            append_text(stem_lines, match_question.group(2))
            continue

        if current is None:
            continue

        segments = choice_segments(line)
        if segments:
            for mark, body in segments:
                active_choice = mark
                current["choices"][active_choice] = body
            continue

        if active_choice:
            current["choices"][active_choice] = (
                f"{current['choices'][active_choice]} {line}".strip()
            )
        else:
            append_text(stem_lines, line)

    flush()
    return questions


def parse_answers(answer_path: Path) -> dict[int, str]:
    lines = clean_lines(hwp_body_text(answer_path), keep_numeric=True)
    digit_lines = [int(line) for line in lines if re.fullmatch(r"\d+", line)]
    if len(digit_lines) % 2 != 0:
        raise ValueError(f"Unexpected answer digit count: {len(digit_lines)}")

    answers: dict[int, str] = {}
    for idx in range(0, len(digit_lines), 2):
        number = digit_lines[idx]
        answer_no = str(digit_lines[idx + 1])
        if not (1 <= number <= 40 and answer_no in ANSWER_MARKS):
            raise ValueError(f"Unexpected answer pair: {number}, {answer_no}")
        answers[number] = ANSWER_MARKS[answer_no]
    return answers


def build_round(round_no: int, config: dict[str, Any]) -> dict[str, Any]:
    source_dir = SOURCE_ROOT / config["roundName"]
    question_path = source_dir / config["questionFile"]
    answer_path = source_dir / config["answerFile"]
    memo_path = source_dir / config["answerMemo"]

    questions = parse_questions(question_path)
    answers = parse_answers(answer_path)
    final_memo = memo_path.read_text(encoding="utf-8").strip() if memo_path.exists() else ""

    if len(questions) != 40:
        raise ValueError(f"{config['roundName']} question count mismatch: {len(questions)}")
    if sorted(q["number"] for q in questions) != list(range(1, 41)):
        raise ValueError(f"{config['roundName']} question numbers are not 1..40")
    if sorted(answers) != list(range(1, 41)):
        raise ValueError(f"{config['roundName']} answers are not 1..40")

    built_questions: list[dict[str, Any]] = []
    for item in questions:
        number = item["number"]
        choices = item["choices"]
        if set(choices) != set("①②③④"):
            raise ValueError(f"Question {number} choices mismatch: {sorted(choices)}")
        built_questions.append(
            {
                "id": f"legal_ethics_r{round_no:02d}_q{number:02d}",
                "round": round_no,
                "number": number,
                "original": {
                    "stem": item["stem"],
                    "choices": choices,
                    "officialAnswer": answers[number],
                    "sourceQuestionFile": config["questionFile"],
                    "sourceAnswerFile": config["answerFile"],
                },
                "current": {
                    "changed": False,
                    "stem": None,
                    "choices": None,
                    "answer": answers[number],
                    "lawAsOf": LAW_AS_OF,
                    "verifiedAt": VERIFIED_AT,
                    "basis": "2026-06-17 기준 현행 법령 및 판례 기준으로 검토 예정",
                    "note": "",
                },
                "atoms": [],
            }
        )

    return {
        "examId": f"legal_ethics_r{round_no:02d}",
        "round": round_no,
        "year": config["year"],
        "title": f"{config['roundName']} 법조윤리시험",
        "questionCount": len(built_questions),
        "answerStatus": config["answerStatus"],
        "finalAnswerMemo": final_memo,
        "source": {
            "questionFile": str(question_path),
            "answerFile": str(answer_path),
            "answerMemo": str(memo_path),
        },
        "lawAsOf": LAW_AS_OF,
        "verifiedAt": VERIFIED_AT,
        "questions": built_questions,
    }


def build_database() -> dict[str, Any]:
    rounds = {str(round_no): build_round(round_no, config) for round_no, config in ROUND_CONFIG.items()}
    data = {
        "schemaVersion": 1,
        "subject": "법조윤리",
        "description": "법조윤리시험 기출 원문과 현행 법령 기준 검토본을 분리해 보관하는 문제은행입니다.",
        "lawAsOf": LAW_AS_OF,
        "verifiedAt": VERIFIED_AT,
        "rounds": rounds,
    }
    preserve_existing_review(data)
    return data


def preserve_existing_review(data: dict[str, Any]) -> None:
    if not OUT_JSON.exists():
        return
    existing = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    existing_rounds = existing.get("rounds") or {}
    for round_key, round_data in data["rounds"].items():
        previous = existing_rounds.get(round_key)
        if not previous:
            continue
        previous_questions = {
            item.get("number"): item for item in previous.get("questions", []) if item.get("number")
        }
        for question in round_data.get("questions", []):
            old_question = previous_questions.get(question.get("number"))
            if not old_question:
                continue
            if old_question.get("current"):
                question["current"] = old_question["current"]
            if old_question.get("atoms"):
                question["atoms"] = old_question["atoms"]
        for key in ["reviewStatus", "reviewNote"]:
            if key in previous:
                round_data[key] = previous[key]


def validate_no_artifacts(data: Any) -> None:
    text = json.dumps(data, ensure_ascii=False)
    leftovers = sorted(ch for ch in ARTIFACT_CHARS if ch in text)
    if leftovers:
        raise ValueError(f"Artifact characters remain: {''.join(leftovers)}")


def main() -> int:
    data = build_database()
    validate_no_artifacts(data)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    round_summaries = {
        round_key: {
            "round": round_data["round"],
            "questions": round_data["questionCount"],
            "firstAnswer": round_data["questions"][0]["current"]["answer"],
            "lastAnswer": round_data["questions"][-1]["current"]["answer"],
        }
        for round_key, round_data in sorted(data["rounds"].items(), key=lambda item: int(item[0]))
    }
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(OUT_JSON),
                "rounds": round_summaries,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
