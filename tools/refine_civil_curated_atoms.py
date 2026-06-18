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
INPUT = ASSETS / "ox_msa_unified_v001.json"
OUTPUT = ASSETS / "ox_msa_unified_refined_v001.json"
AUDIT_JSON = REPORTS / "civil_curated_atom_refine_audit.json"
AUDIT_MD = REPORTS / "civil_curated_atom_refine_audit.md"

SPLIT_LIMIT = 95
HARD_LIMIT = 130


def clean_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
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
        (r"칠 수$", "칠 수 있다"),
        (r"의무가$", "의무가 있다"),
        (r"할 뿐이고$", "한다"),
        (r"할 뿐이며$", "한다"),
        (r"될 뿐이고$", "된다"),
        (r"될 뿐이며$", "된다"),
        (r"수 있고$", "수 있다"),
        (r"수 있으며$", "수 있다"),
        (r"수 있으나$", "수 있다"),
        (r"수 없고$", "수 없다"),
        (r"수 없으며$", "수 없다"),
        (r"수 없으나$", "수 없다"),
        (r"있으나$", "있다"),
        (r"없으나$", "없다"),
        (r"않으나$", "않는다"),
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
        (r"가 아니고$", "가 아니다"),
        (r"이 아니고$", "이 아니다"),
        (r"아니고$", "아니다"),
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


def normalize_right_clause(text: str, original: str) -> str:
    text = clean_text(text).strip(" ,;")
    text = re.sub(r"^그 사람은\b", "제한능력자는", text)
    text = re.sub(r"^그 사람이\b", "제한능력자가", text)
    text = re.sub(r"^그 권리는\b", "해당 권리는", text)
    text = re.sub(r"^그 계약은\b", "해당 계약은", text)
    text = re.sub(r"^그 조항은\b", "해당 조항은", text)
    text = re.sub(r"^그 처분행위는\b", "해당 처분행위는", text)
    text = re.sub(r"^그 등기는\b", "해당 등기는", text)
    text = re.sub(r"^그 채권은\b", "해당 채권은", text)
    text = re.sub(r"^그 채무는\b", "해당 채무는", text)
    return ensure_period(text)


def valid_atom(text: str) -> bool:
    text = clean_text(text)
    if len(text) < 22:
        return False
    if len(text) > 145:
        return False
    if "?" in text or "？" in text:
        return False
    if text.startswith(("그리고", "또한", "나아가", "이로써", "이를", "이는", "그 ", "위 ")):
        return False
    if text.count("(") != text.count(")"):
        return False
    return text.endswith((".", "다"))


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
            second = normalize_right_clause(second_prefix + right, text)
            if not (valid_atom(first) and valid_atom(second)):
                continue
            if first.endswith(("경우.", "때.", "상태.", "상황.")):
                continue
            candidate = [first, second]
            score = max(len(first), len(second))
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
    parts = split_recursively(original)
    parts = [part for part in parts if valid_atom(part)]
    if not parts:
        parts = [ensure_period(original)]

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
        copied["ids"] = list(copied.get("ids") or [])
        copied["refinedFrom"] = item.get("pid")
        copied["refinedPart"] = index
        copied["quality"] = {
            **(copied.get("quality") or {}),
            "length": len(part),
            "splitFromComplexAtom": True,
            "originalLength": len(original),
        }
        refined.append(copied)
    return refined, {
        "pid": item.get("pid"),
        "action": "split",
        "fromLength": len(original),
        "toLengths": [len(part) for part in parts],
        "original": original,
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
            str(item.get("a") or "O"),
            re.sub(r"\s+", "", str(item.get("rep") or "")),
        )
        if key in seen:
            skipped_duplicates += 1
            continue
        seen.add(key)
        deduped.append(item)

    subject_counts = Counter(item.get("subject") or "" for item in deduped)
    answer_counts = Counter(item.get("a") or "" for item in deduped)
    split_events = [event for event in events if event["action"] == "split"]
    long_after = [item for item in deduped if len(str(item.get("rep") or "")) > SPLIT_LIMIT]
    hard_after = [item for item in deduped if len(str(item.get("rep") or "")) > HARD_LIMIT]

    output = {
        **{key: value for key, value in payload.items() if key != "items"},
        "title": "민사법 CLAT OX 대표 atom 정제본",
        "version": "2026-06-18.civil-refined-v001",
        "source": f"assets/{INPUT.name}",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "inputCount": len(source_items),
        "count": len(deduped),
        "splitCount": len(split_events),
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
        "skippedDuplicates": skipped_duplicates,
        "longBefore": sum(1 for item in source_items if len(str(item.get("rep") or "")) > SPLIT_LIMIT),
        "longAfter": len(long_after),
        "hardLongBefore": sum(1 for item in source_items if len(str(item.get("rep") or "")) > HARD_LIMIT),
        "hardLongAfter": len(hard_after),
        "subjectCounts": dict(subject_counts),
        "answerCounts": dict(answer_counts),
        "splitSamples": split_events[:80],
        "manualLongSamples": [
            {
                "pid": item.get("pid"),
                "subject": item.get("subject"),
                "length": len(str(item.get("rep") or "")),
                "rep": item.get("rep"),
            }
            for item in hard_after[:120]
        ],
    }
    return output, audit


def render_md(audit: dict[str, Any]) -> str:
    lines = [
        "# 민사법 CLAT atom 정제 점검",
        "",
        f"- 입력 atom: {audit['inputCount']:,}개",
        f"- 출력 atom: {audit['outputCount']:,}개",
        f"- 분할한 atom: {audit['splitCount']:,}개",
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

    lines.extend(["", "## 분할 예시", ""])
    if not audit["splitSamples"]:
        lines.append("- 자동 분할된 atom이 없습니다.")
    for sample in audit["splitSamples"][:25]:
        lines.append(f"### {sample['pid']} ({sample['fromLength']}자)")
        lines.append(f"- 원문: {sample['original']}")
        for idx, part in enumerate(sample["parts"], start=1):
            lines.append(f"- atom {idx}: {part}")
        lines.append("")

    lines.extend(["", "## 추가 수동 검토 후보", ""])
    if not audit["manualLongSamples"]:
        lines.append("- 130자를 넘는 대표 atom이 없습니다.")
    for sample in audit["manualLongSamples"][:40]:
        lines.append(f"- {sample['pid']} / {sample['subject']} / {sample['length']}자: {sample['rep']}")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    output, audit = build()
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    AUDIT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    AUDIT_MD.write_text(render_md(audit), encoding="utf-8")
    print(
        "civil refined: input={input} output={output} split={split} long95={before}->{after} hard130={hard_before}->{hard_after}".format(
            input=audit["inputCount"],
            output=audit["outputCount"],
            split=audit["splitCount"],
            before=audit["longBefore"],
            after=audit["longAfter"],
            hard_before=audit["hardLongBefore"],
            hard_after=audit["hardLongAfter"],
        )
    )


if __name__ == "__main__":
    main()
