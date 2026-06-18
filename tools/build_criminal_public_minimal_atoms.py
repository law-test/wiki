from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
REPORTS = ROOT / "reports"
ROUNDS = range(1, 16)
KINDS = {
    "criminal": {
        "label": "형사법",
        "source": "ox_criminal_bar{round}_source.json",
        "out": "ox_criminal_bar{round}_minimal_atoms_draft.json",
        "all": "ox_criminal_bar_all_minimal_atoms_draft.json",
    },
    "public": {
        "label": "공법",
        "source": "ox_public_bar{round}_source.json",
        "out": "ox_public_bar{round}_minimal_atoms_draft.json",
        "all": "ox_public_bar_all_minimal_atoms_draft.json",
    },
}

ARTICLE_RE = re.compile(r"제\s*(\d+)\s*조(?:의\s*(\d+))?")
CASE_LABEL_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸]")
HANGUL_CASE_LABEL_RE = re.compile(
    r"(?<![가-힣A-Za-z])(?:갑|을|병|정)\s*(?:토지|건물|회사|은행|채권|채무|주식|부동산|원고|피고|매수인|매도인)"
)
LATIN_CASE_RE = re.compile(r"(?<![A-Za-z])([A-Z])(?=(?:회사|은행|조합|단체|기관|위원회|학교|병원|토지|건물|주식|채권|채무|소유|운영|에게|와|과|의|은|는|이|가|을|를|에|에서|로|으로|부터|까지|,|\.|\s|$))")

MANUAL_REPAIRS: dict[tuple[str, int, int, str], dict[str, str]] = {
    ("criminal", 3, 9, "③"): {
        "rep": "인터넷 기사 댓글란에서 특정 연예인의 출산ㆍ대가수수 등 사생활에 관한 허위사실을 추가 댓글로 게시하면 정보통신망법상 명예훼손죄가 성립한다.",
        "why": "대화체와 인용문을 제거하고 명예훼손죄 성립 여부라는 최소 원리로 정리했습니다.",
    },
    ("public", 4, 9, "①"): {
        "rep": "국무총리에 대한 탄핵소추 발의에는 국회재적의원 과반수의 발의가 필요하다.",
        "why": "국무총리에 대한 탄핵소추 발의정족수는 국회재적의원 3분의 1 이상이므로, 과반수 발의가 필요하다는 문장은 틀립니다.",
    },
    ("public", 4, 9, "②"): {
        "rep": "탄핵소추의 의결을 받은 자는 탄핵심판이 있을 때까지 권한행사가 정지된다.",
        "why": "탄핵소추 의결의 효과를 대화체 없이 정리했습니다.",
    },
    ("public", 4, 9, "③"): {
        "rep": "국회는 탄핵대상자가 직무상 헌법이나 법률을 위반한 경우 탄핵소추를 의결할 헌법상 작위의무를 부담한다.",
        "why": "탄핵소추권은 국회의 권한이지 개별 사안에서 곧바로 헌법상 작위의무가 되는 것은 아닙니다.",
    },
    ("public", 4, 9, "④"): {
        "rep": "대통령의 정치적 무능력이나 정책결정상 잘못 등 직책을 성실히 수행하지 않은 사정은 그 자체로 탄핵사유가 된다.",
        "why": "대통령의 성실한 직책수행의무 위반은 그 자체만으로 탄핵사유가 되지 않습니다.",
    },
    ("public", 4, 9, "⑤"): {
        "rep": "탄핵결정은 피청구인의 민사상ㆍ형사상 책임을 면제한다.",
        "why": "탄핵결정은 공직 파면의 효과를 가질 뿐, 민사상ㆍ형사상 책임을 면제하지 않습니다.",
    },
}


def compact(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    text = text.replace(" | |", " ").replace("| |", " ")
    text = re.sub(r"\+={5,}\+", " ", text)
    text = re.sub(r"-{5,}", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("합 의", "합의").replace("주 식", "주식")
    text = text.replace("｢", "").replace("｣", "")
    return text


def parse_art(value: Any) -> tuple[str, int | None]:
    text = compact(value)
    match = ARTICLE_RE.search(text)
    if not match:
        return "", None
    return f"제{match.group(1)}조" + (f"의{match.group(2)}" if match.group(2) else ""), int(match.group(1))


def source_key(kind: str, item: dict[str, Any]) -> tuple[str, int, int, str]:
    return (
        kind,
        int(item.get("round") or 0),
        int(item.get("question_no") or 0),
        compact(item.get("choice")),
    )


def grade_for(item: dict[str, Any]) -> str:
    round_no = int(item.get("round") or 0)
    if round_no >= 14:
        return "A"
    if round_no >= 12:
        return "B+"
    if round_no >= 9:
        return "B"
    if round_no >= 5:
        return "C+"
    return "C"


def weight_for(grade: str) -> float:
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


def sentence_count(text: str) -> int:
    return len(re.findall(r"(?:다|이다|한다|된다|없다|있다)\.", text))


def rewrite_dialogue(text: str) -> str:
    if "학생 :" not in text:
        return text
    answer = compact(text.split("학생 :", 1)[1])
    answer = re.sub(r"^(네|예)\.\s*", "", answer)
    answer = re.sub(r"^아닙니다\.\s*", "", answer)
    return answer


def rewrite_case_labels(text: str) -> str:
    replacements = {
        "甲": "행위자",
        "乙": "상대방",
        "丙": "제3자",
        "丁": "다른 제3자",
        "戊": "추가 제3자",
        "己": "관련자",
        "庚": "관련자",
        "辛": "관련자",
        "壬": "관련자",
        "癸": "관련자",
    }
    for key, value in replacements.items():
        text = text.replace(key, value)
    text = re.sub(r"(?<![가-힣])갑(?=\s*(?:토지|건물|회사|은행|채권|채무|주식|부동산|원고|피고|매수인|매도인))", "대상", text)
    text = re.sub(r"(?<![가-힣])을(?=\s*(?:토지|건물|회사|은행|채권|채무|주식|부동산|원고|피고|매수인|매도인))", "표시상", text)
    text = re.sub(r"(?<![가-힣])병(?=\s*(?:토지|건물|회사|은행|채권|채무|주식|부동산|원고|피고|매수인|매도인))", "제3", text)
    text = re.sub(r"(?<![가-힣])정(?=\s*(?:토지|건물|회사|은행|채권|채무|주식|부동산|원고|피고|매수인|매도인))", "다른", text)

    latin_map = {
        "A": "사례",
        "B": "상대",
        "C": "제3",
        "D": "다른",
        "E": "추가",
        "P": "사례",
        "Q": "상대",
        "R": "제3",
    }

    def latin_repl(match: re.Match[str]) -> str:
        return latin_map.get(match.group(1), "사례")

    return LATIN_CASE_RE.sub(latin_repl, text)


def fix_korean_particles(text: str) -> str:
    repairs = {
        "행위자이": "행위자가",
        "행위자을": "행위자를",
        "행위자은": "행위자는",
        "행위자의": "행위자의",
        "상대방이": "상대방이",
        "상대방을": "상대방을",
        "상대방로부터": "상대방으로부터",
        "제3자이": "제3자가",
        "제3자을": "제3자를",
        "제3자은": "제3자는",
        "사례이": "사례가",
        "사례을": "사례를",
        "사례은": "사례는",
    }
    for old, new in repairs.items():
        text = text.replace(old, new)
    return text


def rewrite_question_phrases(text: str) -> str:
    text = text.replace("할 수 있는가의 문제는", "할 수 있는지를 판단할 때에는")
    text = text.replace("할 수 있는가를 시도하고", "할 수 있는지를 검토하고")
    text = text.replace("되는가의 문제는", "되는지를 판단할 때에는")
    text = text.replace("인가의 문제는", "인지를 판단할 때에는")
    text = text.replace("인가?", "이다.")
    text = text.replace("되는가?", "된다.")
    text = text.replace("할 수 있는가?", "할 수 있다.")
    return text


def minimalize_text(item: dict[str, Any], kind: str) -> tuple[str, str]:
    repair = MANUAL_REPAIRS.get(source_key(kind, item))
    if repair:
        return compact(repair["rep"]), compact(repair["why"])

    text = compact(item.get("q"))
    text = re.sub(r"^[①②③④⑤]\s*", "", text)
    text = re.sub(r"^[ㄱㄴㄷㄹㅁㅂㅅ가나다라마바사]\.\s*", "", text)
    text = rewrite_dialogue(text)
    text = rewrite_case_labels(text)
    text = rewrite_question_phrases(text)
    text = fix_korean_particles(text)
    text = compact(text)

    why = compact(item.get("why"))
    if why:
        why = why.replace("지문은 정답표상", "지문에서 확인한")
    else:
        why = f"제{item.get('round')}회 변호사시험 {item.get('subject_group')} 선택형 {item.get('question_no')}번 {item.get('choice')} 지문을 최소 atom으로 정리했습니다."
    return text, why


def quality_flags(text: str) -> list[str]:
    flags: list[str] = []
    if not text:
        flags.append("empty")
    if len(text) > 230:
        flags.append("long")
    if any(mark in text for mark in ("???", "??", "�", "| |", "<보기")):
        flags.append("artifact")
    if any(mark in text for mark in ("?", "？", "교수 :", "학생 :")):
        flags.append("question_or_dialogue")
    if CASE_LABEL_RE.search(text) or HANGUL_CASE_LABEL_RE.search(text):
        flags.append("case_label")
    if text.strip().startswith(("①", "②", "③", "④", "⑤")):
        flags.append("orphan_label")
    if sentence_count(text) >= 2:
        flags.append("multi_sentence")
    return flags


def build_one(kind: str, round_no: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    spec = KINDS[kind]
    source_path = ASSETS / spec["source"].format(round=round_no)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source_items = list(source.get("items") or [])
    atoms: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for source_item in source_items:
        rep, why = minimalize_text(source_item, kind)
        flags = quality_flags(rep)
        if (
            "empty" in flags
            or "long" in flags
            or "multi_sentence" in flags
            or "artifact" in flags
            or "question_or_dialogue" in flags
            or "case_label" in flags
            or "orphan_label" in flags
        ):
            rejected.append(
                {
                    "id": source_item.get("id"),
                    "question_no": source_item.get("question_no"),
                    "choice": source_item.get("choice"),
                    "subject": source_item.get("subject"),
                    "flags": flags,
                    "text": rep,
                    "source_statement": source_item.get("q"),
                }
            )
            continue
        grade = grade_for(source_item)
        art, art_no = parse_art(source_item.get("art") or source_item.get("ref"))
        round_label = f"변시{round_no} {source_item.get('question_no')}번 {source_item.get('choice')}"
        atoms.append(
            {
                "pid": f"{kind}-bar{round_no:02d}-q{int(source_item.get('question_no') or 0):02d}-{compact(source_item.get('choice'))}",
                "round": round_no,
                "year": source_item.get("year"),
                "subject_group": spec["label"],
                "subject": source_item.get("subject"),
                "topic": compact(source_item.get("topic")) or spec["label"],
                "rep": rep,
                "a": "X" if source_item.get("a") == "X" else "O",
                "why": why,
                "ref": compact(source_item.get("ref")),
                "art": art or compact(source_item.get("art")),
                "artNo": art_no,
                "src": [round_label],
                "refs": [round_label],
                "years": [f"변시{round_no}"],
                "freq": 1,
                "hot": False,
                "twins": [],
                "grade": grade,
                "weight": weight_for(grade),
                "source_answer": "X" if source_item.get("a") == "X" else "O",
                "source_statement": source_item.get("q"),
                "source_basis": source_item.get("why"),
                "source_kind": source_item.get("source_kind"),
                "statement_kind": source_item.get("statement_kind"),
                "source_layer_needs_atomization": bool(source_item.get("needs_atomization")),
                "quality_flags": flags,
                "type": f"{kind}_bar_minimal_atom_draft",
            }
        )

    audit = {
        "kind": kind,
        "round": round_no,
        "sourceCount": len(source_items),
        "atomCount": len(atoms),
        "rejectedCount": len(rejected),
        "subjects": dict(Counter(item.get("subject") for item in atoms)),
        "answers": dict(Counter(item.get("a") for item in atoms)),
        "qualityFlags": dict(Counter(flag for item in atoms for flag in item.get("quality_flags", []))),
        "rejected": rejected,
    }
    out_path = ASSETS / spec["out"].format(round=round_no)
    out_payload = {
        "title": f"변호사시험 {spec['label']} {round_no}회 최소 atom 정제본",
        "version": f"{kind}_bar{round_no}_minimal_v001",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(atoms),
        "sourceCount": len(source_items),
        "rejectedCount": len(rejected),
        "items": atoms,
    }
    out_path.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_audit(kind, round_no, audit)
    return atoms, audit


def write_audit(kind: str, round_no: int, audit: dict[str, Any]) -> None:
    spec = KINDS[kind]
    prefix = f"{kind}_bar{round_no}_minimal_atom_audit"
    (REPORTS / f"{prefix}.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        f"# 변호사시험 {spec['label']} {round_no}회 최소 atom 정제 점검",
        "",
        f"- 원천 지문: {audit['sourceCount']}개",
        f"- 최소 atom: {audit['atomCount']}개",
        f"- 제외: {audit['rejectedCount']}개",
        "",
        "## 과목별",
        "",
    ]
    for subject, count in Counter(audit["subjects"]).most_common():
        lines.append(f"- {subject}: {count}개")
    if audit["rejected"]:
        lines.extend(["", "## 제외 샘플", ""])
        for item in audit["rejected"][:20]:
            lines.append(
                f"- {item['subject']} {item['question_no']}번 {item['choice']} / {', '.join(item['flags'])}: {item['text'][:180]}"
            )
    lines.append("")
    (REPORTS / f"{prefix}.md").write_text("\n".join(lines), encoding="utf-8")


def write_all(kind: str, all_atoms: list[dict[str, Any]], round_audits: list[dict[str, Any]]) -> None:
    spec = KINDS[kind]
    payload = {
        "title": f"변호사시험 {spec['label']} 1~15회 최소 atom 통합 정제본",
        "version": f"{kind}_bar_all_minimal_v001",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(all_atoms),
        "rounds": {str(audit["round"]): audit["atomCount"] for audit in round_audits},
        "sourceCount": sum(audit["sourceCount"] for audit in round_audits),
        "rejectedCount": sum(audit["rejectedCount"] for audit in round_audits),
        "subjects": dict(Counter(item.get("subject") for item in all_atoms)),
        "answers": dict(Counter(item.get("a") for item in all_atoms)),
        "items": all_atoms,
    }
    (ASSETS / spec["all"]).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    prefix = f"{kind}_bar_all_minimal_atom_audit"
    (REPORTS / f"{prefix}.json").write_text(json.dumps(payload | {"items": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        f"# 변호사시험 {spec['label']} 1~15회 최소 atom 통합 점검",
        "",
        f"- 원천 지문: {payload['sourceCount']}개",
        f"- 최소 atom: {payload['count']}개",
        f"- 제외: {payload['rejectedCount']}개",
        "",
        "## 회차별",
        "",
    ]
    for round_no in ROUNDS:
        lines.append(f"- {round_no}회: {payload['rounds'].get(str(round_no), 0)}개")
    lines.extend(["", "## 과목별", ""])
    for subject, count in Counter(payload["subjects"]).most_common():
        lines.append(f"- {subject}: {count}개")
    lines.append("")
    (REPORTS / f"{prefix}.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    for kind in KINDS:
        all_atoms: list[dict[str, Any]] = []
        audits: list[dict[str, Any]] = []
        for round_no in ROUNDS:
            atoms, audit = build_one(kind, round_no)
            all_atoms.extend(atoms)
            audits.append(audit)
        write_all(kind, all_atoms, audits)
        print(
            f"{kind}: atoms={len(all_atoms)} rejected={sum(a['rejectedCount'] for a in audits)} "
            f"source={sum(a['sourceCount'] for a in audits)}"
        )


if __name__ == "__main__":
    main()
