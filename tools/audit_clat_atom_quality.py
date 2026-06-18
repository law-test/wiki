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
BANK = ASSETS / "ox_clat_unified_v001.json"
OUT_JSON = REPORTS / "clat_atom_quality_audit.json"
OUT_MD = REPORTS / "clat_atom_quality_audit.md"


def load_items() -> list[dict[str, Any]]:
    payload = json.loads(BANK.read_text(encoding="utf-8"))
    return payload.get("items") or []


def has_case_name(text: str) -> bool:
    if any(char in text for char in "甲乙丙丁戊己庚辛"):
        return True
    case_targets = "토지|건물|회사|은행|채권|채무|주식|부동산|원고|피고|매수인|매도인"
    return bool(re.search(rf"(?<![가-힣])(?:갑|을|병|정)\s*(?:{case_targets})", text))


def starts_with_orphan_label(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    labels = (
        "①",
        "②",
        "③",
        "④",
        "⑤",
        "(1)",
        "(2)",
        "(3)",
        "(4)",
        "(5)",
        "ㄱ.",
        "ㄴ.",
        "ㄷ.",
        "ㄹ.",
        "ㅁ.",
        "ㄱ)",
        "ㄴ)",
        "ㄷ)",
        "ㄹ)",
        "ㅁ)",
    )
    if stripped.startswith(labels):
        return True
    return len(stripped) > 2 and stripped[0].isdigit() and stripped[1] == "."


def sentence_count(text: str) -> int:
    return len(re.findall(r"(?:다|이다|한다|된다|없다|있다)\.", text))


def inspect_item(index: int, item: dict[str, Any]) -> list[str]:
    text = str(item.get("rep") or "")
    reasons: list[str] = []
    if not text:
        reasons.append("empty")
    if any(mark in text for mark in ("???", "??", "�", "| |")):
        reasons.append("broken_or_artifact")
    if any(mark in text for mark in ("?", "？", "교수 :", "학생 :", "할 수 있는가", "되는가", "인가?")):
        reasons.append("question_or_dialogue")
    if has_case_name(text):
        reasons.append("case_name")
    if starts_with_orphan_label(text):
        reasons.append("orphan_label")
    if len(text) > 230:
        reasons.append("long")
    if sentence_count(text) >= 3:
        reasons.append("multi_sentence")
    return reasons


def main() -> None:
    items = load_items()
    issues: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    by_layer: Counter[str] = Counter()
    by_subject: Counter[str] = Counter()
    for index, item in enumerate(items):
        targets = [("rep", item.get("rep"), item.get("a"))]
        for twin_index, twin in enumerate(item.get("twins") or [], start=1):
            targets.append((f"twin{twin_index}", twin.get("q"), "X"))
        for field, text, answer in targets:
            probe = dict(item)
            probe["rep"] = text
            reasons = inspect_item(index, probe)
            if not reasons:
                continue
            for reason in reasons:
                counts[reason] += 1
            by_layer[str(item.get("sourceLayer") or "")] += 1
            by_subject[str(item.get("subject") or "")] += 1
            issues.append(
                {
                    "index": index,
                    "field": field,
                    "pid": item.get("pid"),
                    "subject": item.get("subject"),
                    "sourceLayer": item.get("sourceLayer"),
                    "reasons": reasons,
                    "answer": answer,
                    "text": text,
                    "src": item.get("src"),
                }
            )

    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "total": len(items),
        "issueCount": len(issues),
        "issueRatio": round(len(issues) / len(items), 4) if items else 0,
        "reasons": dict(counts),
        "byLayer": dict(by_layer),
        "bySubject": dict(by_subject),
        "issues": issues,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# CLAT atom 품질 점검",
        "",
        f"- 점검일: {payload['updatedAt']}",
        f"- 전체 문항: {payload['total']}개",
        f"- 점검 필요: {payload['issueCount']}개 ({payload['issueRatio'] * 100:.2f}%)",
        "",
        "## 유형별",
        "",
    ]
    if counts:
        for key, count in counts.most_common():
            lines.append(f"- {key}: {count}개")
    else:
        lines.append("- 자동 점검상 즉시 수정할 항목 없음")
    lines.extend(["", "## 층별", ""])
    for key, count in by_layer.most_common():
        lines.append(f"- {key}: {count}개")
    lines.extend(["", "## 샘플", ""])
    for issue in issues[:30]:
        text = str(issue["text"] or "")
        lines.append(
            f"- {issue['subject']} / {issue['pid']} / {issue['field']} / {', '.join(issue['reasons'])}: {text[:180]}"
        )
    lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"quality audit: total={len(items)} issues={len(issues)}")


if __name__ == "__main__":
    main()
