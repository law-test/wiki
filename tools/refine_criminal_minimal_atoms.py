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
INPUT = ASSETS / "ox_criminal_bar_all_minimal_atoms_draft.json"
OUTPUT = ASSETS / "ox_criminal_bar_all_minimal_atoms_refined_v001.json"
AUDIT_JSON = REPORTS / "criminal_minimal_atom_refine_audit.json"
AUDIT_MD = REPORTS / "criminal_minimal_atom_refine_audit.md"

SPLIT_LIMIT = 95
HARD_LIMIT = 130
FINAL_ENDING = "다."


def clean_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    replacements = {
        "행위자과": "행위자와",
        "상대방과 제3자과": "상대방과 제3자와",
        "상대방, 제3자과": "상대방, 제3자와",
        "제3자과": "제3자와",
        "제3자가라고": "제3자라고",
        "정당한 이유없이": "정당한 이유 없이",
        "기소되지 아니한 제3의 공범 제3자": "기소되지 않은 제3의 공범",
        "피고인 행위자": "피고인",
        "피의자 행위자": "피의자",
        "행위자, 상대방": "피고인들",
        "위 사례와 같은": "같은",
        "사례회사": "피해 회사",
        "사례의": "피해자의",
        "사례에게": "피해자에게",
        "사례를": "피해자를",
        "사례가": "피해자가",
        "사례는": "피해자는",
        "사례와": "피해자와",
        "사례로부터": "피해자로부터",
    }
    for before, after in replacements.items():
        text = text.replace(before, after)
    text = text.replace(" · ", "·")
    text = re.sub(r"\s+([,.)])", r"\1", text)
    text = re.sub(r"([(])\s+", r"\1", text)
    return text


def ensure_period(text: str) -> str:
    text = clean_text(text).strip(" ,;")
    if not text:
        return ""
    if text.endswith(("다.", "요.", "임.", "음.", ".")):
        return text
    if text.endswith("다"):
        return text + "."
    return text + "."


def finish_left_clause(text: str) -> str:
    text = clean_text(text).strip(" ,;")
    replacements = [
        (r"할 수$", "할 수 있다"),
        (r"될 수$", "될 수 있다"),
        (r"볼 수$", "볼 수 있다"),
        (r"의무가$", "의무가 있다"),
        (r"수 있고$", "수 있다"),
        (r"수 있으며$", "수 있다"),
        (r"수 있으나$", "수 있다"),
        (r"수 없고$", "수 없다"),
        (r"수 없으며$", "수 없다"),
        (r"수 없으나$", "수 없다"),
        (r"있으나$", "있다"),
        (r"없으나$", "없다"),
        (r"않으나$", "않는다"),
        (r"지 아니하고$", "지 않는다"),
        (r"지 아니하며$", "지 않는다"),
        (r"지 않고$", "지 않는다"),
        (r"지는 않고$", "지 않는다"),
        (r"하지는 않고$", "하지 않는다"),
        (r"지 않으며$", "지 않는다"),
        (r"하므로$", "한다"),
        (r"되므로$", "된다"),
        (r"있으므로$", "있다"),
        (r"없으므로$", "없다"),
        (r"이므로$", "이다"),
        (r"하여야 하나$", "하여야 한다"),
        (r"해야 하나$", "해야 한다"),
        (r"되나$", "된다"),
        (r"지나$", "진다"),
        (r"하나$", "한다"),
        (r"아니고$", "아니다"),
        (r"아니하며$", "아니다"),
        (r"되며$", "된다"),
        (r"되고$", "된다"),
        (r"지며$", "진다"),
        (r"지고$", "진다"),
        (r"하며$", "한다"),
        (r"하고$", "한다"),
        (r"가지며$", "가진다"),
        (r"갖고$", "가진다"),
        (r"있으며$", "있다"),
        (r"있고$", "있다"),
        (r"없으며$", "없다"),
        (r"없고$", "없다"),
        (r"이며$", "이다"),
        (r"이고$", "이다"),
        (r"지만$", "다"),
        (r"할$", "한다"),
    ]
    for pattern, repl in replacements:
        if re.search(pattern, text):
            text = re.sub(pattern, repl, text)
            break
    return ensure_period(text)


def normalize_right_clause(text: str) -> str:
    text = clean_text(text).strip(" ,;")
    text = re.sub(r"^그 행위자는\b", "행위자는", text)
    text = re.sub(r"^그 범죄는\b", "해당 범죄는", text)
    text = re.sub(r"^그 증거는\b", "해당 증거는", text)
    text = re.sub(r"^그 진술은\b", "해당 진술은", text)
    text = re.sub(r"^그 경우\b", "그 경우", text)
    return ensure_period(text)


def valid_atom(text: str) -> bool:
    text = clean_text(text)
    if len(text) < 22:
        return False
    if len(text) > 145:
        return False
    if "?" in text or "？" in text:
        return False
    if text.startswith(("그리고", "또한", "나아가", "이로써", "이를", "이는", "그 ")):
        return False
    if text.count("(") != text.count(")"):
        return False
    return text.endswith(FINAL_ENDING)


def is_complete_atom(text: str) -> bool:
    return clean_text(text).endswith(FINAL_ENDING)


def split_parenthetical_tail(text: str) -> list[str] | None:
    match = re.search(r"^(?P<head>.+?)\s*\((?P<tail>다만\s*.+?다)\)\.?$", text)
    if not match:
        return None
    head = ensure_period(match.group("head"))
    tail = ensure_period(match.group("tail"))
    if valid_atom(head) and valid_atom(tail):
        return [head, tail]
    return None


def split_once(text: str) -> list[str] | None:
    text = clean_text(text)
    parenthetical = split_parenthetical_tail(text)
    if parenthetical:
        return parenthetical

    connector_patterns = [
        (r",\s*다만\s+", "", "다만 "),
        (r",\s*그러나\s+", "", "그러나 "),
        (r",\s*반면\s+", "", "반면 "),
        (r",\s*한편\s+", "", "한편 "),
        (r",\s*또한\s+", "", "또한 "),
        (r"\s+그리고\s+", "", ""),
        (r"\s+뿐이고,\s+", "뿐이고", ""),
        (r"\s+뿐이며,\s+", "뿐이며", ""),
        (r"\s+아니고,\s+", "아니고", ""),
        (r"\s+아니하며,\s+", "아니하며", ""),
        (r"\s+아니한\s+이상\s+", "아니한 이상", ""),
        (r"\s+않고,\s+", "않고", ""),
        (r"\s+없고,\s+", "없고", ""),
        (r"\s+있고,\s+", "있고", ""),
        (r"\s+하며,\s+", "하며", ""),
        (r"\s+하고,\s+", "하고", ""),
        (r"\s+이며,\s+", "이며", ""),
        (r"\s+이고,\s+", "이고", ""),
        (r"\s+하나,\s+", "하나", ""),
        (r"\s+되나,\s+", "되나", ""),
        (r"\s+으나,\s+", "으나", ""),
        (r"\s+으나\s+", "으나", ""),
        (r"\s+하므로,\s+", "하므로", ""),
        (r"\s+되므로,\s+", "되므로", ""),
        (r"\s+있으므로,\s+", "있으므로", ""),
        (r"\s+없으므로,\s+", "없으므로", ""),
        (r"\s+이므로,\s+", "이므로", ""),
        (r"\s+지만,\s+", "지만", ""),
    ]

    best: list[str] | None = None
    for pattern, left_suffix, second_prefix in connector_patterns:
        for match in re.finditer(pattern, text):
            left = text[: match.start()]
            right = text[match.end() :]
            if len(left) < 28 or len(right) < 24:
                continue
            first = finish_left_clause((left + " " + left_suffix).strip())
            second = normalize_right_clause(second_prefix + right)
            if not (valid_atom(first) and valid_atom(second)):
                continue
            if first.endswith(("경우.", "때.", "상태.", "상황.")):
                continue
            candidate = [first, second]
            score = max(len(part) for part in candidate)
            if best is None or score < max(len(part) for part in best):
                best = candidate
    return best


def split_recursively(text: str, depth: int = 0) -> list[str]:
    text = ensure_period(text)
    if depth >= 2 or len(text) <= SPLIT_LIMIT:
        return [text]
    parts = split_once(text)
    if not parts:
        return [text]
    out: list[str] = []
    for part in parts:
        out.extend(split_recursively(part, depth + 1))
    return out


def refine_item(item: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    original = clean_text(item.get("rep"))
    answer = "X" if item.get("a") == "X" else "O"
    normalized = ensure_period(original)

    if not is_complete_atom(normalized):
        return [], {
            "pid": item.get("pid"),
            "answer": answer,
            "action": "rejected_incomplete",
            "length": len(normalized),
            "rep": normalized,
        }

    if answer == "X":
        copied = dict(item)
        copied["rep"] = normalized
        copied["why"] = clean_text(copied.get("why")) or copied["rep"]
        copied["quality"] = {
            **(copied.get("quality") or {}),
            "length": len(copied["rep"]),
            "needsManualSplit": len(copied["rep"]) > HARD_LIMIT,
            "splitSkippedBecauseFalseAtom": len(copied["rep"]) > SPLIT_LIMIT,
        }
        return [copied], {
            "pid": item.get("pid"),
            "answer": answer,
            "action": "kept_false_atom",
            "length": len(copied["rep"]),
            "rep": copied["rep"],
        }

    parts = [part for part in split_recursively(normalized) if valid_atom(part)]
    if not parts:
        parts = [normalized]

    if len(parts) == 1:
        copied = dict(item)
        copied["rep"] = parts[0]
        copied["why"] = clean_text(copied.get("why")) or parts[0]
        copied["quality"] = {
            **(copied.get("quality") or {}),
            "length": len(parts[0]),
            "needsManualSplit": len(parts[0]) > HARD_LIMIT,
        }
        return [copied], {
            "pid": item.get("pid"),
            "answer": answer,
            "action": "kept",
            "length": len(parts[0]),
            "rep": parts[0],
        }

    refined: list[dict[str, Any]] = []
    for index, part in enumerate(parts, start=1):
        copied = dict(item)
        copied["pid"] = item.get("pid") if index == 1 else f"{item.get('pid')}-s{index}"
        copied["rep"] = part
        copied["why"] = part
        copied["twins"] = copied.get("twins") if index == 1 else []
        copied["refinedFrom"] = item.get("pid")
        copied["refinedPart"] = index
        copied["quality"] = {
            **(copied.get("quality") or {}),
            "length": len(part),
            "splitFromComplexAtom": True,
            "originalLength": len(normalized),
        }
        refined.append(copied)
    return refined, {
        "pid": item.get("pid"),
        "answer": answer,
        "action": "split",
        "fromLength": len(normalized),
        "toLengths": [len(part) for part in parts],
        "original": normalized,
        "parts": parts,
    }


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    source_items = payload.get("items") or []
    refined_items: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    for item in source_items:
        refined, event = refine_item(item)
        refined_items.extend(refined)
        events.append(event)

    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    skipped_duplicates = 0
    for item in refined_items:
        key = (
            str(item.get("subject") or ""),
            str(item.get("a") or ""),
            re.sub(r"\s+", "", str(item.get("rep") or "")),
        )
        if key in seen:
            skipped_duplicates += 1
            continue
        seen.add(key)
        deduped.append(item)

    split_events = [event for event in events if event["action"] == "split"]
    false_kept = [event for event in events if event["action"] == "kept_false_atom" and event["length"] > SPLIT_LIMIT]
    incomplete_rejected = [event for event in events if event["action"] == "rejected_incomplete"]
    long_after = [item for item in deduped if len(str(item.get("rep") or "")) > SPLIT_LIMIT]
    hard_after = [item for item in deduped if len(str(item.get("rep") or "")) > HARD_LIMIT]
    subject_counts = Counter(item.get("subject") or "" for item in deduped)
    answer_counts = Counter(item.get("a") or "" for item in deduped)

    output = {
        **{key: value for key, value in payload.items() if key != "items"},
        "title": "형사법 CLAT OX 최소 atom 정제본",
        "version": "2026-06-18.criminal-refined-v001",
        "source": f"assets/{INPUT.name}",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "inputCount": len(source_items),
        "count": len(deduped),
        "splitCount": len(split_events),
        "skippedFalseLongCount": len(false_kept),
        "rejectedIncompleteCount": len(incomplete_rejected),
        "skippedDuplicates": skipped_duplicates,
        "subjects": dict(subject_counts),
        "answers": dict(answer_counts),
        "items": deduped,
    }
    audit = {
        "updatedAt": output["updatedAt"],
        "inputCount": len(source_items),
        "outputCount": len(deduped),
        "splitCount": len(split_events),
        "skippedFalseLongCount": len(false_kept),
        "rejectedIncompleteCount": len(incomplete_rejected),
        "skippedDuplicates": skipped_duplicates,
        "longBefore": sum(1 for item in source_items if len(str(item.get("rep") or "")) > SPLIT_LIMIT),
        "longAfter": len(long_after),
        "hardLongBefore": sum(1 for item in source_items if len(str(item.get("rep") or "")) > HARD_LIMIT),
        "hardLongAfter": len(hard_after),
        "subjectCounts": dict(subject_counts),
        "answerCounts": dict(answer_counts),
        "splitSamples": split_events[:80],
        "falseLongSamples": false_kept[:80],
        "incompleteRejectedSamples": incomplete_rejected[:80],
        "manualLongSamples": [
            {
                "pid": item.get("pid"),
                "subject": item.get("subject"),
                "answer": item.get("a"),
                "length": len(str(item.get("rep") or "")),
                "rep": item.get("rep"),
            }
            for item in hard_after[:120]
        ],
    }
    return output, audit


def render_md(audit: dict[str, Any]) -> str:
    lines = [
        "# 형사법 CLAT atom 정제 점검",
        "",
        f"- 입력 atom: {audit['inputCount']:,}개",
        f"- 출력 atom: {audit['outputCount']:,}개",
        f"- 자동 분할한 O atom: {audit['splitCount']:,}개",
        f"- 긴 X atom 보류: {audit['skippedFalseLongCount']:,}개",
        f"- 불완전 조각 제외: {audit['rejectedIncompleteCount']:,}개",
        f"- 중복 제거: {audit['skippedDuplicates']:,}개",
        f"- 95자 초과: {audit['longBefore']:,}개 -> {audit['longAfter']:,}개",
        f"- 130자 초과: {audit['hardLongBefore']:,}개 -> {audit['hardLongAfter']:,}개",
        f"- 출력 파일: `assets/{OUTPUT.name}`",
        "",
        "## 과목별",
        "",
    ]
    for subject, count in sorted(audit["subjectCounts"].items()):
        lines.append(f"- {subject}: {count:,}개")
    lines.extend(["", "## O atom 분할 예시", ""])
    if not audit["splitSamples"]:
        lines.append("- 자동 분할된 atom이 없습니다.")
    for sample in audit["splitSamples"][:25]:
        lines.append(f"### {sample['pid']} ({sample['fromLength']}자)")
        lines.append(f"- 원문: {sample['original']}")
        for idx, part in enumerate(sample["parts"], start=1):
            lines.append(f"- atom {idx}: {part}")
        lines.append("")
    lines.extend(["", "## 긴 X atom 보류 예시", ""])
    if not audit["falseLongSamples"]:
        lines.append("- 보류한 긴 X atom이 없습니다.")
    for sample in audit["falseLongSamples"][:25]:
        lines.append(f"- {sample['pid']} / {sample['length']}자: {sample['rep']}")
    lines.extend(["", "## 불완전 조각 제외 예시", ""])
    if not audit["incompleteRejectedSamples"]:
        lines.append("- 제외한 불완전 조각이 없습니다.")
    for sample in audit["incompleteRejectedSamples"][:25]:
        lines.append(f"- {sample['pid']} / {sample['length']}자: {sample['rep']}")
    lines.extend(["", "## 추가 수동 검토 후보", ""])
    if not audit["manualLongSamples"]:
        lines.append("- 130자를 넘는 atom이 없습니다.")
    for sample in audit["manualLongSamples"][:40]:
        lines.append(
            f"- {sample['pid']} / {sample['subject']} / {sample['answer']} / {sample['length']}자: {sample['rep']}"
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    output, audit = build()
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    AUDIT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    AUDIT_MD.write_text(render_md(audit), encoding="utf-8")
    print(
        "criminal refined: input={input} output={output} split={split} false_long={false_long} incomplete={incomplete} long95={before}->{after} hard130={hard_before}->{hard_after}".format(
            input=audit["inputCount"],
            output=audit["outputCount"],
            split=audit["splitCount"],
            false_long=audit["skippedFalseLongCount"],
            incomplete=audit["rejectedIncompleteCount"],
            before=audit["longBefore"],
            after=audit["longAfter"],
            hard_before=audit["hardLongBefore"],
            hard_after=audit["hardLongAfter"],
        )
    )


if __name__ == "__main__":
    main()
