#!/usr/bin/env python3
"""Build local-only Supabase import SQL for private game question banks.

The generated .local.sql files contain the problem bank text. Keep them outside
the deploy repository and never commit them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(r"C:\cowork\law-test-private\private_problem_banks\current")
DEFAULT_OUT = Path(r"C:\cowork\law-test-private\supabase_private_game_bank_import")


ARTICLE_RE = re.compile(r"제\s*(\d+)\s*(?:조의\s*(\d+)|의\s*(\d+)\s*조|조)")
SOURCE_PATTERNS = [
    (re.compile(r"(?:변호사시험\s*)?변시\s*(\d{1,2})\s*(?:회)?\s*(?:민사법|민법|상법|민사소송법|형사법|형법|형사소송법|공법|헌법|행정법)?\s*(?:선택형)?\s*(?:문제|문항|문)\s*(\d{1,3})\s*(?:번)?\s*(?:보기)?\s*([ㄱ-ㅎ①-⑤])?"), "변시"),
    (re.compile(r"(?:변호사시험\s*)?변시\s*(\d{1,2})\s*(?:회)?\s+(\d{1,3})\s*(?:번)?\s*([ㄱ-ㅎ①-⑤])?"), "변시"),
    (re.compile(r"변호사시험\s*(?:제)?\s*(\d{1,2})\s*회\s*(?:민사법|민법|상법|민사소송법|형사법|형법|형사소송법|공법|헌법|행정법)?\s*(?:선택형)?\s*(?:(?:문제|문항|문)\s*)?(\d{1,3})?\s*(?:번)?\s*(?:보기)?\s*([ㄱ-ㅎ①-⑤])?"), "변시"),
    (re.compile(r"(?:변호사시험\s*)?변시\s*(\d{1,2})\s*(?:회)?"), "변시"),
    (re.compile(r"법윤\s*(\d{1,2})"), "법윤"),
    (re.compile(r"법조윤리\s*(\d{1,2})"), "법윤"),
    (re.compile(r"법원직\s*(\d{2,4})\s*년?\s*(\d{1,3})?\s*번?\s*([ㄱ-ㅎ①-⑤])?"), "법원직"),
]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def sha_pid(*parts: str) -> str:
    raw = "|".join(clean_text(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def normalize_article_no(value: str) -> str:
    value = re.sub(r"\s+", "", value or "")
    value = re.sub(r"^제(\d+)의(\d+)조$", r"제\1조의\2", value)
    return value


def article_norms(*values: Any) -> list[str]:
    out: list[str] = []
    for value in values:
        text = clean_text(value)
        for match in ARTICLE_RE.finditer(text):
            no = match.group(1)
            sub = match.group(2) or match.group(3)
            norm = f"제{no}조의{sub}" if sub else f"제{no}조"
            if norm not in out:
                out.append(norm)
    return out


def law_name_from_article(article: str, subject: str) -> str:
    prefix = re.split(r"제\s*\d+", article or "", maxsplit=1)[0]
    prefix = re.sub(r"[·,;]\s*$", "", clean_text(prefix))
    return prefix or subject


def short_year(value: str) -> str:
    value = str(value or "")
    if len(value) == 4 and value.startswith("20"):
        return value[2:]
    return value


def round_no(value: str) -> str:
    value = str(value or "").strip()
    return str(int(value)) if value.isdigit() else value


def source_label(kind: str, round_value: str, q_no: str = "", marker: str = "") -> str:
    q_no = clean_text(q_no)
    marker = clean_text(marker)
    if kind == "변시":
        label = f"변호사시험{round_no(round_value)}회"
    elif kind == "법윤":
        label = f"법조윤리{round_no(round_value)}회"
    elif kind == "법원직":
        label = f"법원직{short_year(round_value)}년"
    else:
        label = clean_text(round_value)
    if q_no:
        label += f" {q_no}번"
    if marker:
        label += f" {marker}"
    return label


def flatten(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, list):
        out: list[str] = []
        for value in values:
            out.extend(flatten(value))
        return out
    return [clean_text(values)]


def source_tags(*values: Any) -> str:
    tags: list[str] = []

    def push(tag: str) -> None:
        tag = clean_text(tag)
        if not tag or tag in tags:
            return
        base_match = re.match(r"^(변호사시험\d+회|법조윤리\d+회|법원직\d+년)", tag)
        if base_match and "번" in tag:
            base = base_match.group(1)
            tags[:] = [x for x in tags if x != base]
        if base_match and tag == base_match.group(1) and any(x.startswith(tag + " ") for x in tags):
            return
        tags.append(tag)

    for raw in values:
        for text in flatten(raw):
            text = text.replace("변호사시험 변시", "변시").replace("법원직 법원직", "법원직")
            text = re.sub(r"변시\s*1\s+0\s*번", "변시10", text)
            text = re.sub(r"변호사시험\s*1\s*회\s+0\s*번", "변호사시험10회", text)
            matched = False
            for pattern, kind in SOURCE_PATTERNS:
                for match in pattern.finditer(text):
                    matched = True
                    if kind == "변시":
                        groups = match.groups()
                        round_no = groups[0]
                        q_no = groups[1] if len(groups) > 1 and groups[1] else ""
                        marker = groups[2] if len(groups) > 2 and groups[2] else ""
                        if q_no:
                            push(source_label(kind, round_no, q_no, marker))
                        else:
                            push(source_label(kind, round_no))
                    elif kind == "법윤":
                        push(source_label(kind, match.group(1)))
                    elif kind == "법원직":
                        year, q_no, marker = match.group(1), match.group(2), match.group(3) or ""
                        if q_no:
                            push(source_label(kind, year, q_no, marker))
                        else:
                            push(source_label(kind, year))

    def sort_key(tag: str) -> tuple[int, str]:
        numbers = re.findall(r"\d+", tag)
        return (-(int(numbers[0]) if numbers else 0), tag)

    tags.sort(key=sort_key)
    return " · ".join(tags[:8])


def sql_text(value: Any) -> str:
    if value is None:
        return "null"
    text = str(value)
    if text == "":
        return "null"
    return "convert_from(decode('" + text.encode("utf-8").hex() + "','hex'),'UTF8')"


def sql_array(values: list[str]) -> str:
    values = [v for v in values if v]
    if not values:
        return "'{}'::text[]"
    return "array[" + ",".join(sql_text(v) for v in values) + "]::text[]"


def sql_json(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return sql_text(payload) + "::jsonb"


def as_int(value: Any, default: int = 1) -> int:
    try:
        return int(value)
    except Exception:
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def row_sql(row: dict[str, Any]) -> str:
    values = [
        sql_text(row["bank"]),
        sql_text(row["source_pid"]),
        sql_text(row["source_variant"]),
        sql_text(row["subject"]),
        sql_text(row["law_name"]),
        sql_text(row["article"]),
        sql_array(row["article_norms"]),
        sql_text(row["topic"]),
        sql_text(row["prompt"]),
        sql_text(row["answer"]),
        sql_text(row["explanation"]),
        sql_text(row["reference_text"]),
        sql_text(row["corrected_prompt"]),
        sql_text(row["grade"]),
        f"{as_float(row['weight']):.6f}",
        str(max(1, as_int(row["freq"]))),
        sql_text(row["tags"]),
        sql_json(row["meta"]),
        "true",
    ]
    return "(" + ",".join(values) + ")"


def make_row(
    *,
    bank: str,
    source_pid: str,
    variant: str,
    item: dict[str, Any],
    prompt: str,
    answer: str,
    corrected: str = "",
    twin: dict[str, Any] | None = None,
) -> dict[str, Any]:
    subject = clean_text(item.get("subject") or ("법조윤리" if bank == "ethics" else "민법"))
    article = clean_text((twin or {}).get("art") or item.get("art") or "")
    ref = clean_text((twin or {}).get("ref") or item.get("ref") or item.get("source_basis") or "")
    tags = source_tags(
        item.get("years"),
        item.get("src"),
        item.get("refs"),
        item.get("ref"),
        (twin or {}).get("years"),
        (twin or {}).get("src"),
        (twin or {}).get("refs"),
        (twin or {}).get("ref"),
    )
    return {
        "bank": bank,
        "source_pid": source_pid,
        "source_variant": variant,
        "subject": subject,
        "law_name": law_name_from_article(article, subject),
        "article": article,
        "article_norms": article_norms(article, ref),
        "topic": clean_text((twin or {}).get("trap") or item.get("topic") or ""),
        "prompt": clean_text(prompt),
        "answer": "X" if answer == "X" else "O",
        "explanation": clean_text((twin or {}).get("why") or item.get("why") or ""),
        "reference_text": ref,
        "corrected_prompt": clean_text(corrected),
        "grade": clean_text((twin or {}).get("grade") or item.get("grade") or ""),
        "weight": as_float((twin or {}).get("weight", item.get("weight", 0))),
        "freq": as_int((twin or {}).get("freq", item.get("freq", 1))),
        "tags": tags,
        "meta": {
            "source_round": item.get("sourceRound") or item.get("round"),
            "source_question": item.get("sourceQuestion"),
            "source_part": (twin or {}).get("sourcePart") or item.get("sourcePart"),
            "source_type": item.get("type"),
        },
    }


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def build_clat_rows(source_dir: Path) -> list[dict[str, Any]]:
    path = source_dir / "ox_clat_unified_v001.json"
    data = load_json(path)
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(data.get("items") or []):
        if item.get("subject") == "법조윤리":
            continue
        pid = clean_text(item.get("pid") or f"clat-{idx + 1}-{sha_pid(item.get('rep', ''))}")
        rep = clean_text(item.get("rep") or item.get("q"))
        if not rep:
            continue
        rows.append(
            make_row(
                bank="clat",
                source_pid=pid,
                variant="base",
                item=item,
                prompt=rep,
                answer="X" if item.get("a") == "X" or item.get("answer") == "X" else "O",
                corrected=rep if item.get("a") == "X" else "",
            )
        )
        for t_idx, twin in enumerate(item.get("twins") or [], start=1):
            trap = clean_text(twin.get("trap"))
            prompt = clean_text(twin.get("q"))
            if not trap or trap in {"-", "—", "없음"} or not prompt or prompt == rep:
                continue
            rows.append(
                make_row(
                    bank="clat",
                    source_pid=pid,
                    variant=f"twin{t_idx}",
                    item=item,
                    prompt=prompt,
                    answer="X",
                    corrected=clean_text(twin.get("corrected") or twin.get("rep") or rep),
                    twin=twin,
                )
            )
    return rows


def build_ethics_rows(source_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for round_no in range(1, 16):
        path = source_dir / f"ox_legal_ethics_exam{round_no}.json"
        if not path.exists():
            continue
        data = load_json(path)
        for idx, item in enumerate(data.get("items") or []):
            pid = clean_text(item.get("pid") or f"ethics-{round_no}-{idx + 1}-{sha_pid(item.get('rep', ''))}")
            rep = clean_text(item.get("rep"))
            if not rep:
                continue
            rows.append(
                make_row(
                    bank="ethics",
                    source_pid=pid,
                    variant="base",
                    item=item,
                    prompt=rep,
                    answer="O",
                )
            )
            for t_idx, twin in enumerate(item.get("twins") or [], start=1):
                prompt = clean_text(twin.get("q"))
                if not prompt or prompt == rep:
                    continue
                rows.append(
                    make_row(
                        bank="ethics",
                        source_pid=pid,
                        variant=f"twin{t_idx}",
                        item=item,
                        prompt=prompt,
                        answer="X",
                        corrected=clean_text(twin.get("corrected") or rep),
                        twin=twin,
                    )
                )
    return rows


def write_chunks(rows: list[dict[str, Any]], out_dir: Path, chunk_size: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    header = """-- Local-only private game-bank import.
-- Run supabase_private_game_bank.sql before these files.
-- Do not commit this file.

"""
    reset = "update public.private_game_questions set active = false where bank in ('clat', 'ethics');\n\n"
    columns = """insert into public.private_game_questions
(bank, source_pid, source_variant, subject, law_name, article, article_norms, topic,
 prompt, answer, explanation, reference_text, corrected_prompt, grade, weight, freq,
 tags, meta, active)
values
"""
    footer = """
on conflict (bank, source_pid, source_variant) do update set
  subject = excluded.subject,
  law_name = excluded.law_name,
  article = excluded.article,
  article_norms = excluded.article_norms,
  topic = excluded.topic,
  prompt = excluded.prompt,
  answer = excluded.answer,
  explanation = excluded.explanation,
  reference_text = excluded.reference_text,
  corrected_prompt = excluded.corrected_prompt,
  grade = excluded.grade,
  weight = excluded.weight,
  freq = excluded.freq,
  tags = excluded.tags,
  meta = excluded.meta,
  active = true,
  updated_at = now();
"""
    for old in out_dir.glob("private_game_questions_*.local.sql"):
        old.unlink()
    total = len(rows)
    for start in range(0, total, chunk_size):
        chunk = rows[start : start + chunk_size]
        idx = start // chunk_size + 1
        path = out_dir / f"private_game_questions_{idx:03d}.local.sql"
        body = columns + ",\n".join(row_sql(row) for row in chunk) + footer
        prefix = header
        if idx == 1:
            prefix += reset
        path.write_text(prefix + body, encoding="utf-8")
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "rows": total,
        "chunks": (total + chunk_size - 1) // chunk_size,
        "chunk_size": chunk_size,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--chunk-size", type=int, default=450)
    args = parser.parse_args()

    source_dir = args.source.resolve()
    rows = build_clat_rows(source_dir) + build_ethics_rows(source_dir)
    rows = [row for row in rows if row["prompt"] and row["answer"] in {"O", "X"}]
    write_chunks(rows, args.out.resolve(), max(50, args.chunk_size))
    print(f"source={source_dir}")
    print(f"out={args.out.resolve()}")
    print(f"rows={len(rows)}")


if __name__ == "__main__":
    main()
