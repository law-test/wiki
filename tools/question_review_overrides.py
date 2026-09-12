#!/usr/bin/env python3
"""Apply reviewed question corrections after final source-key disambiguation.

Registry schema: {version: 1, reviewed_at: ISO date/time, overrides: [...]}.
Each override requires bank, source_pid, source_variant, expected_prompt,
report_id and resolution, plus at least one field in PATCH_FIELDS. Strings are
matched exactly; a key whose prompt has drifted is never corrected by guesswork.

This module does not connect to a database. generate_review_sql() produces a
reviewable transaction; it never executes it. Full-import callers must preserve
the returned active field in both INSERT values and conflict updates.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "reports" / "question_review_overrides_20260913.json"
KEY_FIELDS = ("bank", "source_pid", "source_variant")
PATCH_FIELDS = ("prompt", "answer", "explanation", "reference_text", "corrected_prompt", "tags", "active")
REQUIRED_FIELDS = (*KEY_FIELDS, "expected_prompt", "report_id", "resolution")
BANKS = frozenset({"clat", "ethics"})


class ReviewOverrideError(ValueError):
    """Unsafe or ambiguous correction input; no partial output is returned."""


def _text(value: Any, name: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ReviewOverrideError(f"{name} must be {'a' if empty else 'a nonempty'} string")
    if "\x00" in value or any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise ReviewOverrideError(f"{name} contains an invalid Unicode character")
    return value


def _key(row: dict[str, Any]) -> tuple[str, str, str]:
    values = tuple(_text(row.get(name), name) for name in KEY_FIELDS)
    if values[0] not in BANKS:
        raise ReviewOverrideError(f"Unknown question bank: {values[0]}")
    return values


def validate_registry(registry: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(registry, dict) or set(registry) != {"version", "reviewed_at", "overrides"}:
        raise ReviewOverrideError("Registry requires exactly version, reviewed_at and overrides")
    if type(registry["version"]) is not int or registry["version"] != 1:
        raise ReviewOverrideError("Only registry version 1 is supported")
    reviewed_at = _text(registry["reviewed_at"], "reviewed_at")
    try:
        if len(reviewed_at) == 10:
            date.fromisoformat(reviewed_at)
        else:
            datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewOverrideError("reviewed_at must be an ISO date or datetime") from exc
    overrides = registry["overrides"]
    if not isinstance(overrides, list):
        raise ReviewOverrideError("overrides must be an array")
    seen = set()
    allowed = set(REQUIRED_FIELDS) | set(PATCH_FIELDS)
    for index, override in enumerate(overrides):
        if not isinstance(override, dict):
            raise ReviewOverrideError(f"Override {index} must be an object")
        missing = set(REQUIRED_FIELDS) - set(override)
        unknown = set(override) - allowed
        if missing or unknown:
            raise ReviewOverrideError(f"Override {index}: missing fields {sorted(missing)}; unknown fields {sorted(unknown)}")
        key = _key(override)
        if key in seen:
            raise ReviewOverrideError(f"Duplicate override key: {key}")
        seen.add(key)
        _text(override["expected_prompt"], "expected_prompt")
        _text(override["resolution"], "resolution")
        report_id = override["report_id"]
        if type(report_id) is int:
            if report_id <= 0:
                raise ReviewOverrideError("report_id must be positive")
        else:
            _text(report_id, "report_id")
        if not any(field in override for field in PATCH_FIELDS):
            raise ReviewOverrideError(f"Override {key} contains no correction")
        for field in PATCH_FIELDS:
            if field not in override:
                continue
            value = override[field]
            if field == "active":
                if type(value) is not bool:
                    raise ReviewOverrideError("active must be a JSON boolean")
            else:
                _text(value, field, empty=field not in {"prompt", "answer"})
                if field == "answer" and value not in {"O", "X"}:
                    raise ReviewOverrideError("answer must be O or X")
    return deepcopy(registry)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReviewOverrideError(f"Duplicate JSON object member: {key}")
        result[key] = value
    return result


def load_registry(path: Path | str = DEFAULT_REGISTRY) -> dict[str, Any]:
    # A missing registry must not silently re-enable a withdrawn question.
    with Path(path).open(encoding="utf-8-sig") as stream:
        return validate_registry(json.load(stream, object_pairs_hook=_unique_json_object))


def _selected(registry: dict[str, Any], banks: Iterable[str] | None) -> list[dict[str, Any]]:
    selected = BANKS if banks is None else frozenset(banks)
    if not selected or selected - BANKS:
        raise ReviewOverrideError("banks must select clat, ethics or both")
    return [entry for entry in registry["overrides"] if entry["bank"] in selected]


def _audit(registry: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": registry["version"],
        "reviewed_at": registry["reviewed_at"],
        "report_id": override["report_id"],
        "resolution": override["resolution"],
    }


def apply_reviewed_overrides(
    rows: Iterable[dict[str, Any]], registry: dict[str, Any], *, banks: Iterable[str] | None = None
) -> list[dict[str, Any]]:
    """Return independent final rows, or raise before returning any partial work.

    Call after key disambiguation and filtering, before output serialization or
    any upload/reset operation. A bank-scoped import only requires that bank's
    registered targets. Duplicate final source keys always fail, even when their
    text is identical. Existing active=False values are preserved.
    """
    checked = validate_registry(registry)
    selected_banks = None if banks is None else frozenset(banks)
    selected = _selected(checked, selected_banks)
    result = deepcopy(list(rows))
    by_key = {}
    for index, row in enumerate(result):
        if not isinstance(row, dict):
            raise ReviewOverrideError(f"Source row {index} must be an object")
        key = _key(row)
        if selected_banks is not None and key[0] not in selected_banks:
            raise ReviewOverrideError(f"Source row outside selected banks: {key}")
        if key in by_key:
            raise ReviewOverrideError(f"Duplicate final source key: {key}")
        _text(row.get("prompt"), "source prompt")
        if row.get("answer") not in {"O", "X"}:
            raise ReviewOverrideError(f"Invalid source answer: {key}")
        if "active" in row and type(row["active"]) is not bool:
            raise ReviewOverrideError(f"Invalid source active value: {key}")
        if "meta" in row and not isinstance(row["meta"], dict):
            raise ReviewOverrideError(f"Source meta must be an object: {key}")
        row.setdefault("active", True)
        by_key[key] = row
    # Validate every target before applying any patch, including retirements.
    for entry in selected:
        key = _key(entry)
        row = by_key.get(key)
        if row is None:
            raise ReviewOverrideError(f"Reviewed target missing from final source rows: {key}")
        allowed_prompts = {entry["expected_prompt"], entry.get("prompt", entry["expected_prompt"])}
        if row["prompt"] not in allowed_prompts:
            raise ReviewOverrideError(f"Reviewed target prompt drifted: {key}")
    for entry in selected:
        row = by_key[_key(entry)]
        row.update({field: entry[field] for field in PATCH_FIELDS if field in entry})
        row.setdefault("meta", {})["question_review"] = _audit(checked, entry)
    return result


def _sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def generate_review_sql(registry: dict[str, Any], *, banks: Iterable[str] | None = None) -> str:
    """Create an atomic, guarded PostgreSQL correction transaction; never run it.

    STRICT row lookup aborts on a missing or duplicate key. Exact prompt guards
    also accept the corrected prompt on repeat execution. Already-correct rows
    are not updated, so their updated_at values remain unchanged on reruns.
    """
    checked = validate_registry(registry)
    selected = _selected(checked, banks)
    statements = []
    for entry in selected:
        predicate = " AND ".join(f"{field} = {_sql_text(entry[field])}" for field in KEY_FIELDS)
        label = _sql_text(" / ".join(_key(entry)))
        expected = _sql_text(entry["expected_prompt"])
        replacement = _sql_text(entry.get("prompt", entry["expected_prompt"]))
        audit = _sql_text(json.dumps(_audit(checked, entry), ensure_ascii=False, sort_keys=True, separators=(",", ":"))) + "::jsonb"
        assignments = []
        conditions = []
        for field in PATCH_FIELDS:
            if field not in entry:
                continue
            value = ("true" if entry[field] else "false") if field == "active" else _sql_text(entry[field])
            assignments.append(f"{field} = {value}")
            conditions.append(f"{field} IS DISTINCT FROM {value}")
        metadata = f"coalesce(meta, '{{}}'::jsonb) || jsonb_build_object('question_review', {audit})"
        assignments.extend([f"meta = {metadata}", "updated_at = now()"])
        conditions.append(f"meta IS DISTINCT FROM ({metadata})")
        statements.append(f"""  BEGIN
    SELECT prompt, meta INTO STRICT current_prompt, current_meta
      FROM public.private_game_questions WHERE {predicate} FOR UPDATE;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN RAISE EXCEPTION 'Reviewed question missing: %', {label};
    WHEN TOO_MANY_ROWS THEN RAISE EXCEPTION 'Duplicate reviewed question: %', {label};
  END;
  IF current_prompt IS DISTINCT FROM {expected} AND current_prompt IS DISTINCT FROM {replacement} THEN
    RAISE EXCEPTION 'Reviewed question prompt drifted: %', {label};
  END IF;
  IF current_meta IS NOT NULL AND jsonb_typeof(current_meta) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'Reviewed question meta is not an object: %', {label};
  END IF;
  UPDATE public.private_game_questions
    SET {', '.join(assignments)}
    WHERE {predicate} AND ({' OR '.join(conditions)});""")
    body = "DECLARE\n  current_prompt text;\n  current_meta jsonb;\nBEGIN\n" + ("\n".join(statements) if statements else "  NULL;") + "\nEND;"
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    delimiter = f"$review_{digest}$"
    while delimiter in body:
        delimiter = delimiter[:-1] + "x$"
    return (
        "-- Reviewed question corrections. Review locally before authorized execution.\n"
        "BEGIN;\nSET LOCAL standard_conforming_strings = on;\n"
        f"DO {delimiter}\n{body}\n{delimiter};\nCOMMIT;\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--bank", choices=["all", "clat", "ethics"], default="all")
    parser.add_argument("--sql-out", type=Path, required=True, help="Local SQL output only; no database connection")
    args = parser.parse_args()
    banks = BANKS if args.bank == "all" else {args.bank}
    sql = generate_review_sql(load_registry(args.registry), banks=banks)
    args.sql_out.parent.mkdir(parents=True, exist_ok=True)
    args.sql_out.write_text(sql, encoding="utf-8")
    print(f"sql_out={args.sql_out.resolve()}")


if __name__ == "__main__":
    main()
