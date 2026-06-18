#!/usr/bin/env python3
"""Upload private game-bank rows to Supabase through the REST API.

Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY or LAW_TEST_SUPABASE_KEY.
The script intentionally keeps mock source-month/question metadata out of
uploaded rows by reusing build_private_game_bank_import.py's row builder.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from urllib import error, parse, request


DEFAULT_SOURCE = Path(r"C:\cowork\law-test-private\private_problem_banks\current")
DEFAULT_URL = "https://vtqbyznczhgkpylczxpe.supabase.co"
ROW_COLUMNS = {
    "bank",
    "source_pid",
    "source_variant",
    "subject",
    "law_name",
    "article",
    "article_norms",
    "topic",
    "prompt",
    "answer",
    "explanation",
    "reference_text",
    "corrected_prompt",
    "grade",
    "weight",
    "freq",
    "tags",
    "meta",
    "active",
}


def load_import_module():
    path = Path(__file__).with_name("build_private_game_bank_import.py")
    spec = importlib.util.spec_from_file_location("private_game_bank_import", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def env_key() -> str:
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("LAW_TEST_SUPABASE_KEY")
    if not key:
        raise SystemExit("SUPABASE_SERVICE_ROLE_KEY or LAW_TEST_SUPABASE_KEY is required.")
    return key


def api_request(url: str, key: str, method: str, path: str, payload=None, prefer: str | None = None):
    body = None
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = request.Request(url.rstrip("/") + path, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=120) as res:
            text = res.read().decode("utf-8")
            return res.status, text
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Supabase API failed {exc.code} {exc.reason}: {detail}") from exc


def api_request_headers(
    url: str,
    key: str,
    method: str,
    path: str,
    payload=None,
    prefer: str | None = None,
    extra_headers: dict[str, str] | None = None,
):
    body = None
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    if extra_headers:
        headers.update(extra_headers)
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = request.Request(url.rstrip("/") + path, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=120) as res:
            return res.status, res.read().decode("utf-8"), dict(res.headers)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Supabase API failed {exc.code} {exc.reason}: {detail}") from exc


def build_rows(source: Path, banks: set[str]) -> list[dict]:
    bank = load_import_module()
    rows: list[dict] = []
    if "clat" in banks:
        rows.extend(bank.build_clat_rows(source))
    if "ethics" in banks:
        rows.extend(bank.build_ethics_rows(source))
    clean_rows = []
    for row in rows:
        if not row.get("prompt") or row.get("answer") not in {"O", "X"}:
            continue
        out = {key: row.get(key) for key in ROW_COLUMNS if key in row}
        out["active"] = True
        clean_rows.append(out)
    return bank.disambiguate_rows(clean_rows)


def chunks(rows: list[dict], size: int):
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def upload_rows(url: str, key: str, rows: list[dict], banks: set[str], chunk_size: int) -> None:
    for bank in sorted(banks):
        encoded = parse.quote(f"eq.{bank}", safe="=.")
        api_request(url, key, "PATCH", f"/rest/v1/private_game_questions?bank={encoded}", {"active": False})
    total = len(rows)
    for idx, chunk in enumerate(chunks(rows, chunk_size), start=1):
        api_request(
            url,
            key,
            "POST",
            "/rest/v1/private_game_questions?on_conflict=bank,source_pid,source_variant",
            chunk,
            prefer="resolution=merge-duplicates,return=minimal",
        )
        print(f"uploaded {min(idx * chunk_size, total)}/{total}")


def count_active(url: str, key: str, bank: str) -> int:
    _, _, headers = api_request_headers(
        url,
        key,
        "GET",
        f"/rest/v1/private_game_questions?bank=eq.{parse.quote(bank)}&active=eq.true&select=source_pid",
        None,
        prefer="count=exact",
        extra_headers={"Range": "0-0"},
    )
    content_range = headers.get("Content-Range", "")
    if "/" in content_range:
        return int(content_range.rsplit("/", 1)[1])
    return -1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--url", default=os.environ.get("SUPABASE_URL", DEFAULT_URL))
    parser.add_argument("--bank", choices=["clat", "ethics", "all"], default="clat")
    parser.add_argument("--chunk-size", type=int, default=400)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    banks = {"clat", "ethics"} if args.bank == "all" else {args.bank}
    rows = build_rows(args.source.resolve(), banks)
    print(f"source={args.source.resolve()}")
    print(f"banks={','.join(sorted(banks))}")
    print(f"rows={len(rows)}")
    if args.dry_run:
        return
    key = env_key()
    upload_rows(args.url, key, rows, banks, max(50, args.chunk_size))
    for bank in sorted(banks):
        print(f"active_{bank}_sanity={count_active(args.url, key, bank)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
