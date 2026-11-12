"""Spec-0024 tests/eval/eval_support.py 白箱單元測試（全離線，資料於暫存目錄動態建立）。"""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from tests.eval.eval_support import (
    STATUS_LABELS,
    CountingEmbeddingService,
    RedisNamespace,
    candidate_ranking,
    check_isolation,
    classification_summary,
    confusion_matrix,
    load_jsonl,
    merge_usage,
    subsets_by,
    write_csv,
)

PROD = RedisNamespace("idx:resumes:v1", "resume:v1:chunk:", "resume:v1:hash:")


class ConfusionMatrixTests(unittest.TestCase):
    def test_hand_computed_example(self):
        pairs = [
            ("SUPPORTED", "SUPPORTED"),
            ("SUPPORTED", "NOT_MENTIONED"),
            ("CONTRADICTED", "CONTRADICTED"),
            ("NOT_MENTIONED", "SUPPORTED"),
            ("NOT_MENTIONED", "NOT_MENTIONED"),
            ("NOT_MENTIONED", "NOT_MENTIONED"),
        ]
        m = confusion_matrix(pairs)
        self.assertEqual(m["SUPPORTED"], {"SUPPORTED": 1, "CONTRADICTED": 0, "NOT_MENTIONED": 1})
        self.assertEqual(m["CONTRADICTED"], {"SUPPORTED": 0, "CONTRADICTED": 1, "NOT_MENTIONED": 0})
        self.assertEqual(m["NOT_MENTIONED"], {"SUPPORTED": 1, "CONTRADICTED": 0, "NOT_MENTIONED": 2})

    def test_empty_input_has_all_zero_cells(self):
        m = confusion_matrix([])
        self.assertEqual(set(m), set(STATUS_LABELS))
        self.assertTrue(all(v == 0 for row in m.values() for v in row.values()))

    def test_unknown_label_rejected(self):
        with self.assertRaises(ValueError):
            confusion_matrix([("SUPPORTED", "MAYBE")])
        with self.assertRaises(ValueError):
            confusion_matrix([("ERROR", "SUPPORTED")])


class ClassificationSummaryTests(unittest.TestCase):
    def test_hand_computed_summary(self):
        m = confusion_matrix([
            ("SUPPORTED", "SUPPORTED"),
            ("SUPPORTED", "NOT_MENTIONED"),
            ("CONTRADICTED", "CONTRADICTED"),
            ("NOT_MENTIONED", "SUPPORTED"),
            ("NOT_MENTIONED", "NOT_MENTIONED"),
            ("NOT_MENTIONED", "NOT_MENTIONED"),
        ])
        s = classification_summary(m)
        self.assertEqual(s["total"], 6)
        self.assertAlmostEqual(s["accuracy"], 4 / 6)
        self.assertAlmostEqual(s["per_class"]["SUPPORTED"]["precision"], 1 / 2)
        self.assertAlmostEqual(s["per_class"]["SUPPORTED"]["recall"], 1 / 2)
        self.assertAlmostEqual(s["per_class"]["NOT_MENTIONED"]["precision"], 2 / 3)
        self.assertAlmostEqual(s["per_class"]["NOT_MENTIONED"]["recall"], 2 / 3)
        self.assertEqual(s["false_support_count"], 1)
        self.assertAlmostEqual(s["false_support_rate"], 1 / 3)

    def test_zero_denominators_return_none(self):
        s = classification_summary(confusion_matrix([("SUPPORTED", "SUPPORTED")]))
        self.assertIsNone(s["per_class"]["CONTRADICTED"]["precision"])
        self.assertIsNone(s["per_class"]["CONTRADICTED"]["recall"])
        self.assertIsNone(s["false_support_rate"])
        self.assertEqual(s["false_support_count"], 0)

    def test_empty_matrix_accuracy_none(self):
        self.assertIsNone(classification_summary(confusion_matrix([]))["accuracy"])


class CandidateRankingTests(unittest.TestCase):
    def test_keeps_first_occurrence(self):
        self.assertEqual(candidate_ranking(["c2", "c1", "c2", "c3", "c1"]), ["c2", "c1", "c3"])

    def test_accepts_generator_and_empty(self):
        self.assertEqual(candidate_ranking(x for x in ["a", "a"]), ["a"])
        self.assertEqual(candidate_ranking([]), [])


class SubsetsByTests(unittest.TestCase):
    def test_groups_keep_order_and_all(self):
        rows = [{"id": 1, "d": "hard"}, {"id": 2, "d": "basic"}, {"id": 3, "d": "hard"}]
        groups = subsets_by(rows, "d", ("basic", "hard"))
        self.assertEqual([r["id"] for r in groups["all"]], [1, 2, 3])
        self.assertEqual([r["id"] for r in groups["basic"]], [2])
        self.assertEqual([r["id"] for r in groups["hard"]], [1, 3])

    def test_missing_level_is_empty_and_unknown_only_in_all(self):
        rows = [{"id": 1, "d": "basic"}, {"id": 2, "d": "other"}, {"id": 3}]
        groups = subsets_by(rows, "d", ("basic", "hard"))
        self.assertEqual(groups["hard"], [])
        self.assertEqual(len(groups["all"]), 3)
        self.assertEqual(set(groups), {"all", "basic", "hard"})

    def test_empty_subset_yields_none_metrics(self):
        groups = subsets_by([], "d", ("basic",))
        summary = classification_summary(confusion_matrix(
            (r["e"], r["p"]) for r in groups["basic"]))
        self.assertIsNone(summary["accuracy"])


class IsolationTests(unittest.TestCase):
    def test_valid_eval_namespace(self):
        check_isolation(RedisNamespace("idx:eval:resumes:v1", "eval:resume:v1:chunk:", "eval:resume:v1:hash:"), PROD)

    def test_same_index_name_rejected(self):
        with self.assertRaises(ValueError):
            check_isolation(RedisNamespace("idx:resumes:v1", "eval:c:", "eval:h:"), PROD)

    def test_prefix_containing_prod_rejected(self):
        with self.assertRaises(ValueError):
            check_isolation(RedisNamespace("idx:eval", "resume:v1:chunk:eval:", "eval:h:"), PROD)

    def test_prefix_contained_by_prod_rejected(self):
        with self.assertRaises(ValueError):
            check_isolation(RedisNamespace("idx:eval", "eval:c:", "resume:"), PROD)

    def test_empty_values_rejected(self):
        with self.assertRaises(ValueError):
            check_isolation(RedisNamespace("", "eval:c:", "eval:h:"), PROD)
        with self.assertRaises(ValueError):
            check_isolation(RedisNamespace("idx:eval", "", "eval:h:"), PROD)


class LoadJsonlTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, rows):
        path = self.dir / "data.jsonl"
        path.write_text("\n".join(r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in rows),
                        encoding="utf-8")
        return path

    def _load(self, path):
        return load_jsonl(path, ["case_id", "expected_status"], "case_id",
                          enum_fields={"expected_status": STATUS_LABELS})

    def test_valid_rows_and_blank_lines(self):
        path = self._write([{"case_id": "f1", "expected_status": "SUPPORTED", "question": "王小明會 Go 嗎？"}, "",
                            {"case_id": "f2", "expected_status": "NOT_MENTIONED"}])
        rows = self._load(path)
        self.assertEqual([r["case_id"] for r in rows], ["f1", "f2"])

    def test_missing_field_reports_line(self):
        path = self._write([{"case_id": "f1", "expected_status": "SUPPORTED"}, {"case_id": "f2"}])
        with self.assertRaisesRegex(ValueError, "第 2 行.*expected_status"):
            self._load(path)

    def test_invalid_status(self):
        path = self._write([{"case_id": "f1", "expected_status": "supported"}])
        with self.assertRaisesRegex(ValueError, "不合法"):
            self._load(path)

    def test_duplicate_id(self):
        path = self._write([{"case_id": "f1", "expected_status": "SUPPORTED"},
                            {"case_id": "f1", "expected_status": "CONTRADICTED"}])
        with self.assertRaisesRegex(ValueError, "重複"):
            self._load(path)

    def test_invalid_json_and_non_object(self):
        with self.assertRaisesRegex(ValueError, "不是合法 JSON"):
            self._load(self._write(["{bad"]))
        with self.assertRaisesRegex(ValueError, "JSON 物件"):
            self._load(self._write(["[1, 2]"]))


class UsageAndEmbeddingTests(unittest.TestCase):
    def test_merge_usage_accumulates_and_tolerates_missing(self):
        total = {}
        merge_usage(total, {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
                            "output_token_details": {"reasoning": 7}})
        merge_usage(total, {"input_tokens": 50, "output_tokens": None})
        merge_usage(total, None)
        self.assertEqual(total, {"input_tokens": 150, "output_tokens": 20, "total_tokens": 120,
                                 "thinking_tokens": 7})

    def test_counting_embedding_records_by_phase(self):
        class FakeEmbedding:
            dim = 4

            def embed_texts(self, texts, task_type="retrieval_document"):
                return [[0.0] * 4 for _ in texts]

            def embed_query(self, query):
                return [0.0] * 4

        svc = CountingEmbeddingService(FakeEmbedding())
        svc.embed_texts(texts=["ab", "cde"], task_type="retrieval_document")
        svc.embed_query("後端")
        svc.embed_query("前端工程師")
        self.assertEqual(svc.dim, 4)
        self.assertEqual(svc.stats["index"], {"calls": 1, "texts": 2, "chars": 5})
        self.assertEqual(svc.stats["query"], {"calls": 2, "texts": 2, "chars": 7})


class WriteCsvTests(unittest.TestCase):
    def test_utf8_bom_and_extra_keys_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.csv"
            write_csv(path, [{"case_id": "f1", "answer_text": "王小明具備帶領團隊經驗", "extra": 1}],
                      ["case_id", "answer_text", "spot_check_notes"])
            raw = path.read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            with path.open(encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(rows, [{"case_id": "f1", "answer_text": "王小明具備帶領團隊經驗", "spot_check_notes": ""}])


if __name__ == "__main__":
    unittest.main()
