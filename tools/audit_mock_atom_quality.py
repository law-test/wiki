#!/usr/bin/env python3
r"""Audit local-only mock-exam CLAT atom quality.

This does not modify game banks.  It scans all
`C:\cowork\lawinus.org\02_비공개데이터\private_problem_banks\mock*` atom payloads and
writes a private JSON/Markdown report under `law-test-private\reports`.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


PRIVATE_ROOT = Path(r"C:\cowork\lawinus.org\02_비공개데이터\private_problem_banks")
REPORT_ROOT = Path(r"C:\cowork\lawinus.org\02_비공개데이터\reports")

EXPECTED_SUBJECTS = {"민법", "민사소송법", "상법", "형법", "형사소송법", "헌법", "행정법"}
EXPECTED_SUBJECT_AREAS = {"민사법", "형사법", "공법"}
BROKEN_RE = re.compile(r"[�]|占|竊|蹂|誘쇱|誘쇰|怨듬|뺤|뚯|몄|쒗|Ã|Â|ì|ë|í|Ð|þ|捤獥|汤捯")
QUESTION_RE = re.compile(r"(옳은 것은|옳지 않은 것은|타당한 것은|타당하지 않은 것은|모두 고른 것은|고른 것은|다음 중|보기 중|문\s*\d+)")
CHOICE_MARK_RE = re.compile(r"[①②③④⑤❶❷❸❹❺]")
REFERENCE_IN_PROMPT_RE = re.compile(
    r"(대법원\s*\d{4}\.|\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.\s*선고|헌재\s*\d{4}\.|"
    r"헌법재판소\s*\d{4}\.|[가-힣]+법\s*제\s*\d+\s*조|제\s*\d+\s*조(?:의\s*\d+)?)"
)
PARTY_LABEL_RE = re.compile(r"(?<![A-Za-z])[A-Z](?![A-Za-z])|[甲乙丙丁戊己庚辛壬癸]")
BAD_START_RE = re.compile(r"^(위|그|이|해당|전항|후항|위와 같은|이와 같은|이러한|그러한)\s")
BAD_PHRASE_RE = re.compile(r"(위와 같은|이와 같은|이러한 경우|그러한 경우|이 경우|위 사안|본 사안|위 판례)")
CASE_ROLE_RE = re.compile(r"(원고|피고|피해자|피의자|피고인|고소인|피고 회사|갑 회사|을 회사)")
PLACEHOLDER_RE = re.compile(r"(당사자|상대방|목적물|가나건설|K국|P가|P에|Z는|제1범죄사실|증거\s*[❶❷❸❹❺])")


def load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def mock_sort_key(path: Path) -> tuple[int, str]:
    match = re.search(r"mock(\d+)", path.as_posix())
    return (int(match.group(1)) if match else 999, path.as_posix())


def atom_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("ox_mock*_expected_atoms_v001.json"):
        if re.search(r"_민법_|_민사소송법_|_상법_|_형법_|_형사소송법_|_헌법_|_행정법_", path.name):
            continue
        files.append(path)
    return sorted(files, key=mock_sort_key)


def prompt_text(item: dict[str, Any]) -> str:
    return str(item.get("rep") or item.get("q") or "").strip()


def source_labels(item: dict[str, Any]) -> list[str]:
    labels = []
    labels.extend(str(value) for value in (item.get("src") or []) if value)
    labels.extend(str(value) for value in (item.get("years") or []) if value)
    if item.get("mockPublicLabel"):
        labels.append(str(item["mockPublicLabel"]))
    for source in item.get("privateSources") or []:
        if source.get("publicLabel"):
            labels.append(str(source["publicLabel"]))
    return labels


def inspect_atom(item: dict[str, Any]) -> list[str]:
    text = prompt_text(item)
    reasons: list[str] = []
    if not text:
        return ["empty_prompt"]
    if item.get("a") not in {"O", "X"}:
        reasons.append("bad_answer")
    if item.get("subject") not in EXPECTED_SUBJECTS:
        reasons.append("bad_subject")
    if item.get("subjectArea") not in EXPECTED_SUBJECT_AREAS:
        reasons.append("bad_subject_area")
    if BROKEN_RE.search(text):
        reasons.append("broken_text")
    if "?" in text:
        reasons.append("question_mark_or_artifact")
    if QUESTION_RE.search(text) or CHOICE_MARK_RE.search(text):
        reasons.append("question_format_leftover")
    if REFERENCE_IN_PROMPT_RE.search(text):
        reasons.append("reference_in_prompt")
    if PARTY_LABEL_RE.search(text):
        reasons.append("party_label")
    if CASE_ROLE_RE.search(text):
        reasons.append("case_role")
    if PLACEHOLDER_RE.search(text):
        reasons.append("placeholder_leftover")
    if BAD_START_RE.search(text):
        reasons.append("dependent_start")
    if BAD_PHRASE_RE.search(text):
        reasons.append("dependent_phrase")
    if len(text) < 18:
        reasons.append("too_short")
    if len(text) > 260:
        reasons.append("too_long")
    if not re.search(r"(다|된다|아니다|없다|있다|한다|못한다)\.$", text):
        reasons.append("not_declarative_ending")
    labels = source_labels(item)
    for label in labels:
        if not re.fullmatch(r"변호사시험 \d+회 예상", label):
            reasons.append("bad_public_source_label")
            break
    if not item.get("privateSources"):
        reasons.append("missing_private_source")
    return reasons


def short(text: str, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PRIVATE_ROOT)
    parser.add_argument("--report-root", type=Path, default=REPORT_ROOT)
    parser.add_argument("--sample-limit", type=int, default=12)
    args = parser.parse_args()

    files = atom_files(args.root)
    if not files:
        raise SystemExit(f"no mock atom files found under {args.root}")

    all_issues: list[dict[str, Any]] = []
    per_file: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    subject_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    duplicate_counter: Counter[tuple[str, str, str]] = Counter()
    total_atoms = 0

    for path in files:
        payload = load_payload(path)
        items = payload.get("items") or []
        file_reason_counts: Counter[str] = Counter()
        file_subject_counts: Counter[str] = Counter()
        file_issue_count = 0
        for index, item in enumerate(items):
            total_atoms += 1
            text = prompt_text(item)
            subject = str(item.get("subject") or "")
            answer = str(item.get("a") or "")
            file_subject_counts[subject] += 1
            subject_counts[subject] += 1
            duplicate_counter[(subject, re.sub(r"\s+", "", text), answer)] += 1
            for label in set(source_labels(item)):
                source_counts[label] += 1
            reasons = inspect_atom(item)
            if not reasons:
                continue
            file_issue_count += 1
            for reason in reasons:
                reason_counts[reason] += 1
                file_reason_counts[reason] += 1
            all_issues.append(
                {
                    "file": str(path),
                    "index": index,
                    "pid": item.get("pid"),
                    "subject": item.get("subject"),
                    "subjectArea": item.get("subjectArea"),
                    "answer": item.get("a"),
                    "reasons": reasons,
                    "prompt": text,
                    "sourceLabels": source_labels(item),
                    "privateSources": item.get("privateSources") or [],
                }
            )
        per_file.append(
            {
                "file": str(path),
                "count": len(items),
                "issueCount": file_issue_count,
                "issueRatio": round(file_issue_count / len(items), 4) if items else 0,
                "reasons": dict(file_reason_counts),
                "subjects": dict(file_subject_counts),
            }
        )

    duplicates = [
        {"subject": key[0], "answer": key[2], "prompt": key[1], "count": count}
        for key, count in duplicate_counter.items()
        if count > 1
    ]
    duplicates.sort(key=lambda row: row["count"], reverse=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.report_root.mkdir(parents=True, exist_ok=True)
    out_json = args.report_root / f"mock_atom_quality_audit_{stamp}.json"
    out_md = args.report_root / f"mock_atom_quality_audit_{stamp}.md"

    payload = {
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "files": [str(path) for path in files],
        "totalAtoms": total_atoms,
        "issueAtoms": len(all_issues),
        "issueRatio": round(len(all_issues) / total_atoms, 4) if total_atoms else 0,
        "reasonCounts": dict(reason_counts),
        "subjectCounts": dict(subject_counts),
        "sourceCounts": dict(source_counts),
        "duplicatePromptAnswerCount": len(duplicates),
        "topDuplicates": duplicates[:50],
        "perFile": per_file,
        "issues": all_issues,
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Mock Atom Quality Audit",
        "",
        f"- Created: {payload['createdAt']}",
        f"- Files: {len(files)}",
        f"- Total atoms: {total_atoms:,}",
        f"- Flagged atoms: {len(all_issues):,} ({payload['issueRatio'] * 100:.2f}%)",
        f"- Duplicate same prompt/answer keys: {len(duplicates):,}",
        "",
        "## Reasons",
        "",
    ]
    for reason, count in reason_counts.most_common():
        lines.append(f"- {reason}: {count:,}")
    lines.extend(["", "## Per File", ""])
    for row in per_file:
        lines.append(f"- {Path(row['file']).parent.name}: {row['count']:,} atoms, {row['issueCount']:,} flagged ({row['issueRatio'] * 100:.2f}%)")
    lines.extend(["", "## Samples", ""])
    for issue in all_issues[: args.sample_limit]:
        lines.append(
            f"- {Path(issue['file']).parent.name} / {issue['subject']} / {issue['pid']} / "
            f"{', '.join(issue['reasons'])}: {short(issue['prompt'])}"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"mock_atom_audit total={total_atoms} flagged={len(all_issues)} report={out_md}")


if __name__ == "__main__":
    main()
