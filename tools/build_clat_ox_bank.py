from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
REPORTS = ROOT / "reports"

CIVIL_BANK = ASSETS / "ox_msa_unified_v001.json"
CRIMINAL_SOURCE = ASSETS / "ox_criminal_bar_all_source.json"
PUBLIC_SOURCE = ASSETS / "ox_public_bar_all_source.json"
OUT_BANK = ASSETS / "ox_clat_unified_v001.json"
OUT_AUDIT_JSON = REPORTS / "clat_ox_bank_audit.json"
OUT_AUDIT_MD = REPORTS / "clat_ox_bank_audit.md"


MANUAL_SOURCE_OVERRIDES: dict[tuple[str, int, int, str], dict[str, str]] = {
    (
        "criminal",
        3,
        9,
        "③",
    ): {
        "rep": "인터넷 기사 댓글란에서 특정 연예인의 출산ㆍ대가수수 등 사생활에 관한 허위사실을 추가 댓글로 게시하면 정보통신망법상 명예훼손죄가 성립한다.",
        "why": "대화체와 인용문을 제거하고 명예훼손 성립 여부라는 최소 원리 문장으로 정리했습니다.",
    },
    (
        "public",
        4,
        9,
        "①",
    ): {
        "rep": "국무총리에 대한 탄핵소추 발의에는 국회재적의원 과반수의 발의가 필요하다.",
        "why": "국무총리에 대한 탄핵소추 발의정족수는 국회재적의원 3분의 1 이상이므로, 과반수 발의가 필요하다는 문장은 틀립니다.",
    },
    (
        "public",
        4,
        9,
        "②",
    ): {
        "rep": "탄핵소추의 의결을 받은 자는 탄핵심판이 있을 때까지 권한행사가 정지된다.",
        "why": "헌법상 탄핵소추 의결의 효과를 대화체 없이 정리했습니다.",
    },
    (
        "public",
        4,
        9,
        "③",
    ): {
        "rep": "국회는 탄핵대상자가 직무상 헌법이나 법률을 위반한 경우 탄핵소추를 의결할 헌법상 작위의무를 부담한다.",
        "why": "탄핵소추권은 국회의 권한이지 개별 사안에서 곧바로 헌법상 작위의무가 되는 것은 아닙니다.",
    },
    (
        "public",
        4,
        9,
        "④",
    ): {
        "rep": "대통령의 정치적 무능력이나 정책결정상 잘못 등 직책을 성실히 수행하지 않은 사정은 그 자체로 탄핵사유가 된다.",
        "why": "대통령의 성실한 직책수행의무 위반은 그 자체만으로 탄핵사유가 되지 않습니다.",
    },
    (
        "public",
        4,
        9,
        "⑤",
    ): {
        "rep": "탄핵결정은 피청구인의 민사상ㆍ형사상 책임을 면제한다.",
        "why": "탄핵결정은 공직 파면의 효과를 가질 뿐, 민사상ㆍ형사상 책임을 면제하지 않습니다.",
    },
}


def source_key(layer: str, item: dict[str, Any]) -> tuple[str, int, int, str]:
    return (
        layer,
        int(item.get("round") or 0),
        int(item.get("question_no") or 0),
        clean_text(item.get("choice")),
    )


def reject_source_item(text: str) -> bool:
    if len(text) > 230:
        return True
    if "<보기" in text or " | |" in text or "교수 :" in text:
        return True
    if any(marker in text for marker in ("?", "？", "할 수 있는가", "되는가")):
        return True
    if starts_with_orphan_label(text):
        return True
    if sentence_count(text) >= 2:
        return True
    return False


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def sentence_count(text: str) -> int:
    return len(re.findall(r"(?:다|이다|한다|된다|없다|있다)\.", text))


def has_case_label(text: str) -> bool:
    if any(char in text for char in "甲乙丙丁戊己庚辛"):
        return True
    case_targets = "토지|건물|회사|은행|채권|채무|주식|부동산|원고|피고|매수인|매도인"
    return bool(re.search(rf"(?<![가-힣])(?:갑|을|병|정)\s*(?:{case_targets})", text))


def starts_with_orphan_label(text: str) -> bool:
    return text.strip().startswith(("①", "②", "③", "④", "⑤"))


def reject_clat_atom_text(text: str) -> bool:
    if len(text) > 230:
        return True
    if any(marker in text for marker in ("?", "？", "교수 :", "학생 :", "할 수 있는가", "되는가")):
        return True
    if "<보기" in text or " | |" in text:
        return True
    if has_case_label(text) or starts_with_orphan_label(text):
        return True
    if sentence_count(text) >= 2:
        return True
    return False


def parse_article(value: Any) -> tuple[str, int | None]:
    text = clean_text(value)
    match = re.search(r"제\s*(\d+)\s*조(?:의\s*(\d+))?", text)
    if not match:
        return "", None
    label = f"제{match.group(1)}조" + (f"의{match.group(2)}" if match.group(2) else "")
    return label, int(match.group(1))


def grade_for_source(item: dict[str, Any]) -> str:
    round_no = int(item.get("round") or 0)
    source_kind = str(item.get("source_kind") or "")
    if round_no >= 14:
        grade = "A"
    elif round_no >= 12:
        grade = "B+"
    elif round_no >= 9:
        grade = "B"
    elif round_no >= 5:
        grade = "C+"
    else:
        grade = "C"
    if source_kind == "explicit_ox_combination" and grade in {"C", "C+"}:
        return "B"
    return grade


def weight_for_grade(grade: str) -> float:
    return {
        "S": 0.95,
        "A+": 0.82,
        "A": 0.68,
        "B+": 0.52,
        "B": 0.4,
        "C+": 0.28,
        "C": 0.22,
        "D+": 0.16,
        "D": 0.12,
    }.get(grade, 0.3)


def years_from_source(item: dict[str, Any]) -> list[str]:
    round_no = int(item.get("round") or 0)
    return [f"변시{round_no}"] if round_no else []


def normalize_existing_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        rep = clean_text(item.get("rep"))
        if not rep or reject_clat_atom_text(rep):
            continue
        copied = dict(item)
        copied["rep"] = rep
        copied["a"] = "X" if item.get("a") == "X" else "O"
        copied["sourceLayer"] = copied.get("sourceLayer") or "curated_atom"
        copied["twins"] = [
            twin
            for twin in (copied.get("twins") or [])
            if clean_text(twin.get("q")) and not reject_clat_atom_text(clean_text(twin.get("q")))
        ]
        out.append(copied)
    return out


def transform_source_items(items: list[dict[str, Any]], layer: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        override = MANUAL_SOURCE_OVERRIDES.get(source_key(layer, item))
        question = clean_text(item.get("q"))
        if override:
            question = clean_text(override.get("rep"))
        if item.get("needs_atomization") and not override:
            continue
        if reject_source_item(question) and not override:
            continue
        answer = item.get("a")
        if not question or answer not in {"O", "X"}:
            continue
        art, art_no = parse_article(item.get("art") or item.get("ref"))
        grade = grade_for_source(item)
        src = [clean_text(x) for x in (item.get("src") or item.get("refs") or []) if clean_text(x)]
        layer_prefix = "형사법" if layer == "criminal" else "공법"
        round_no = int(item.get("round") or 0)
        question_no = int(item.get("question_no") or 0)
        choice = clean_text(item.get("choice"))
        out.append(
            {
                "art": art,
                "artNo": art_no,
                "pid": f"{layer}-{round_no:02d}-{question_no:03d}-{choice}",
                "topic": clean_text(item.get("topic")) or layer_prefix,
                "rep": question,
                "a": answer,
                "why": clean_text(override.get("why") if override else item.get("why"))
                or f"{layer_prefix} 원문 지문층에서 추출한 {answer} 지문입니다.",
                "ref": clean_text(item.get("ref")),
                "src": src,
                "years": years_from_source(item),
                "freq": 1,
                "hot": False,
                "twins": [],
                "ids": [item.get("id")] if item.get("id") is not None else [],
                "xref": [],
                "subject": clean_text(item.get("subject")) or layer_prefix,
                "weight": weight_for_grade(grade),
                "grade": grade,
                "sourceLayer": f"{layer}_source_statement",
                "sourceKind": item.get("source_kind"),
                "statementKind": item.get("statement_kind"),
                "originalQuestion": item.get("original_question"),
                "originalAnswer": item.get("original_answer"),
                "answerChoice": item.get("answer_choice"),
            }
        )
    return out


def dedupe(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    skipped = 0
    for item in items:
        key = (
            clean_text(item.get("subject")),
            "X" if item.get("a") == "X" else "O",
            re.sub(r"\s+", "", clean_text(item.get("rep"))),
        )
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        out.append(item)
    return out, skipped


def render_audit(payload: dict[str, Any], skipped_duplicates: int) -> str:
    items = payload["items"]
    subject_counts = Counter(item.get("subject") for item in items)
    answer_counts = Counter(item.get("a") for item in items)
    layer_counts = Counter(item.get("sourceLayer") for item in items)
    lines = [
        "# CLAT OX 통합 문제은행 검증",
        "",
        "- 작성일: 2026-06-18",
        f"- 총 문항: {len(items)}개",
        f"- 중복 제거: {skipped_duplicates}개",
        f"- O/X: O {answer_counts.get('O', 0)}개 / X {answer_counts.get('X', 0)}개",
        "",
        "## 과목별",
        "",
    ]
    for subject, count in subject_counts.most_common():
        lines.append(f"- {subject}: {count}개")
    lines.extend(["", "## 출처층", ""])
    for layer, count in layer_counts.most_common():
        lines.append(f"- {layer}: {count}개")
    lines.extend(["", "## 비고", "", "- 민사법은 기존 최소 atom 통합본을 사용했습니다.", "- 형사법·공법은 이번 원문 지문층을 CLAT 전용으로 연결했습니다.", ""])
    return "\n".join(lines)


def main() -> None:
    civil = normalize_existing_items(load_json(CIVIL_BANK).get("items") or [])
    criminal = transform_source_items(load_json(CRIMINAL_SOURCE).get("items") or [], "criminal")
    public = transform_source_items(load_json(PUBLIC_SOURCE).get("items") or [], "public")
    items, skipped = dedupe(civil + criminal + public)
    payload = {
        "title": "CLAT OX unified bank",
        "version": "2026-06-18.clat-all-v001",
        "source": {
            "civil": str(CIVIL_BANK.relative_to(ROOT)),
            "criminal": str(CRIMINAL_SOURCE.relative_to(ROOT)),
            "public": str(PUBLIC_SOURCE.relative_to(ROOT)),
        },
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "subjects": dict(Counter(item.get("subject") for item in items)),
        "answers": dict(Counter(item.get("a") for item in items)),
        "layers": dict(Counter(item.get("sourceLayer") for item in items)),
        "items": items,
    }
    OUT_BANK.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_AUDIT_JSON.write_text(
        json.dumps(
            {
                "count": payload["count"],
                "subjects": payload["subjects"],
                "answers": payload["answers"],
                "layers": payload["layers"],
                "skippedDuplicates": skipped,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    OUT_AUDIT_MD.write_text(render_audit(payload, skipped), encoding="utf-8")
    print(f"clat bank built: items={payload['count']} skipped_duplicates={skipped}")


if __name__ == "__main__":
    main()
