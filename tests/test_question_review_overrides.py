"""Offline tests: synthetic questions only, no private sources or database."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from question_review_overrides import (  # noqa: E402
    ReviewOverrideError,
    apply_reviewed_overrides,
    generate_review_sql,
    load_registry,
    validate_registry,
)


def row(pid="sample-1", **values):
    return {
        "bank": "clat", "source_pid": pid, "source_variant": "base",
        "prompt": "검수 전 테스트 문항", "answer": "X", "active": True,
        "explanation": "기존 해설", "reference_text": "기존 근거",
        "corrected_prompt": "기존 정정문", "tags": "기존 태그",
        "meta": {"preserved": "기존 메타데이터"}, **values,
    }


def entry(pid="sample-1", **values):
    return {
        "bank": "clat", "source_pid": pid, "source_variant": "base",
        "expected_prompt": "검수 전 테스트 문항", "prompt": "검수 후 테스트 문항",
        "answer": "O", "corrected_prompt": "", "report_id": 101,
        "resolution": "테스트용 검수 수정", **values,
    }


def registry(*entries):
    return {"version": 1, "reviewed_at": "2026-09-13", "overrides": list(entries or [entry()])}


class OverrideTests(unittest.TestCase):
    def test_correction_is_idempotent_and_preserves_unspecified_data(self):
        source = [row(), row("untouched", active=False)]
        before = deepcopy(source)
        result = apply_reviewed_overrides(source, registry())
        self.assertEqual(source, before)
        self.assertEqual(result[0]["prompt"], "검수 후 테스트 문항")
        self.assertEqual(result[0]["answer"], "O")
        self.assertEqual(result[0]["corrected_prompt"], "")
        self.assertEqual(result[0]["explanation"], "기존 해설")
        self.assertEqual(result[0]["meta"]["preserved"], "기존 메타데이터")
        self.assertEqual(result[0]["meta"]["question_review"]["report_id"], 101)
        self.assertFalse(result[1]["active"])
        self.assertEqual(apply_reviewed_overrides(result, registry()), result)

    def test_deactivation_only_is_supported_and_repeatable(self):
        correction = entry(active=False)
        for field in ("prompt", "answer", "corrected_prompt"):
            correction.pop(field)
        result = apply_reviewed_overrides([row()], registry(correction))
        self.assertFalse(result[0]["active"])
        self.assertEqual(result[0]["prompt"], row()["prompt"])
        self.assertEqual(apply_reviewed_overrides(result, registry(correction)), result)

    def test_missing_key_fails_even_for_deactivation(self):
        with self.assertRaisesRegex(ReviewOverrideError, "missing"):
            apply_reviewed_overrides([row("other")], registry(entry(active=False)))

    def test_unexpected_prompt_fails_without_partial_mutation(self):
        rows = [row(), row("sample-2", prompt="새로 변경된 미검수 원문")]
        before = deepcopy(rows)
        with self.assertRaisesRegex(ReviewOverrideError, "drifted"):
            apply_reviewed_overrides(rows, registry(entry(), entry("sample-2")))
        self.assertEqual(rows, before)

    def test_prompt_matching_is_exact(self):
        with self.assertRaisesRegex(ReviewOverrideError, "drifted"):
            apply_reviewed_overrides([row(prompt="검수 전  테스트 문항")], registry())

    def test_duplicate_final_keys_fail_even_when_identical(self):
        with self.assertRaisesRegex(ReviewOverrideError, "Duplicate final"):
            apply_reviewed_overrides([row(), row()], registry())

    def test_duplicate_registry_keys_fail(self):
        with self.assertRaisesRegex(ReviewOverrideError, "Duplicate override"):
            apply_reviewed_overrides([row()], registry(entry(), entry(answer="X")))

    def test_source_variant_is_part_of_identity(self):
        with self.assertRaisesRegex(ReviewOverrideError, "missing"):
            apply_reviewed_overrides([row(source_variant="twin1")], registry())

    def test_bank_scoped_import_does_not_require_other_bank_rows(self):
        reviewed = registry(entry(), entry("ethics-1", bank="ethics"))
        result = apply_reviewed_overrides([row()], reviewed, banks={"clat"})
        self.assertEqual(result[0]["answer"], "O")
        with self.assertRaisesRegex(ReviewOverrideError, "missing"):
            apply_reviewed_overrides([row()], reviewed)
        with self.assertRaisesRegex(ReviewOverrideError, "outside selected"):
            apply_reviewed_overrides([row(bank="ethics")], reviewed, banks={"clat"})

    def test_registry_types_fail_closed(self):
        invalid = [entry(active="false"), entry(answer="Y"), entry(tags=["태그"]), entry(report_id=True), entry(prompt=""), entry(unreviewed=True)]
        for correction in invalid:
            with self.subTest(correction=correction), self.assertRaises(ReviewOverrideError):
                validate_registry(registry(correction))
        for value in ["v1", True, 2]:
            data = registry(); data["version"] = value
            with self.assertRaises(ReviewOverrideError):
                validate_registry(data)

    def test_registry_cannot_omit_provenance_or_patch(self):
        for field in ["report_id", "resolution", "expected_prompt", "source_variant"]:
            correction = entry(); correction.pop(field)
            with self.assertRaises(ReviewOverrideError):
                validate_registry(registry(correction))
        correction = entry()
        for field in ["prompt", "answer", "corrected_prompt"]:
            correction.pop(field)
        with self.assertRaisesRegex(ReviewOverrideError, "no correction"):
            validate_registry(registry(correction))

    def test_meta_and_active_source_corruption_fail(self):
        for source in [row(meta=[]), row(active="false"), row(answer="maybe")]:
            with self.assertRaises(ReviewOverrideError):
                apply_reviewed_overrides([source], registry())

    def test_load_registry_rejects_duplicate_json_members_and_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            with self.assertRaises(FileNotFoundError):
                load_registry(path)
            path.write_text('{"version":1,"version":1,"reviewed_at":"2026-09-13","overrides":[]}', encoding="utf-8")
            with self.assertRaisesRegex(ReviewOverrideError, "Duplicate JSON"):
                load_registry(path)
            path.write_text(json.dumps(registry(), ensure_ascii=False), encoding="utf-8-sig")
            self.assertEqual(load_registry(path), registry())

    def test_valid_review_datetime_and_string_report_id(self):
        data = registry(entry(report_id="report-101")); data["reviewed_at"] = "2026-09-13T12:00:00+09:00"
        self.assertEqual(validate_registry(data), data)
        data["reviewed_at"] = "2026-02-31"
        with self.assertRaises(ReviewOverrideError):
            validate_registry(data)

    def test_empty_registry_preserves_rows_and_defaults_active(self):
        data = {"version": 1, "reviewed_at": "2026-09-13", "overrides": []}
        source = row(); source.pop("active")
        result = apply_reviewed_overrides([source], data)
        self.assertTrue(result[0]["active"])
        self.assertNotIn("active", source)


class SqlGenerationTests(unittest.TestCase):
    def test_sql_is_guarded_atomic_and_avoids_rewriting_identical_rows(self):
        sql = generate_review_sql(registry(entry(active=False)))
        self.assertIn("BEGIN;\nSET LOCAL standard_conforming_strings = on;", sql)
        self.assertIn("INTO STRICT current_prompt, current_meta", sql)
        self.assertIn("FOR UPDATE", sql)
        self.assertIn("WHEN NO_DATA_FOUND", sql)
        self.assertIn("WHEN TOO_MANY_ROWS", sql)
        self.assertIn("current_prompt IS DISTINCT FROM '검수 전 테스트 문항' AND current_prompt IS DISTINCT FROM '검수 후 테스트 문항'", sql)
        self.assertIn("active = false", sql)
        self.assertIn("prompt IS DISTINCT FROM '검수 후 테스트 문항'", sql)
        self.assertTrue(sql.endswith("COMMIT;\n"))
        self.assertEqual(sql, generate_review_sql(registry(entry(active=False))))

    def test_sql_quotes_untrusted_text_and_uses_noncolliding_body_delimiter(self):
        text = "문장 ' 인용 \\ 경로\n$question_review$; DROP TABLE test; --"
        sql = generate_review_sql(registry(entry(prompt=text)))
        self.assertIn("문장 '' 인용 \\ 경로", sql)
        delimiter = next(line for line in sql.splitlines() if line.startswith("DO "))[3:]
        self.assertEqual(sql.count(delimiter), 2)
        with self.assertRaises(ReviewOverrideError):
            generate_review_sql(registry(entry(prompt="문장\x00")))

    def test_sql_bank_scope_and_empty_registry(self):
        data = registry(entry(), entry("ethics-1", bank="ethics"))
        sql = generate_review_sql(data, banks={"clat"})
        self.assertNotIn("ethics-1", sql)
        data["overrides"] = []
        self.assertIn("  NULL;", generate_review_sql(data))


class ImportIntegrationTests(unittest.TestCase):
    @staticmethod
    def load_tool(name):
        spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def fixture(self, directory):
        root = Path(directory)
        source = root / "source"; source.mkdir()
        source.joinpath("ox_clat_unified_v001.json").write_text(json.dumps({"items": [{
            "pid": "sample-1", "rep": "검수 전 테스트 문항", "a": "X", "subject": "민법", "why": "기존 해설"
        }]}, ensure_ascii=False), encoding="utf-8")
        reviewed = root / "reviews.json"
        reviewed.write_text(json.dumps(registry(entry(active=False)), ensure_ascii=False), encoding="utf-8")
        return root, source, reviewed

    def test_sql_import_preserves_retirement_in_values_and_conflict_update(self):
        builder = self.load_tool("build_private_game_bank_import")
        with tempfile.TemporaryDirectory() as directory:
            root, source, reviewed = self.fixture(directory)
            rows = builder.disambiguate_rows(builder.build_clat_rows(source))
            rows = builder.apply_final_reviews(rows, reviewed)
            self.assertFalse(rows[0]["active"])
            self.assertEqual(rows[0]["prompt"], "검수 후 테스트 문항")
            self.assertTrue(builder.row_sql(rows[0]).endswith(",false)"))
            builder.write_chunks(rows, root / "sql", 10)
            sql = (root / "sql" / "private_game_questions_001.local.sql").read_text(encoding="utf-8")
            self.assertIn("active = excluded.active", sql)
            self.assertNotIn("active = true", sql)

    def test_rest_build_applies_reviews_without_any_network(self):
        uploader = self.load_tool("upload_private_game_bank_rest")
        with tempfile.TemporaryDirectory() as directory, patch("urllib.request.urlopen", side_effect=AssertionError("Network forbidden")):
            _, source, reviewed = self.fixture(directory)
            result = uploader.build_rows(source, {"clat"}, reviewed)
            self.assertFalse(result[0]["active"])
            self.assertEqual(result[0]["answer"], "O")
            self.assertEqual(result[0]["meta"]["question_review"]["report_id"], 101)

    def test_missing_registry_stops_rest_before_reset_or_upload(self):
        uploader = self.load_tool("upload_private_game_bank_rest")
        with tempfile.TemporaryDirectory() as directory:
            root, source, _ = self.fixture(directory)
            with patch.object(uploader, "upload_rows") as upload, patch.object(uploader, "env_key") as key:
                with patch.object(sys, "argv", ["upload", "--source", str(source), "--review-overrides", str(root / "missing.json")]):
                    with self.assertRaises(FileNotFoundError):
                        uploader.main()
                upload.assert_not_called(); key.assert_not_called()


if __name__ == "__main__":
    unittest.main()
