#!/usr/bin/env python3
"""Replace one mock-exam contribution inside the private CLAT bank.

Use this after rebuilding a mock-year atom file that was previously merged
partially.  It removes the old private source occurrences for that mock year
from the current CLAT JSON, then merges the rebuilt atom payload.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PRIVATE_ROOT = Path(r"C:\cowork\lawinus.org\02_비공개데이터\private_problem_banks")
DEFAULT_CURRENT = PRIVATE_ROOT / "current" / "ox_clat_unified_v001.json"


def load_mock_builder():
    path = Path(__file__).with_name("build_mock_expected_atoms.py")
    spec = importlib.util.spec_from_file_location("build_mock_expected_atoms", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_matches(source: dict[str, Any], exam_year: int, public_label: str | None) -> bool:
    if source.get("examYear") != exam_year:
        return False
    if not public_label:
        return True
    return source.get("publicLabel") == public_label or source.get("mockPublicLabel") == public_label


def dedupe_keep_order(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    out: list[Any] = []
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def remove_target_sources(
    item: dict[str, Any],
    *,
    exam_year: int,
    public_label: str | None,
) -> tuple[bool, int, set[str]]:
    private_sources = list(item.get("privateSources") or [])
    kept_sources: list[dict[str, Any]] = []
    removed_sources: list[dict[str, Any]] = []
    for source in private_sources:
        if source_matches(source, exam_year, public_label):
            removed_sources.append(source)
        else:
            kept_sources.append(source)

    if not removed_sources:
        return False, 0, set()

    removed_labels = {
        str(source.get("publicLabel") or source.get("mockPublicLabel") or "")
        for source in removed_sources
        if source.get("publicLabel") or source.get("mockPublicLabel")
    }
    if public_label:
        removed_labels.add(public_label)

    item["privateSources"] = kept_sources
    item["freq"] = max(0, int(item.get("freq") or 1) - len(removed_sources))

    for key in ("years", "src"):
        values = list(item.get(key) or [])
        item[key] = dedupe_keep_order([value for value in values if str(value) not in removed_labels])

    item["articleRefs"] = dedupe_keep_order(list(item.get("articleRefs") or []))
    return True, len(removed_sources), removed_labels


def has_visible_source(item: dict[str, Any]) -> bool:
    if int(item.get("freq") or 0) > 0:
        return True
    if item.get("privateSources"):
        return True
    if item.get("years") or item.get("src"):
        return True
    return False


def normalize_current_metadata(current: dict[str, Any]) -> None:
    items = list(current.get("items") or [])
    current["items"] = items
    current["count"] = len(items)
    current["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    current["subjects"] = dict(Counter(str(item.get("subject") or "") for item in items if item.get("subject")))
    current["answers"] = dict(Counter(str(item.get("a") or "") for item in items if item.get("a")))
    current["layers"] = dict(Counter(str(item.get("sourceLayer") or "unknown") for item in items))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-clat", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument("--atoms", type=Path, required=True)
    parser.add_argument("--exam-year", type=int, required=True)
    parser.add_argument("--public-label")
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    builder = load_mock_builder()
    current = load_json(args.current_clat)
    atom_payload = load_json(args.atoms)
    incoming_atoms = list(atom_payload.get("items") or [])

    original_items = list(current.get("items") or [])
    kept_items: list[dict[str, Any]] = []
    removed_source_count = 0
    touched_items = 0
    dropped_items = 0

    for item in original_items:
        changed, removed_count, _labels = remove_target_sources(
            item,
            exam_year=args.exam_year,
            public_label=args.public_label,
        )
        if changed:
            touched_items += 1
            removed_source_count += removed_count
        if has_visible_source(item):
            kept_items.append(item)
        else:
            dropped_items += 1

    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    similarity_index: dict[tuple[str, str], dict[str, list[tuple[dict[str, Any], str, set[str]]]]] = {}
    for item in kept_items:
        index[builder.atom_key(item)] = item
        builder.add_similarity_index(similarity_index, item)

    added = 0
    merged = 0
    near_merged = 0
    for atom in incoming_atoms:
        key = builder.atom_key(atom)
        if key in index:
            builder.merge_atom(index[key], atom)
            merged += 1
        else:
            similar = builder.find_similar_atom(similarity_index, atom)
            if similar is not None:
                builder.merge_atom(similar, atom)
                merged += 1
                near_merged += 1
            else:
                kept_items.append(atom)
                index[key] = atom
                builder.add_similarity_index(similarity_index, atom)
                added += 1

    current["items"] = kept_items
    normalize_current_metadata(current)

    report = {
        "current": str(args.current_clat),
        "atoms": str(args.atoms),
        "examYear": args.exam_year,
        "publicLabel": args.public_label,
        "originalItems": len(original_items),
        "touchedItems": touched_items,
        "removedPrivateSources": removed_source_count,
        "droppedItems": dropped_items,
        "incomingAtoms": len(incoming_atoms),
        "added": added,
        "merged": merged,
        "nearMerged": near_merged,
        "finalItems": len(kept_items),
        "dryRun": args.dry_run,
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.dry_run:
        return

    if not args.no_backup:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = args.current_clat.with_name(args.current_clat.stem + f".replace_mock_backup_{stamp}" + args.current_clat.suffix)
        shutil.copy2(args.current_clat, backup)
        print(f"backup={backup}")
    write_json(args.current_clat, current)


if __name__ == "__main__":
    main()
