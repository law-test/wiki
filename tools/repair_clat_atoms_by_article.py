#!/usr/bin/env python3
r"""Repair CLAT atom wording by statute-article unit and merge exact duplicates.

The script focuses on safe wording cleanup in the private current CLAT bank:

- normalize broken spacing and punctuation
- remove residual source/page fragments
- replace obvious exam-case labels such as `<경우 ❶>`, `증거 ❷`, `K국`, `P가`
- fix malformed placeholder particles such as `당사자과`, `당사자으로`
- group the result by `(subject, article, answer, prompt)` and merge exact duplicates

It intentionally does not invent new legal doctrine.  Items that still look
case-dependent after safe repair are reported for later manual/legal curation.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


PRIVATE_ROOT = Path(r"C:\cowork\lawinus.org\02_비공개데이터\private_problem_banks")
REPORT_ROOT = Path(r"C:\cowork\lawinus.org\02_비공개데이터\reports")
DEFAULT_CURRENT = PRIVATE_ROOT / "current" / "ox_clat_unified_v001.json"

ARTICLELESS = "조문미상"


def clean_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\u00a0", " ").replace("\u3000", " ").replace("\xad", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"(?:,\s*){2,}", ", ", text)
    text = re.sub(r"(?:;\s*){2,}", "; ", text)
    text = re.sub(r"([,.;:])(?=[^\s\d])", r"\1 ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def unique_keep_order(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    out: list[Any] = []
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def normalize_article(item: dict[str, Any]) -> str:
    art = clean_text(item.get("art") or item.get("article"))
    if art:
        return art
    refs = item.get("articleRefs") or []
    if refs:
        return clean_text(refs[0])
    ref = clean_text(item.get("ref"))
    match = re.search(r"([가-힣]+법)\s*제\s*(\d+)\s*조(?:의\s*(\d+))?", ref)
    if match:
        suffix = f"의{match.group(3)}" if match.group(3) else ""
        return f"제{match.group(2)}조{suffix}"
    return ARTICLELESS


def article_no(article: str) -> int | None:
    match = re.search(r"제\s*(\d+)\s*조", article)
    return int(match.group(1)) if match else None


def is_mock_related(item: dict[str, Any]) -> bool:
    if item.get("sourceLayer") == "mock_expected_atom":
        return True
    if item.get("mockPublicLabel") or item.get("mockYear"):
        return True
    for source in item.get("privateSources") or []:
        if source.get("examYear") or str(source.get("id") or "").startswith("mock"):
            return True
    labels = [*list(item.get("src") or []), *list(item.get("years") or [])]
    return any("예상" in str(label) for label in labels)


SOURCE_FRAGMENT_RE = re.compile(r"\s*(?:민사법|형사법|공법|사법)?\s*\d+\s*책형\s*\d+\s*쪽\s*")
CASE_CHOICE_RE = re.compile(r"<\s*경우\s*[❶❷❸❹❺①②③④⑤1-5]\s*>\s*에서")
CASE_CHOICE_BARE_RE = re.compile(r"<\s*경우\s*[❶❷❸❹❺①②③④⑤1-5]\s*>")
EVIDENCE_MARK_RE = re.compile(r"증거\s*[❶❷❸❹❺①②③④⑤1-5]")
CRIME_FACT_RE = re.compile(r"제\s*[1-5]\s*범죄사실")


SAFE_REPLACEMENTS = [
    ("당사자과", "당사자와"),
    ("당사자와과", "당사자와"),
    ("당사자으로", "당사자로"),
    ("당사자을", "당사자를"),
    ("당사자은", "당사자는"),
    ("당사자 부동산", "당사자의 부동산"),
    ("당사자부동산", "당사자의 부동산"),
    ("상대방부동산", "상대방의 부동산"),
    ("목적물부동산", "목적 부동산"),
    ("당사자회사", "해당 회사"),
    ("당사자 회사", "해당 회사"),
    ("원고 당사자", "원고"),
    ("피고 당사자", "피고"),
    ("피고 만", "피고만"),
    ("원고 만", "원고만"),
    ("피고 의", "피고의"),
    ("원고 의", "원고의"),
    ("제 심판결", "제1심판결"),
    ("제 심 판결", "제1심판결"),
    ("할 1 수 있다", "할 수 있다"),
    ("고 한다", "고 한다"),
    (" .", "."),
    (" ,", ","),
]


REGEX_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (SOURCE_FRAGMENT_RE, " "),
    (CASE_CHOICE_RE, "해당 경우에 "),
    (CASE_CHOICE_BARE_RE, "해당 경우"),
    (EVIDENCE_MARK_RE, "해당 증거"),
    (CRIME_FACT_RE, "해당 범죄사실"),
    (re.compile(r"\bFrank공식\b"), "프랑크 공식"),
    (re.compile(r"\bK국\b"), "어떤 국가"),
    (re.compile(r"\bP가\b"), "수사기관이"),
    (re.compile(r"\bP는\b"), "수사기관은"),
    (re.compile(r"\bP에 의해\b"), "수사기관에 의해"),
    (re.compile(r"\bP에게\b"), "수사기관에게"),
    (re.compile(r"\bP의\b"), "수사기관의"),
    (re.compile(r"\bZ는\b"), "제3자는"),
    (re.compile(r"\bZ가\b"), "제3자가"),
    (re.compile(r"\bZ의\b"), "제3자의"),
    (re.compile(r"\bZ에게\b"), "제3자에게"),
    (re.compile(r"\bZ를\b"), "제3자를"),
    (re.compile(r"\b가나건설\b"), "해당 회사"),
    (re.compile(r"\s{2,}"), " "),
]


REVIEW_PATTERNS = {
    "placeholder_leftover": re.compile(r"(당사자|상대방|목적물)"),
    "dependent_start": re.compile(r"^(위|그|이|해당|전항|후항|위와 같은|이와 같은|이러한|그러한)\s"),
    "dependent_phrase": re.compile(r"(위와 같은|이와 같은|이러한 경우|그러한 경우|위 사안|본 사안|위 판례)"),
    "party_label": re.compile(r"(?<![A-Za-z])[A-Z](?![A-Za-z])|[甲乙丙丁戊己庚辛壬癸]"),
    "choice_or_evidence_label": re.compile(r"[❶❷❸❹❺]"),
    "not_declarative": re.compile(r"(?<![다요음됨함함다니다없다있다한다된다아니다못한다])$"),
}


def repair_prompt(text: str) -> tuple[str, list[str]]:
    original = clean_text(text)
    repaired = original
    changes: list[str] = []

    for old, new in SAFE_REPLACEMENTS:
        if old in repaired:
            repaired = repaired.replace(old, new)
            changes.append(f"replace:{old}->{new}")

    for pattern, replacement in REGEX_REPLACEMENTS:
        new_text = pattern.sub(replacement, repaired)
        if new_text != repaired:
            changes.append(f"regex:{pattern.pattern}")
            repaired = new_text

    repaired = clean_text(repaired)
    repaired = re.sub(r"\s+([,.;:])", r"\1", repaired)
    repaired = re.sub(r"([,.;:])\s+", r"\1 ", repaired)
    repaired = re.sub(r"\s+", " ", repaired).strip(" ,")

    if repaired and not repaired.endswith((".", "다.", "다")):
        repaired += "."
        changes.append("ending_period")
    if repaired.endswith("다"):
        repaired += "."
        changes.append("ending_period")

    return repaired, changes


def review_reasons(text: str) -> list[str]:
    reasons = []
    for name, pattern in REVIEW_PATTERNS.items():
        if name == "not_declarative":
            if not re.search(r"(다|된다|아니다|없다|있다|한다|못한다)\.$", text):
                reasons.append(name)
            continue
        if pattern.search(text):
            reasons.append(name)
    return reasons


def item_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    subject = clean_text(item.get("subject"))
    article = normalize_article(item)
    answer = clean_text(item.get("a"))
    prompt = re.sub(r"\s+", "", clean_text(item.get("rep")))
    return subject, article, answer, prompt


def merge_item(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    target["freq"] = int(target.get("freq") or 1) + int(incoming.get("freq") or 1)
    for key in ("src", "years", "ids", "xref", "articleRefs", "privateSources"):
        values = list(target.get(key) or [])
        values.extend(incoming.get(key) or [])
        if values:
            target[key] = unique_keep_order(values)
    if not target.get("why") and incoming.get("why"):
        target["why"] = incoming["why"]
    if not target.get("ref") and incoming.get("ref"):
        target["ref"] = incoming["ref"]
    if not target.get("art") and incoming.get("art"):
        target["art"] = incoming["art"]
        target["artNo"] = incoming.get("artNo")
    target["hot"] = bool(target.get("hot") or incoming.get("hot"))


def normalize_metadata(payload: dict[str, Any]) -> None:
    items = list(payload.get("items") or [])
    payload["items"] = items
    payload["count"] = len(items)
    payload["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    payload["subjects"] = dict(Counter(clean_text(item.get("subject")) for item in items if clean_text(item.get("subject"))))
    payload["answers"] = dict(Counter(clean_text(item.get("a")) for item in items if clean_text(item.get("a"))))
    payload["layers"] = dict(Counter(clean_text(item.get("sourceLayer")) or "unknown" for item in items))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument("--report-root", type=Path, default=REPORT_ROOT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--mock-only", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.current.read_text(encoding="utf-8"))
    items = list(payload.get("items") or [])
    repaired_count = 0
    changed_items: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []
    article_stats: dict[str, Counter[str]] = defaultdict(Counter)

    for index, item in enumerate(items):
        if args.mock_only and not is_mock_related(item):
            continue
        article = normalize_article(item)
        subject = clean_text(item.get("subject"))
        article_key = f"{subject} {article}"
        before = clean_text(item.get("rep"))
        after, changes = repair_prompt(before)
        if changes and after and after != before:
            item["rep"] = after
            repaired_count += 1
            changed_items.append(
                {
                    "index": index,
                    "pid": item.get("pid"),
                    "subject": subject,
                    "article": article,
                    "answer": item.get("a"),
                    "before": before,
                    "after": after,
                    "changes": changes,
                    "mockRelated": is_mock_related(item),
                    "sources": item.get("src") or item.get("years"),
                }
            )
            article_stats[article_key]["changed"] += 1
        reasons = review_reasons(clean_text(item.get("rep")))
        if reasons:
            review_items.append(
                {
                    "index": index,
                    "pid": item.get("pid"),
                    "subject": subject,
                    "article": article,
                    "answer": item.get("a"),
                    "prompt": item.get("rep"),
                    "reasons": reasons,
                    "mockRelated": is_mock_related(item),
                    "sources": item.get("src") or item.get("years"),
                }
            )
            for reason in reasons:
                article_stats[article_key][reason] += 1
        article_stats[article_key]["total"] += 1

    deduped: list[dict[str, Any]] = []
    index_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    merged_duplicates = 0
    for item in items:
        key = item_key(item)
        if key in index_by_key:
            merge_item(index_by_key[key], item)
            merged_duplicates += 1
        else:
            index_by_key[key] = item
            deduped.append(item)

    payload["items"] = deduped
    normalize_metadata(payload)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.report_root.mkdir(parents=True, exist_ok=True)
    report_json = args.report_root / f"clat_article_atom_repair_{stamp}.json"
    report_md = args.report_root / f"clat_article_atom_repair_{stamp}.md"

    top_articles = sorted(
        (
            {"articleKey": key, **dict(counter)}
            for key, counter in article_stats.items()
        ),
        key=lambda row: (row.get("changed", 0) + sum(v for k, v in row.items() if k not in {"articleKey", "total", "changed"})),
        reverse=True,
    )
    report = {
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "current": str(args.current),
        "apply": args.apply,
        "mockOnly": args.mock_only,
        "originalCount": len(items),
        "finalCount": len(deduped),
        "repairedItems": repaired_count,
        "mergedExactDuplicates": merged_duplicates,
        "reviewItems": len(review_items),
        "reviewReasonCounts": dict(Counter(reason for item in review_items for reason in item["reasons"])),
        "topArticles": top_articles[:200],
        "changedItems": changed_items,
        "reviewSamples": review_items[:1000],
    }
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# CLAT Article Atom Repair",
        "",
        f"- Created: {report['createdAt']}",
        f"- Apply: {args.apply}",
        f"- Mock only: {args.mock_only}",
        f"- Original count: {len(items):,}",
        f"- Final count after exact merge: {len(deduped):,}",
        f"- Repaired items: {repaired_count:,}",
        f"- Exact duplicates merged: {merged_duplicates:,}",
        f"- Still needs review: {len(review_items):,}",
        "",
        "## Review Reasons",
        "",
    ]
    for reason, count in Counter(reason for item in review_items for reason in item["reasons"]).most_common():
        lines.append(f"- {reason}: {count:,}")
    lines.extend(["", "## Top Article Units", ""])
    for row in top_articles[:40]:
        key = row.pop("articleKey")
        detail = ", ".join(f"{k}={v}" for k, v in row.items() if v)
        lines.append(f"- {key}: {detail}")
    lines.extend(["", "## Changed Samples", ""])
    for row in changed_items[:40]:
        lines.append(f"- {row['subject']} {row['article']} / {row['pid']}: {row['before']} => {row['after']}")
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if args.apply:
        backup = args.current.with_name(args.current.stem + f".article_repair_backup_{stamp}" + args.current.suffix)
        shutil.copy2(args.current, backup)
        args.current.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"backup={backup}")
    print(
        f"article_repair apply={args.apply} repaired={repaired_count} "
        f"merged={merged_duplicates} review={len(review_items)} report={report_md}"
    )


if __name__ == "__main__":
    main()
