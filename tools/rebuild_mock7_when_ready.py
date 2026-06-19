#!/usr/bin/env python3
"""Rebuild and replace the 2017 mock-exam CLAT atoms when the missing file exists.

The 2017 first-round civil-law choice question paper is currently missing.
Run this script after placing that HWP/HWPX/PDF into the 2017 first-round
민사법 folder.  It rebuilds mock7 source JSON, rebuilds mock7 atoms, replaces
the old partial mock7 contribution in the current CLAT bank, and optionally
uploads CLAT rows to Supabase.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


PYTHON = Path(r"C:\Users\HOME\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe")
REPO_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = Path(r"C:\cowork\law-test-private\private_problem_banks")
DEFAULT_SOURCE_ROOT = (
    Path(r"C:\cowork\변호사시험_2026_06_15")
    / "ALL 모의고사문제+채점기준표 (2)"
    / "2017학년도 변시 모의"
)
DEFAULT_CURRENT_CLAT = PRIVATE_ROOT / "current" / "ox_clat_unified_v001.json"
MOCK_DIR = PRIVATE_ROOT / "mock7"
SOURCE_JSON = MOCK_DIR / "mock7_2017_choice_sources_v001.json"
ATOM_JSON = MOCK_DIR / "ox_mock7_2017_expected_atoms_v001.json"
PUBLIC_LABEL = "변호사시험 7회 예상"


def python_executable() -> Path:
    return PYTHON if PYTHON.exists() else Path(sys.executable)


def run(args: list[str], *, dry_run: bool = False, env: dict[str, str] | None = None) -> None:
    print(" ".join(args))
    if dry_run:
        return
    subprocess.run(args, cwd=REPO_ROOT, check=True, env=env)


def find_first_round_civil_dir(source_root: Path) -> Path:
    round_dirs = sorted(path for path in source_root.iterdir() if path.is_dir() and "2017 법전협 1차 모의고사" in path.name)
    if len(round_dirs) != 1:
        names = ", ".join(path.name for path in round_dirs) or "none"
        raise SystemExit(f"2017 first-round folder not found cleanly: {names}")
    civil_dirs = sorted(path for path in round_dirs[0].iterdir() if path.is_dir() and "민사법" in path.name)
    if len(civil_dirs) != 1:
        names = ", ".join(path.name for path in civil_dirs) or "none"
        raise SystemExit(f"2017 first-round civil-law folder not found cleanly: {names}")
    return civil_dirs[0]


def has_missing_question_file(civil_dir: Path) -> bool:
    candidates = []
    for path in civil_dir.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        if "선택형" not in name or "문제" not in name:
            continue
        if "사례형" in name or "기록형" in name or "채점" in name or "정답" in name or name.endswith(".txt"):
            continue
        if path.suffix.lower() not in {".hwp", ".hwpx", ".pdf"}:
            continue
        candidates.append(path)
    if candidates:
        print("found missing question candidate:")
        for path in candidates:
            print(f"- {path}")
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--current-clat", type=Path, default=DEFAULT_CURRENT_CLAT)
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    current_clat = args.current_clat.resolve()
    if not source_root.exists():
        raise SystemExit(f"source root not found: {source_root}")
    if not current_clat.exists():
        raise SystemExit(f"current CLAT not found: {current_clat}")

    civil_dir = find_first_round_civil_dir(source_root)
    if not has_missing_question_file(civil_dir):
        raise SystemExit(
            "missing file is still absent. Put the 2017 first-round civil-law choice question paper into:\n"
            f"{civil_dir}"
        )
    if args.check_only:
        print("ready: missing 2017 first-round civil-law choice question paper is present.")
        return

    py = str(python_executable())
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    run(
        [
            py,
            str(REPO_ROOT / "tools" / "build_mock15_choice_sources.py"),
            "--source-root",
            str(source_root),
            "--out",
            str(SOURCE_JSON),
            "--exam-year",
            "2017",
            "--bar-round",
            "7",
            "--public-label",
            PUBLIC_LABEL,
        ],
        dry_run=args.dry_run,
        env=env,
    )

    run(
        [
            py,
            str(REPO_ROOT / "tools" / "build_mock_expected_atoms.py"),
            "--source",
            str(SOURCE_JSON),
            "--out",
            str(MOCK_DIR),
            "--current-clat",
            str(current_clat),
            "--public-label",
            PUBLIC_LABEL,
            "--id-prefix",
            "mock7",
            "--mock-year",
            "2017",
            "--output-prefix",
            "ox_mock7_2017_expected_atoms",
            "--version",
            "mock7-expected-v001",
        ],
        dry_run=args.dry_run,
        env=env,
    )

    run(
        [
            py,
            str(REPO_ROOT / "tools" / "replace_mock_atoms_in_current.py"),
            "--current-clat",
            str(current_clat),
            "--atoms",
            str(ATOM_JSON),
            "--exam-year",
            "2017",
            "--public-label",
            PUBLIC_LABEL,
        ],
        dry_run=args.dry_run,
        env=env,
    )

    if args.upload:
        run(
            [
                py,
                str(REPO_ROOT / "tools" / "upload_private_game_bank_rest.py"),
                "--source",
                str(PRIVATE_ROOT / "current"),
                "--bank",
                "clat",
            ],
            dry_run=args.dry_run,
            env=env,
        )

    print("done")


if __name__ == "__main__":
    main()
