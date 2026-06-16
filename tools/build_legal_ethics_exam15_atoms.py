from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
QUESTION_BANK = ROOT / "assets" / "legal_ethics_exam_questions.json"
OUT_JSON = ROOT / "assets" / "ox_legal_ethics_exam15.json"


ROUND_NO = 15
SOURCE_TAG = "법윤15"

CHOICE_MARKS = "①②③④"
JAMO_RE = re.compile(r"([\u3131-\u314e])\.")

QUESTION_OVERRIDES: dict[int, dict[str, Any]] = {
    2: {"predicate": "이 사례는 변호사의 징계 대상이 된다."},
    5: {"predicate": "이는 변호사법상 형사처벌의 대상이 아니다.", "answerMeansTrue": True},
    9: {"predicate": "이 사람은 법률사무소 사무직원으로 채용될 자격이 없다."},
    16: {"predicate": "이는 변호사법상 형사처벌의 대상이다.", "answerMeansTrue": True},
    22: {"predicate": "이 광고 행위는 허용된다.", "answerMeansTrue": True},
}


def norm(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    text = text.replace(" .", ".").replace(" ,", ",")
    return text


def article_no_value(article_no: str) -> int | None:
    match = re.search(r"제\s*(\d+)", article_no or "")
    return int(match.group(1)) if match else None


def atom_article(current: dict[str, Any]) -> tuple[str, int | None]:
    articles = current.get("basisArticles") or []
    if articles:
        first = articles[0]
        art = f"{first.get('lawName', '').strip()} {first.get('articleNo', '').strip()}".strip()
        return art, article_no_value(first.get("articleNo", ""))
    return "법조윤리 제15회", None


def split_list_stem(stem: str) -> tuple[str, list[tuple[str, str]]]:
    matches = list(JAMO_RE.finditer(stem))
    if len(matches) < 2:
        return stem, []
    head = norm(stem[: matches[0].start()])
    entries: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(stem)
        entries.append((match.group(1), norm(stem[start:end])))
    return head, entries


def answer_choice(question: dict[str, Any]) -> str:
    return question["original"]["choices"][question["current"]["answer"]]


def selected_letters(question: dict[str, Any]) -> set[str]:
    return set(re.findall(r"[\u3131-\u314e]", answer_choice(question)))


def answer_is_false_prompt(stem: str) -> bool:
    return any(token in stem for token in ["옳지 않은", "아닌 것은", "아닌 행위"])


def choice_truth(question: dict[str, Any], mark: str) -> bool:
    override = QUESTION_OVERRIDES.get(question["number"], {})
    if "answerMeansTrue" in override:
        return (mark == question["current"]["answer"]) is bool(override["answerMeansTrue"])
    if answer_is_false_prompt(question["original"]["stem"]):
        return mark != question["current"]["answer"]
    return mark == question["current"]["answer"]


def list_truth(question: dict[str, Any], letter: str) -> bool:
    answer_letters = selected_letters(question)
    if "옳지 않은" in question["original"]["stem"]:
        return letter not in answer_letters
    return letter in answer_letters


def make_statement(question: dict[str, Any], raw: str) -> str:
    override = QUESTION_OVERRIDES.get(question["number"], {})
    predicate = override.get("predicate")
    text = norm(raw)
    if predicate:
        if text and text[-1] not in ".?!":
            text = f"{text}."
        return norm(f"{text} {predicate}")
    return text


def build_statements(question: dict[str, Any]) -> list[dict[str, Any]]:
    stem = question["original"]["stem"]
    _, entries = split_list_stem(stem)
    rows: list[dict[str, Any]] = []
    if entries:
        for letter, body in entries:
            rows.append(
                {
                    "text": make_statement(question, body),
                    "truth": list_truth(question, letter),
                    "sourcePart": letter,
                }
            )
        return rows

    for mark in CHOICE_MARKS:
        body = question["original"]["choices"].get(mark, "")
        if not body:
            continue
        rows.append(
            {
                "text": make_statement(question, body),
                "truth": choice_truth(question, mark),
                "sourcePart": mark,
            }
        )
    return rows


def atom_ref(question: dict[str, Any]) -> str:
    current = question["current"]
    articles = current.get("basisArticles") or []
    bits = [f"{a['lawName']} {a['articleNo']}" for a in articles[:4]]
    bits.extend((current.get("externalBasis") or [])[:2])
    return " · ".join(bits) or current.get("basis", "")


def atom_why(question: dict[str, Any]) -> str:
    tags = question["current"].get("reviewTags") or []
    tag_text = " · ".join(tags[:3])
    return f"법무부 제15회 법조윤리시험 확정정답과 2026-06-17 현행 검토 기준입니다." + (
        f" 핵심 쟁점: {tag_text}." if tag_text else ""
    )


def grade_for(question: dict[str, Any], statement_count: int) -> str:
    if statement_count >= 4:
        return "A"
    if question["current"].get("externalBasis"):
        return "B+"
    return "B"


def build_atoms() -> dict[str, Any]:
    data = json.loads(QUESTION_BANK.read_text(encoding="utf-8"))
    round15 = data["rounds"]["15"]
    items: list[dict[str, Any]] = []

    for question in round15["questions"]:
        statements = build_statements(question)
        oks = [row for row in statements if row["truth"]]
        xs = [row for row in statements if not row["truth"]]
        if not oks:
            raise ValueError(f"Question {question['number']} has no O statement")

        art, art_no = atom_article(question["current"])
        topic = (question["current"].get("reviewTags") or ["법조윤리"])[0]
        ref = atom_ref(question)
        why = atom_why(question)
        grade = grade_for(question, len(statements))
        weight = round(0.42 + min(len(statements), 4) * 0.08, 4)

        twin_buckets: list[list[dict[str, Any]]] = [[] for _ in oks]
        for idx, row in enumerate(xs):
            twin_buckets[idx % len(oks)].append(row)

        for idx, row in enumerate(oks, 1):
            items.append(
                {
                    "art": art,
                    "artNo": art_no,
                    "pid": f"legal-ethics-r{ROUND_NO:02d}-q{question['number']:02d}-{idx:02d}",
                    "topic": topic,
                    "rep": row["text"],
                    "a": "O",
                    "why": why,
                    "ref": ref,
                    "src": [SOURCE_TAG],
                    "years": [SOURCE_TAG],
                    "freq": 1,
                    "hot": False,
                    "twins": [
                        {
                            "q": twin["text"],
                            "trap": f"{topic} 함정",
                            "src": [SOURCE_TAG],
                            "weight": weight,
                            "grade": grade,
                            "ref": ref,
                        }
                        for twin in twin_buckets[idx - 1]
                    ],
                    "ids": [question["number"]],
                    "xref": [],
                    "subject": "법조윤리",
                    "weight": weight,
                    "grade": grade,
                    "sourceQuestionId": question["id"],
                    "sourcePart": row["sourcePart"],
                }
            )

    return {
        "title": "법조윤리 제15회 OX atom",
        "version": "2026-06-17.exam15.v1",
        "source": "제15회 법조윤리시험 공식 문제 및 확정정답",
        "lawAsOf": "2026-06-17",
        "subject": "법조윤리",
        "round": ROUND_NO,
        "count": len(items),
        "items": items,
    }


def validate(data: dict[str, Any]) -> None:
    items = data["items"]
    if not items:
        raise ValueError("No atoms generated")
    all_questions = {q for item in items for q in item.get("ids", [])}
    if all_questions != set(range(1, 41)):
        raise ValueError(f"Question coverage mismatch: {sorted(set(range(1, 41)) - all_questions)}")
    if any(not item.get("rep") for item in items):
        raise ValueError("Empty O statement")
    if any(item.get("a") != "O" for item in items):
        raise ValueError("Representative atoms must be O")
    for item in items:
        for twin in item.get("twins", []):
            if not twin.get("q"):
                raise ValueError(f"Empty twin in {item['pid']}")


def main() -> int:
    data = build_atoms()
    validate(data)
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    twin_count = sum(len(item.get("twins", [])) for item in data["items"])
    print(json.dumps({"status": "ok", "items": data["count"], "twins": twin_count}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
