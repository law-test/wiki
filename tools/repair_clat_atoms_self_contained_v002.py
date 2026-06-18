from __future__ import annotations

import copy
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
REPORTS = ROOT / "reports"

SOURCE_FILES = {
    "civil": ASSETS / "ox_msa_unified_refined_v001.json",
    "criminal": ASSETS / "ox_criminal_bar_all_minimal_atoms_refined_v001.json",
    "public": ASSETS / "ox_public_bar_all_minimal_atoms_refined_v001.json",
}

RAW_FILES = {
    "civil": ASSETS / "ox_msa_unified_v001.json",
    "criminal": ASSETS / "ox_criminal_bar_all_source.json",
    "public": ASSETS / "ox_public_bar_all_source.json",
}

OUT_FILES = {
    "civil": ASSETS / "ox_msa_unified_selfcontained_v002.json",
    "criminal": ASSETS / "ox_criminal_bar_all_minimal_atoms_selfcontained_v002.json",
    "public": ASSETS / "ox_public_bar_all_minimal_atoms_selfcontained_v002.json",
}

REPORT_JSON = REPORTS / "clat_atoms_selfcontained_repair_v002.json"
REPORT_MD = REPORTS / "clat_atoms_selfcontained_repair_v002.md"


CONTEXT_PREFIXES = (
    "\ub2e4\ub9cc",
    "\uadf8\ub7ec\ub098",
    "\uadf8\ub7f0\ub370",
    "\uadf8\ub9ac\uace0",
    "\ub530\ub77c\uc11c",
    "\ud55c\ud3b8",
    "\ub098\uc544\uac00",
    "\ubc18\uba74",
    "\uc624\ud788\ub824",
    "\ub610\ud55c",
    "\uc774\ub54c",
    "\uc774 ",
    "\uc774 \uacbd\uc6b0",
    "\uadf8 \uacbd\uc6b0",
    "\uc774\uc640 \ubcc4\ub3c4\ub85c",
    "\uc774\uc640 \uac19\uc740",
    "\uc774\ub97c ",
    "\uc774\uc5d0 ",
    "\uadf8\uac83",
    "\uadf8\ub7ec\ud55c",
    "\uadf8 ",
    "\uadf8 \uc7ac\ud310",
    "\uadf8 \uac10\uc0ac",
    "\uadf8 \uc2ec\uc0ac",
    "\uadf8 \uc2e0\uccad",
    "\ud574\ub2f9 ",
    "\uc774\ub7ec\ud55c",
    "\uc6d0\uce59\uc801\uc73c\ub85c",
    "\ub9cc\uc57d",
    "\ub9cc\uc77c",
    "\uc0ac\uc548",
)

SCENARIO_PREFIXES = (
    "\uc704 ",
    "\uc704\uc640 \uac19\uc774",
    "\uc704\uc640 \uac19\uc740",
    "\uc704 \uc0ac\ub840",
    "\uc704 \uc0ac\uc548",
    "\uc704 \uc0ac\uac74",
    "\uc704 \ud310\uacb0",
    "\uc704 \uaddc\uc815",
    "\uc704 \uc870\ud56d",
    "\uc704 \uc81c",
)

TYPO_FIXES = (
    ("\ud53c\uace0\uc778\ub294", "\ud53c\uace0\uc778\uc740"),
    ("\ub2e4\ub978\uc758 \uc9c4\uc220", "\ud0c0\uc778\uc758 \uc9c4\uc220"),
)

CASE_LABEL_RE = re.compile(r"[\u7532\u4e59\u4e19\u4e01]|\u321c|(?<![A-Za-z0-9])[A-D](?![A-Za-z0-9])")
SCENARIO_INTERNAL_RE = re.compile(
    r"[\u3260-\u327f]|\uc0ac\ub840|\uc704 \uc0ac\ub840|\uc704 \uc0ac\uc548|\uc704 \uc0ac\uac74|"
    r"\uc774 \uc0ac\uac74|\uc774 \uc0ac\ub840|\uc774 \uc0ac\uc548|\uadf8 \uc0ac\uac74|\uc0c1\ub300\ubc29\uc2dc"
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def item_id(item: dict[str, Any]) -> str:
    return str(item.get("pid") or item.get("id") or "")


def base_pid(item: dict[str, Any]) -> str:
    explicit = item.get("refinedFrom")
    if explicit:
        return str(explicit)
    return re.sub(r"-s\d+$", "", item_id(item))


def starts_with_any(text: str, prefixes: tuple[str, ...]) -> bool:
    stripped = text.strip()
    return any(stripped.startswith(prefix) for prefix in prefixes)


def is_context_start(text: str) -> bool:
    return starts_with_any(text, CONTEXT_PREFIXES)


def is_scenario_dependent(text: str) -> bool:
    stripped = text.strip()
    if CASE_LABEL_RE.search(stripped):
        return True
    if SCENARIO_INTERNAL_RE.search(stripped):
        return True
    if starts_with_any(stripped, SCENARIO_PREFIXES):
        return True
    if re.match(r"^\uc774 \uc0ac(\ub840|\uc548|\uac74|)\b", stripped):
        return True
    if re.match(r"^\uc774 \uc0ac\ubc95\uc2dc\ud5d8\ub839\b", stripped):
        return True
    return False


def is_not_sentence(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped.endswith((".", "다.", "요.", "됨.", "함.")):
        return False
    return True


def is_split_fragment(item: dict[str, Any]) -> bool:
    pid = item_id(item)
    quality = item.get("quality") if isinstance(item.get("quality"), dict) else {}
    return bool(
        re.search(r"-s\d+$", pid)
        or int(item.get("refinedPart") or 1) > 1
        or quality.get("splitFromComplexAtom")
    )


def needs_self_containment_repair(item: dict[str, Any]) -> bool:
    text = clean_text(item.get("rep"))
    if is_context_start(text) or is_scenario_dependent(text) or is_not_sentence(text):
        return True
    if is_split_fragment(item):
        first = text.split(" ", 1)[0]
        weak_first_words = {
            "\uc911\ub3c5",
            "\ud611\ub825\ud558\uc9c0",
            "\ubcf8\uc778\uc774",
            "\uc0c1\ub300\ubc29\uc774",
            "\ubb34\uad8c\ub300\ub9ac\ud589\uc704\uac00",
            "\uc124\ub839",
            "\uc7ac\uc0dd\ud654\uba74\uc5d0\ub294",
            "\ubc18\ub4dc\uc2dc",
            "\ub2e4\ub978",
        }
        if first in weak_first_words:
            return True
    return False


def apply_text_fixes(text: str) -> str:
    out = clean_text(text)
    for wrong, right in TYPO_FIXES:
        out = out.replace(wrong, right)
    if out.startswith("\uadf8\ub9ac\uace0 "):
        out = out[len("\uadf8\ub9ac\uace0 ") :]
    return out


def load_raw_maps() -> dict[str, dict[str, dict[str, Any]]]:
    maps: dict[str, dict[str, dict[str, Any]]] = {}
    for layer, path in RAW_FILES.items():
        payload = read_json(path)
        rows = payload["items"] if isinstance(payload, dict) and "items" in payload else payload
        by_pid: dict[str, dict[str, Any]] = {}
        for row in rows:
            pid = str(row.get("pid") or "")
            if pid:
                by_pid[pid] = row
            if layer in {"criminal", "public"}:
                round_no = row.get("round")
                q_no = row.get("question_no")
                choice = clean_text(row.get("choice"))
                if round_no and q_no and choice:
                    key = f"{layer}-bar{int(round_no):02d}-q{int(q_no):02d}-{choice}"
                    by_pid[key] = row
        maps[layer] = by_pid
    return maps


def make_merged_item(layer: str, group: list[dict[str, Any]], raw_maps: dict[str, dict[str, dict[str, Any]]]) -> tuple[dict[str, Any] | None, str]:
    exemplar = copy.deepcopy(group[0])
    base = base_pid(exemplar)
    raw = raw_maps.get(layer, {}).get(base)
    source_text = ""
    if raw:
        source_text = clean_text(raw.get("rep") or raw.get("q"))
    if not source_text:
        source_text = clean_text(exemplar.get("source_statement"))
    if not source_text:
        source_text = clean_text(exemplar.get("rep"))
    source_text = apply_text_fixes(source_text)
    if not source_text or is_scenario_dependent(source_text) or is_not_sentence(source_text):
        return None, "context_dependent_split_source"
    merged = exemplar
    merged["pid"] = base
    merged["rep"] = source_text
    merged["why"] = source_text if layer == "civil" else clean_text(exemplar.get("why"))
    merged["twins"] = []
    merged["quality"] = {
        **(merged.get("quality") if isinstance(merged.get("quality"), dict) else {}),
        "selfContainedReview": "merged_split_source",
        "mergedFrom": [item_id(item) for item in group],
    }
    return merged, "merged_split_source"


def review_layer(layer: str, raw_maps: dict[str, dict[str, dict[str, Any]]]) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = read_json(SOURCE_FILES[layer])
    items = payload["items"]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[base_pid(item)].append(item)

    reviewed: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    decision_counts: Counter[str] = Counter()

    for base, group in grouped.items():
        group_has_split = len(group) > 1 or any(is_split_fragment(item) for item in group)
        group_needs_repair = any(needs_self_containment_repair(item) for item in group)
        if group_has_split and group_needs_repair:
            merged, reason = make_merged_item(layer, group, raw_maps)
            if merged:
                reviewed.append(merged)
                decision_counts[reason] += 1
                decisions.append(
                    {
                        "layer": layer,
                        "base": base,
                        "decision": reason,
                        "from": [item_id(item) for item in group],
                        "rep": merged.get("rep"),
                    }
                )
            else:
                kept = 0
                for item in group:
                    if needs_self_containment_repair(item):
                        decision_counts[reason] += 1
                        decisions.append(
                            {
                                "layer": layer,
                                "base": base,
                                "pid": item_id(item),
                                "decision": reason,
                                "rep": item.get("rep"),
                            }
                        )
                        continue
                    copied = copy.deepcopy(item)
                    copied["rep"] = apply_text_fixes(copied.get("rep"))
                    reviewed.append(copied)
                    kept += 1
                if kept:
                    decision_counts["kept_safe_siblings"] += kept
            continue

        for item in group:
            copied = copy.deepcopy(item)
            copied["rep"] = apply_text_fixes(copied.get("rep"))
            rep = clean_text(copied.get("rep"))
            if is_scenario_dependent(rep) or is_context_start(rep) or is_not_sentence(rep):
                decision = "excluded_context_dependent"
                decision_counts[decision] += 1
                decisions.append(
                    {
                        "layer": layer,
                        "base": base,
                        "pid": item_id(item),
                        "decision": decision,
                        "rep": rep,
                    }
                )
                continue
            if copied["rep"] != item.get("rep"):
                decision_counts["text_fix"] += 1
                decisions.append(
                    {
                        "layer": layer,
                        "base": base,
                        "pid": item_id(item),
                        "decision": "text_fix",
                        "before": item.get("rep"),
                        "after": copied["rep"],
                    }
                )
            reviewed.append(copied)

    out = copy.deepcopy(payload)
    out["version"] = "v002-self-contained"
    out["updatedAt"] = datetime.now(timezone.utc).isoformat()
    out["inputCount"] = len(items)
    out["count"] = len(reviewed)
    out["selfContainedReview"] = {
        "method": "full item pass with source-backed merge/exclusion for non-standalone atoms",
        "dropped": len(items) - len(reviewed),
        "decisions": dict(decision_counts),
    }
    out["items"] = reviewed
    report = {
        "layer": layer,
        "inputCount": len(items),
        "outputCount": len(reviewed),
        "decisions": dict(decision_counts),
        "details": decisions,
    }
    return out, report


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    raw_maps = load_raw_maps()
    reports: list[dict[str, Any]] = []
    for layer in ("civil", "criminal", "public"):
        payload, report = review_layer(layer, raw_maps)
        write_json(OUT_FILES[layer], payload)
        reports.append(report)

    total_in = sum(report["inputCount"] for report in reports)
    total_out = sum(report["outputCount"] for report in reports)
    audit = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "totalInput": total_in,
        "totalOutput": total_out,
        "totalDropped": total_in - total_out,
        "layers": reports,
    }
    write_json(REPORT_JSON, audit)

    lines = [
        "# CLAT atom self-contained repair v002",
        "",
        f"- Input atoms: {total_in:,}",
        f"- Output atoms: {total_out:,}",
        f"- Dropped/context-held atoms: {total_in - total_out:,}",
        "",
    ]
    for report in reports:
        lines.append(f"## {report['layer']}")
        lines.append("")
        lines.append(f"- Input: {report['inputCount']:,}")
        lines.append(f"- Output: {report['outputCount']:,}")
        for key, value in report["decisions"].items():
            lines.append(f"- {key}: {value:,}")
        lines.append("")
        for detail in report["details"][:80]:
            rep = clean_text(detail.get("rep") or detail.get("after") or "")
            lines.append(f"- `{detail.get('decision')}` `{detail.get('pid') or detail.get('base')}` {rep[:180]}")
        lines.append("")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"self-contained repair: input={total_in} output={total_out} dropped={total_in-total_out}")


if __name__ == "__main__":
    main()
