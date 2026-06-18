#!/usr/bin/env python3
r"""Build local-only CLAT atoms from 2025 mock bar-exam source JSON.

The generated JSON files stay under C:\cowork\law-test-private.  They keep
month/round/question metadata locally, while public labels are reduced to
"변호사시험 15회 예상" for upload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


PRIVATE_ROOT = Path(r"C:\cowork\law-test-private\private_problem_banks")
DEFAULT_SOURCE = PRIVATE_ROOT / "mock15" / "mock15_2025_choice_sources_v001.json"
DEFAULT_CURRENT = PRIVATE_ROOT / "current"
DEFAULT_OUT = PRIVATE_ROOT / "mock15"
CURRENT_CLAT = DEFAULT_CURRENT / "ox_clat_unified_v001.json"
PUBLIC_LABEL = "변호사시험 15회 예상"

CIRCLED = "①②③④⑤"
CIRCLED_TO_NO = {ch: idx + 1 for idx, ch in enumerate(CIRCLED)}
NO_TO_CIRCLED = {idx + 1: ch for idx, ch in enumerate(CIRCLED)}
LETTER_MARKS = "ㄱㄴㄷㄹㅁㅂ"

SUBJECT_ORDER = ["민법", "민사소송법", "상법", "형법", "형사소송법", "헌법", "행정법"]
SUBJECT_AREA_BY_LAW = {
    "민법": "민사법",
    "민사소송법": "민사법",
    "상법": "민사법",
    "형법": "형사법",
    "형사소송법": "형사법",
    "헌법": "공법",
    "행정법": "공법",
}
SUBJECT_KEYWORDS = {
    "상법": [
        "상법", "상인", "상행위", "상호계산", "상호", "상업등기", "상업사용인", "지배인", "대리상",
        "회사", "주식", "주주", "이사", "대표이사", "감사", "합병", "분할", "어음", "수표", "배서",
        "보험", "보험자", "보험계약", "피보험자", "보험료", "운송", "운송인", "운송주선", "해상",
    ],
    "민사소송법": [
        "민사소송", "소송", "관할", "법원", "당사자능력", "소송능력", "소송대리", "변론",
        "송달", "증거", "문서제출", "판결", "화해권고", "항소", "상고", "재심", "독촉절차",
        "공시최고", "집행정지", "소송비용", "청구취지", "청구원인",
    ],
    "형사소송법": [
        "형사소송", "피의자", "피고인", "검사", "사법경찰", "체포", "구속", "압수", "수색",
        "영장", "공소", "공소사실", "기소", "불기소", "재정신청", "공판", "증거능력",
        "전문증거", "자백", "보석", "항소", "상고", "약식명령", "고소", "친고죄",
    ],
    "형법": [
        "형법", "죄", "범죄", "처벌", "구성요건", "위법성", "책임", "고의", "과실", "미수",
        "공범", "정범", "교사", "방조", "살인", "상해", "폭행", "협박", "강요", "체포감금",
        "절도", "강도", "사기", "공갈", "횡령", "배임", "손괴", "주거침입", "명예훼손",
        "업무방해", "문서", "공무집행방해", "뇌물",
    ],
    "헌법": [
        "헌법", "기본권", "평등권", "신체의 자유", "표현의 자유", "직업의 자유", "재산권",
        "국회", "대통령", "정부", "법률안", "헌법재판소", "위헌", "헌법소원", "탄핵", "정당",
        "선거", "국민투표",
    ],
    "행정법": [
        "행정", "행정청", "처분", "취소소송", "무효확인", "부작위", "행정심판", "재량",
        "하자", "인가", "허가", "신고", "부관", "대집행", "이행강제금", "국가배상",
        "손실보상", "정보공개", "공무원", "공물", "행정절차",
    ],
}
GRADE_BY_SUBJECT = {
    "민법": "A",
    "민사소송법": "A",
    "상법": "A",
    "형법": "A",
    "형사소송법": "A",
    "헌법": "A",
    "행정법": "A",
}
WEIGHT_BY_GRADE = {
    "S": 0.95,
    "A+": 0.82,
    "A": 0.68,
    "B+": 0.52,
    "B": 0.4,
    "C+": 0.28,
    "C": 0.22,
}

ARTICLE_RE = re.compile(
    r"(?:(민법|민사소송법|상법|형법|형사소송법|헌법|행정기본법|행정소송법|국가배상법|공직선거법|"
    r"행정심판법|지방자치법|상가건물 임대차보호법|주택임대차보호법)\s*)?"
    r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?(?:\s*제\s*\d+\s*항)?"
)
CASE_RE = re.compile(
    r"(?:대법원|헌법재판소|헌재)\s*\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.\s*"
    r"(?:선고|자|결정)?\s*[0-9가-힣헌바헌마두다도모초초기카합노]+(?:\s*[0-9가-힣헌바헌마두다도모초초기카합노]+)*"
)
CASE_LABEL_REPLACEMENTS = {
    "甲": "당사자",
    "乙": "상대방",
    "丙": "제3자",
    "丁": "제4자",
}
ASCII_CASE_REPLACEMENTS = {
    "A": "당사자",
    "B": "상대방",
    "C": "제3자",
    "D": "제4자",
    "E": "제5자",
    "X": "목적물",
    "Y": "상대방",
}
PARTICLE_FIXES = {
    "상대방는": "상대방은",
    "상대방가": "상대방이",
    "상대방를": "상대방을",
    "제3자은": "제3자는",
    "제3자이": "제3자가",
    "제3자을": "제3자를",
    "제4자은": "제4자는",
    "제4자이": "제4자가",
    "제4자을": "제4자를",
    "제5자은": "제5자는",
    "제5자이": "제5자가",
    "제5자을": "제5자를",
    "목적물는": "목적물은",
    "목적물가": "목적물이",
    "목적물를": "목적물을",
    "당사자은": "당사자는",
    "당사자이": "당사자가",
    "당사자을": "당사자를",
}


def clean_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\u00a0", " ").replace("･", "·").replace("ㆍ", "·")
    text = text.replace("｢", "").replace("｣", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def sha_id(*parts: str) -> str:
    raw = "|".join(clean_text(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def first_sentence(text: str) -> str:
    text = clean_text(text)
    if len(text) <= 220:
        return text
    # Keep the first legally meaningful sentence when a choice was extracted as a long bundle.
    pieces = re.split(r"(?<=[다음함됨임됨다])\.\s+", text)
    if pieces and 35 <= len(pieces[0]) <= 220:
        return pieces[0].rstrip(".") + "."
    return text[:220].rstrip(" ,;·") + "."


def strip_question_noise(text: str) -> str:
    text = clean_text(text)
    text = re.sub(r"^[①②③④⑤]\s*", "", text)
    text = re.sub(r"^[ㄱㄴㄷㄹㅁㅂ]\s*[.)]\s*", "", text)
    text = re.sub(r"\((?:다툼이 있는 경우 )?판례에 의함\)", "", text)
    text = re.sub(r"\((?:다툼이 있으면 )?판례에 따름\)", "", text)
    text = CASE_RE.sub("", text)
    text = re.sub(r"\s*,\s*(?:대법원|헌법재판소|헌재)\s*$", "", text)
    text = re.sub(r"(민법|민사소송법|상법|형법|형사소송법|헌법)\s+제\s*\d+\s*조(?:\s*의\s*\d+)?(?:\s*제\s*\d+\s*항)?", r"\1", text)
    text = re.sub(r"제\s*\d+\s*조(?:\s*의\s*\d+)?(?:\s*제\s*\d+\s*항)?", "관련 규정", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;")
    text = generalize_case_labels(text)
    return first_sentence(text)


def generalize_case_labels(text: str) -> str:
    for src, dst in CASE_LABEL_REPLACEMENTS.items():
        text = text.replace(src, dst)
    for src, dst in ASCII_CASE_REPLACEMENTS.items():
        text = re.sub(rf"(?<![A-Za-z]){re.escape(src)}(?![A-Za-z])", dst, text)
    for src, dst in PARTICLE_FIXES.items():
        text = text.replace(src, dst)
    text = re.sub(r"(당사자|상대방|제3자|제4자)\s*:", "", text)
    text = re.sub(r"\(\s*\d+\s*\)\s*에서(?:의)?", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def infer_subject(raw: str, fallback: str, context: str = "") -> str:
    combined = f"{raw} {context}"
    positions: list[tuple[int, str]] = []
    for subject in SUBJECT_ORDER:
        idx = combined.find(subject)
        if idx >= 0:
            positions.append((idx, subject))
    if positions:
        return sorted(positions)[0][1]
    scores = {
        subject: sum(combined.count(keyword) for keyword in keywords)
        for subject, keywords in SUBJECT_KEYWORDS.items()
    }
    best_subject, best_score = max(scores.items(), key=lambda kv: kv[1])
    if best_score:
        if fallback in {"민법", "민사소송법", "상법"} and best_subject in {"민법", "민사소송법", "상법"}:
            return best_subject
        if fallback in {"형법", "형사소송법"} and best_subject in {"형법", "형사소송법"}:
            return best_subject
        if fallback in {"헌법", "행정법"} and best_subject in {"헌법", "행정법"}:
            return best_subject
    return fallback


def reject_prompt(prompt: str, raw: str) -> bool:
    if len(prompt) < 12:
        return True
    if re.search(r"20\d{2}\s*(?:년|\.)", prompt) or re.search(r"\d{1,2}:\d{2}", prompt):
        return True
    if any(token in prompt for token in ("위 사실", "주소", "생략", "춘천시", "사무실 인근")):
        return True
    if any(token in prompt for token in ("“", "”", '"')):
        return True
    if re.search(r"\.\s+", prompt):
        return True
    if not re.search(r"(?:다|된다|한다|없다|있다|아니다)\.?$", prompt):
        return True
    if prompt.endswith(("는데.", "는데", "후.", "후", "로서.", "로서")):
        return True
    if prompt.endswith("?") or "?" in prompt:
        return True
    if re.match(r"^\(\s*\d+\s*\)", prompt):
        return True
    if re.search(r"(?:묻|답변|논의|말씀|청구인적격을 논외)", prompt):
        return True
    if any(ch in prompt for ch in ("甲", "乙", "丙", "丁")):
        return True
    if re.search(r"(?<![A-Za-z])[A-D](?![A-Za-z])", prompt):
        return True
    # Conversation-style choices are not minimal legal propositions.
    if re.search(r"[가-힣]{1,4}\s*:", raw):
        return True
    return False


def article_label(no: str, sub: str | None = None) -> str:
    return f"제{int(no)}조" + (f"의{int(sub)}" if sub else "")


def extract_article(text: str, subject: str) -> tuple[str, int | None, list[str], str]:
    refs: list[str] = []
    chosen = ""
    chosen_no: int | None = None
    for match in ARTICLE_RE.finditer(text):
        law, no, sub = match.group(1), match.group(2), match.group(3)
        label = article_label(no, sub)
        ref_law = law or subject
        ref = f"{ref_law} {label}"
        if ref not in refs:
            refs.append(ref)
        if not chosen and (not law or law == subject):
            chosen = label
            chosen_no = int(no)
    ref_text = " · ".join(refs[:5])
    return chosen, chosen_no, refs, ref_text


def topic_from_stem(stem: str) -> str:
    stem = clean_text(stem)
    stem = re.sub(r"\((?:.*?)\)", "", stem)
    stem = re.sub(r"에 관한.*$", "", stem)
    stem = re.sub(r"에 대한.*$", "", stem)
    stem = stem.replace("다음 설명 중", "").strip(" ?")
    return stem[:40] or "예상 기출"


def split_circled(text: str) -> tuple[str, dict[int, str]]:
    matches = list(re.finditer(r"[①②③④⑤]", text))
    if not matches:
        return text, {}
    stem = text[: matches[0].start()]
    choices: dict[int, str] = {}
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        no = CIRCLED_TO_NO[match.group(0)]
        choices[no] = text[match.end() : end].strip()
    return stem, choices


def split_letter_statements(text: str) -> tuple[str, dict[str, str]]:
    # Use the area before the first circled answer option as the statement block.
    first_choice = re.search(r"[①②③④⑤]", text)
    head = text[: first_choice.start()] if first_choice else text
    matches = list(re.finditer(r"(?:^|\n|\s)([ㄱㄴㄷㄹㅁㅂ])\s*[.]\s*", head))
    if not matches:
        return head, {}
    stem = head[: matches[0].start()]
    statements: dict[str, str] = {}
    for idx, match in enumerate(matches):
        mark = match.group(1)
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(head)
        body = head[match.end() : end].strip()
        if mark not in statements and len(body) > 8:
            statements[mark] = body
    return stem, statements


def selected_choice_text(choices: dict[int, str], answer_no: int) -> str:
    return clean_text(choices.get(answer_no, ""))


def parse_selected_letters(choice_text: str) -> set[str]:
    return set(re.findall(r"[ㄱㄴㄷㄹㅁㅂ]", choice_text))


def parse_ox_table(choice_text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for mark, ox in re.findall(r"([ㄱㄴㄷㄹㅁㅂ])\s*\(\s*([○×OX])\s*\)", choice_text):
        out[mark] = "O" if ox in {"○", "O"} else "X"
    return out


def infer_simple_answers(stem: str, choices: dict[int, str], answer_no: int) -> dict[int, str]:
    stem = clean_text(stem)
    negative = any(token in stem for token in ("옳지 않은", "타당하지 않은", "부당한", "잘못된"))
    positive = any(token in stem for token in ("옳은", "타당한", "정당한"))
    answers: dict[int, str] = {}
    for no in choices:
        if negative:
            answers[no] = "X" if no == answer_no else "O"
        elif positive:
            answers[no] = "O" if no == answer_no else "X"
        else:
            answers[no] = "O" if no == answer_no else "X"
    return answers


def infer_letter_answers(stem: str, choices: dict[int, str], answer_no: int, statements: dict[str, str]) -> dict[str, str]:
    selected = selected_choice_text(choices, answer_no)
    table = parse_ox_table(selected)
    if table:
        return {mark: table.get(mark, "O") for mark in statements}

    selected_marks = parse_selected_letters(selected)
    stem = clean_text(stem)
    selected_are_false = any(token in stem for token in ("옳지 않은", "타당하지 않은", "부당한", "잘못된"))
    selected_are_true = any(token in stem for token in ("옳은", "타당한", "정당한"))
    out: dict[str, str] = {}
    for mark in statements:
        if selected_are_false:
            out[mark] = "X" if mark in selected_marks else "O"
        elif selected_are_true:
            out[mark] = "O" if mark in selected_marks else "X"
        else:
            out[mark] = "O" if mark in selected_marks else "X"
    return out


def source_record(item: dict[str, Any], unit: str, answer: str) -> dict[str, Any]:
    source = item.get("source") or {}
    return {
        "id": item.get("id"),
        "examYear": source.get("examYear"),
        "mockRound": source.get("mockRound"),
        "sourceMonth": source.get("sourceMonth"),
        "questionNo": source.get("questionNo"),
        "subjectArea": source.get("subjectArea"),
        "lawName": item.get("lawName"),
        "unit": unit,
        "answer": answer,
        "publicLabel": PUBLIC_LABEL,
    }


def make_atom(item: dict[str, Any], *, unit: str, raw: str, answer: str, stem: str) -> dict[str, Any] | None:
    subject = infer_subject(raw, clean_text(item.get("lawName")), stem)
    if subject not in SUBJECT_ORDER:
        return None
    raw = clean_text(raw)
    prompt = strip_question_noise(raw)
    if reject_prompt(prompt, raw):
        return None
    article, art_no, article_refs, ref_text = extract_article(raw, subject)
    grade = GRADE_BY_SUBJECT.get(subject, "A")
    pid = "mock15-" + sha_id(subject, prompt, answer)
    topic = topic_from_stem(stem)
    explanation = "2025년 변호사시험 모의시험 지문을 공개용 법리 문장으로 정리한 예상 atom입니다."
    if ref_text:
        explanation += f" 근거 단서: {ref_text}."
    return {
        "art": article,
        "artNo": art_no,
        "pid": pid,
        "topic": topic,
        "rep": prompt,
        "a": answer,
        "why": explanation,
        "ref": ref_text,
        "src": [PUBLIC_LABEL],
        "years": [PUBLIC_LABEL],
        "freq": 1,
        "hot": True,
        "twins": [],
        "ids": [],
        "xref": [],
        "subject": subject,
        "subjectArea": SUBJECT_AREA_BY_LAW.get(subject, item.get("subjectArea")),
        "weight": WEIGHT_BY_GRADE[grade],
        "grade": grade,
        "sourceLayer": "mock_expected_atom",
        "mockYear": 2025,
        "mockRound": (item.get("source") or {}).get("mockRound"),
        "mockMonth": (item.get("source") or {}).get("sourceMonth"),
        "mockPublicLabel": PUBLIC_LABEL,
        "articleRefs": article_refs,
        "privateSources": [source_record(item, unit, answer)],
    }


def atoms_from_item(item: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    text = str(item.get("originalQuestionText") or "")
    answer_no = int(item.get("answerNo") or 0)
    stem_circled, choices = split_circled(text)
    stem_letters, letter_statements = split_letter_statements(text)
    atoms: list[dict[str, Any]] = []
    mode = "simple"

    if letter_statements and choices:
        mode = "letter"
        answers = infer_letter_answers(stem_letters, choices, answer_no, letter_statements)
        for mark, raw in letter_statements.items():
            atom = make_atom(item, unit=mark, raw=raw, answer=answers.get(mark, "O"), stem=stem_letters)
            if atom:
                atoms.append(atom)
    elif choices:
        mode = "choice"
        answers = infer_simple_answers(stem_circled, choices, answer_no)
        for no, raw in choices.items():
            atom = make_atom(item, unit=NO_TO_CIRCLED.get(no, str(no)), raw=raw, answer=answers.get(no, "O"), stem=stem_circled)
            if atom:
                atoms.append(atom)
    return atoms, mode


def atom_key(atom: dict[str, Any]) -> tuple[str, str, str]:
    prompt = re.sub(r"\s+", "", clean_text(atom.get("rep")))
    return clean_text(atom.get("subject")), prompt, clean_text(atom.get("a"))


def merge_atom(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    target["freq"] = int(target.get("freq") or 1) + int(incoming.get("freq") or 1)
    for key in ("years", "src"):
        target.setdefault(key, [])
        target[key].extend(incoming.get(key) or [])
    target.setdefault("privateSources", [])
    target["privateSources"].extend(incoming.get("privateSources") or [])
    if not target.get("ref") and incoming.get("ref"):
        target["ref"] = incoming["ref"]
    if not target.get("art") and incoming.get("art"):
        target["art"] = incoming["art"]
        target["artNo"] = incoming.get("artNo")
    refs = target.setdefault("articleRefs", [])
    for ref in incoming.get("articleRefs") or []:
        if ref not in refs:
            refs.append(ref)
    target["hot"] = bool(target.get("hot") or incoming.get("hot"))
    target["sourceLayer"] = target.get("sourceLayer") or incoming.get("sourceLayer")


def build_atoms(source_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = json.loads(source_path.read_text(encoding="utf-8"))
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    stats = Counter()
    mode_stats = Counter()
    skipped: list[str] = []
    for item in data.get("items") or []:
        atoms, mode = atoms_from_item(item)
        mode_stats[mode] += 1
        stats["source_questions"] += 1
        if not atoms:
            skipped.append(str(item.get("id")))
        for atom in atoms:
            key = atom_key(atom)
            if key in by_key:
                merge_atom(by_key[key], atom)
                stats["local_duplicates"] += 1
            else:
                by_key[key] = atom
            stats[f"subject:{atom['subject']}"] += 1
            stats[f"answer:{atom['a']}"] += 1
    atoms = list(by_key.values())
    atoms.sort(key=lambda x: (SUBJECT_ORDER.index(x.get("subject")) if x.get("subject") in SUBJECT_ORDER else 99, x.get("artNo") or 99999, x.get("rep", "")))
    audit = {
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "source": str(source_path),
        "sourceQuestions": stats["source_questions"],
        "atomCount": len(atoms),
        "rawAtomOccurrences": sum(int(atom.get("freq") or 1) for atom in atoms),
        "localDuplicatesMerged": stats["local_duplicates"],
        "modes": dict(mode_stats),
        "answers": {k.split(":", 1)[1]: v for k, v in stats.items() if k.startswith("answer:")},
        "subjects": {k.split(":", 1)[1]: v for k, v in stats.items() if k.startswith("subject:")},
        "skippedQuestionIds": skipped,
    }
    return atoms, audit


def payload_for_atoms(title: str, atoms: list[dict[str, Any]], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    subjects = Counter(atom.get("subject") for atom in atoms)
    answers = Counter(atom.get("a") for atom in atoms)
    payload = {
        "title": title,
        "version": "mock15-expected-v001",
        "publicSourceLabel": PUBLIC_LABEL,
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
        "count": len(atoms),
        "subjects": dict(subjects),
        "answers": dict(answers),
        "items": atoms,
    }
    if extra:
        payload.update(extra)
    return payload


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_current_clat(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def merge_into_current(current_path: Path, atoms: list[dict[str, Any]], *, backup: bool = True) -> dict[str, Any]:
    current = load_current_clat(current_path)
    items = list(current.get("items") or [])
    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in items:
        index[atom_key(item)] = item

    added = 0
    merged = 0
    for atom in atoms:
        key = atom_key(atom)
        if key in index:
            merge_atom(index[key], atom)
            index[key]["sourceLayer"] = index[key].get("sourceLayer") or "curated_atom"
            merged += 1
        else:
            items.append(atom)
            index[key] = atom
            added += 1

    if backup:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = current_path.with_name(current_path.stem + f".backup_{stamp}" + current_path.suffix)
        shutil.copy2(current_path, backup_path)

    current["items"] = items
    current["count"] = len(items)
    current["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    current["subjects"] = dict(Counter(clean_text(item.get("subject")) for item in items if clean_text(item.get("subject"))))
    current["answers"] = dict(Counter(clean_text(item.get("a")) for item in items if clean_text(item.get("a"))))
    layers = Counter(clean_text(item.get("sourceLayer")) or "unknown" for item in items)
    current["layers"] = dict(layers)
    write_json(current_path, current)
    return {"added": added, "merged": merged, "total": len(items)}


def write_outputs(atoms: list[dict[str, Any]], audit: dict[str, Any], out_dir: Path) -> None:
    all_payload = payload_for_atoms("2025년 변호사시험 모의시험 예상 atom", atoms, {"audit": audit})
    write_json(out_dir / "ox_mock15_2025_expected_atoms_v001.json", all_payload)
    by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for atom in atoms:
        by_subject[atom["subject"]].append(atom)
    for subject in SUBJECT_ORDER:
        subject_atoms = by_subject.get(subject, [])
        if subject_atoms:
            write_json(
                out_dir / f"ox_mock15_2025_expected_atoms_{subject}_v001.json",
                payload_for_atoms(f"2025년 변호사시험 모의시험 {subject} 예상 atom", subject_atoms),
            )
    write_json(out_dir / "ox_mock15_2025_expected_atoms_audit_v001.json", audit)


def render_md(audit: dict[str, Any], merge_result: dict[str, Any] | None) -> str:
    lines = [
        "# 2025년 변호사시험 모의시험 예상 atom 생성 보고",
        "",
        f"- 원본 문항: {audit['sourceQuestions']:,}개",
        f"- 생성 atom: {audit['atomCount']:,}개",
        f"- 원출처 발생 횟수: {audit['rawAtomOccurrences']:,}회",
        f"- 내부 중복 병합: {audit['localDuplicatesMerged']:,}회",
        "",
        "## 과목별",
    ]
    for subject, count in sorted(audit["subjects"].items(), key=lambda kv: SUBJECT_ORDER.index(kv[0]) if kv[0] in SUBJECT_ORDER else 99):
        lines.append(f"- {subject}: {count:,}개")
    lines += ["", "## O/X", *[f"- {k}: {v:,}개" for k, v in sorted(audit["answers"].items())]]
    if merge_result:
        lines += [
            "",
            "## CLAT 병합",
            f"- 새로 추가: {merge_result['added']:,}개",
            f"- 기존 atom에 병합: {merge_result['merged']:,}개",
            f"- 병합 후 총 CLAT atom: {merge_result['total']:,}개",
        ]
    if audit.get("skippedQuestionIds"):
        lines += ["", "## 확인 필요", f"- atom을 만들지 못한 문항: {len(audit['skippedQuestionIds']):,}개"]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--current-clat", type=Path, default=CURRENT_CLAT)
    parser.add_argument("--merge-current", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    atoms, audit = build_atoms(args.source)
    write_outputs(atoms, audit, args.out)
    merge_result = None
    if args.merge_current:
        merge_result = merge_into_current(args.current_clat, atoms, backup=not args.no_backup)
        audit["mergeResult"] = merge_result
        write_json(args.out / "ox_mock15_2025_expected_atoms_audit_v001.json", audit)
    (args.out / "ox_mock15_2025_expected_atoms_report_v001.md").write_text(render_md(audit, merge_result), encoding="utf-8")

    print(f"source={args.source}")
    print(f"out={args.out}")
    print(f"atoms={len(atoms)}")
    if merge_result:
        print(f"merged_added={merge_result['added']} merged_existing={merge_result['merged']} total={merge_result['total']}")


if __name__ == "__main__":
    main()
