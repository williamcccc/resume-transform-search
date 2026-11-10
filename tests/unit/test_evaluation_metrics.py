"""
檢索與抽取品質指標白箱單元測試（src/domain/evaluation_metrics.py）
全部為記憶體內的虛構資料，零網路、零磁碟讀取。
"""
import ast
import math
import pathlib
import unittest

from src.domain.evaluation_metrics import (
    RetrievalCase,
    dedupe_ranked,
    field_f1,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    summarize_retrieval,
)

_MODULE_PATH = pathlib.Path(__file__).resolve().parents[2] / "src" / "domain" / "evaluation_metrics.py"
_ALLOWED_IMPORTS = {"__future__", "math", "dataclasses", "typing"}


class TestRecall(unittest.TestCase):
    def test_hand_calculated_three_relevant_two_hits_at_k3(self):
        self.assertAlmostEqual(recall_at_k({"a", "b", "c"}, ["a", "x", "b", "y"], 3), 2 / 3)

    def test_k_exceeds_result_length_uses_actual_results(self):
        self.assertAlmostEqual(recall_at_k({"a", "b", "c"}, ["a", "b"], 10), 2 / 3)

    def test_empty_relevant_returns_none(self):
        self.assertIsNone(recall_at_k(set(), ["a"], 3))


class TestPrecision(unittest.TestCase):
    def test_denominator_is_actual_length_when_k_exceeds_results(self):
        self.assertAlmostEqual(precision_at_k({"a"}, ["a", "x"], 5), 0.5)

    def test_empty_ranked_with_relevant_returns_zero(self):
        self.assertEqual(precision_at_k({"a"}, [], 3), 0.0)

    def test_empty_relevant_returns_none(self):
        self.assertIsNone(precision_at_k(set(), ["a"], 3))


class TestReciprocalRank(unittest.TestCase):
    def test_first_relevant_at_second_position(self):
        self.assertAlmostEqual(reciprocal_rank({"b"}, ["a", "b", "c"]), 0.5)

    def test_no_hit_returns_zero(self):
        self.assertEqual(reciprocal_rank({"b"}, ["a", "c"]), 0.0)

    def test_empty_relevant_returns_none(self):
        self.assertIsNone(reciprocal_rank(set(), ["a"]))


class TestNdcg(unittest.TestCase):
    def test_perfect_ranking_is_one(self):
        self.assertAlmostEqual(ndcg_at_k({"a", "b"}, ["a", "b", "x"], 3), 1.0)

    def test_hand_calculated_discount(self):
        dcg = 1 / math.log2(3) + 1 / math.log2(4)
        idcg = 1 / math.log2(2) + 1 / math.log2(3)
        self.assertAlmostEqual(ndcg_at_k({"a", "b"}, ["x", "a", "b"], 3), dcg / idcg)

    def test_ideal_count_capped_at_k(self):
        self.assertAlmostEqual(ndcg_at_k({"a", "b", "c"}, ["a", "b", "c"], 2), 1.0)

    def test_empty_relevant_returns_none(self):
        self.assertIsNone(ndcg_at_k(set(), ["a"], 3))


class TestDedupeAndK(unittest.TestCase):
    def test_duplicate_ids_count_once_for_rank(self):
        self.assertEqual(dedupe_ranked(["a", "a", "b"]), ["a", "b"])
        self.assertAlmostEqual(reciprocal_rank({"b"}, ["a", "a", "b"]), 0.5)

    def test_duplicate_ids_do_not_inflate_recall(self):
        self.assertAlmostEqual(recall_at_k({"a"}, ["a", "a"], 1), 1.0)

    def test_invalid_k_raises(self):
        for bad_k in (0, -1, True, 2.0):
            with self.subTest(k=bad_k):
                with self.assertRaises(ValueError):
                    recall_at_k({"a"}, ["a"], bad_k)


class TestFieldF1(unittest.TestCase):
    def test_identical_fields_score_one(self):
        expected = {"name": "王小明", "skills": ["python", "kubernetes"]}
        self.assertEqual(field_f1(expected, dict(expected)), 1.0)

    def test_case_and_whitespace_insensitive(self):
        expected = {"name": "王小明", "skills": ["python", "kubernetes"]}
        actual = {"name": "  王小明 ", "skills": ["Python", "KUBERNETES"]}
        self.assertEqual(field_f1(expected, actual), 1.0)

    def test_list_order_does_not_matter(self):
        self.assertEqual(field_f1({"skills": ["a", "b"]}, {"skills": ["b", "a"]}), 1.0)

    def test_both_empty_scores_one(self):
        self.assertEqual(field_f1({}, {}), 1.0)
        self.assertEqual(field_f1({"name": None}, {}), 1.0)
        self.assertEqual(field_f1({"name": ""}, {}), 1.0)

    def test_one_side_empty_scores_zero(self):
        self.assertEqual(field_f1({"name": "王小明"}, {}), 0.0)
        self.assertEqual(field_f1({}, {"name": "王小明"}), 0.0)

    def test_partial_match_hand_calculated(self):
        expected = {"skills": ["python", "kubernetes", "redis"]}
        actual = {"skills": ["python", "go"]}
        # tp=1, precision=1/2, recall=1/3, F1=2*(1/2)*(1/3)/(1/2+1/3)=0.4
        self.assertAlmostEqual(field_f1(expected, actual), 0.4)


class TestFieldF1Nested(unittest.TestCase):
    def test_nested_mapping_is_flattened_by_path(self):
        expected = {"education": {"school": "範例大學", "degree": "碩士"}}
        actual = {"education": {"school": " 範例大學", "degree": "學士"}}
        # facts: education.school 命中、education.degree 不同 → tp=1, P=1/2, R=1/2, F1=0.5
        self.assertAlmostEqual(field_f1(expected, actual), 0.5)

    def test_nested_key_does_not_match_top_level_key(self):
        self.assertEqual(field_f1({"education": {"school": "範例大學"}}, {"school": "範例大學"}), 0.0)

    def test_list_of_mappings_hand_calculated(self):
        expected = {"experience": [
            {"company": "範例科技", "title": "後端工程師"},
            {"company": "示範資訊", "title": "實習生"},
        ]}
        actual = {"experience": [{"company": "範例科技", "title": "資深後端工程師"}]}
        # expected facts 4 個、actual facts 2 個，僅 experience.company=範例科技 命中
        # tp=1, P=1/2, R=1/4, F1=2*(1/2)*(1/4)/(1/2+1/4)=1/3
        self.assertAlmostEqual(field_f1(expected, actual), 1 / 3)

    def test_nested_lists_are_flattened(self):
        self.assertEqual(field_f1({"tags": [["a", "b"], ["c"]]}, {"tags": ["c", "a", "b"]}), 1.0)

    def test_empty_nested_containers_count_as_missing(self):
        self.assertEqual(field_f1({"education": {}, "skills": [], "note": {"x": None}}, {}), 1.0)
        self.assertEqual(field_f1({"education": {"school": "範例大學"}}, {"education": {}}), 0.0)

    def test_deeply_nested_structure_does_not_raise(self):
        expected = {"a": {"b": [{"c": ["x", {"d": "y"}]}]}}
        self.assertEqual(field_f1(expected, expected), 1.0)


class TestSummarize(unittest.TestCase):
    def test_summary_excludes_empty_relevant_and_averages_rest(self):
        cases = [
            RetrievalCase("q1", frozenset({"a"}), ("a",)),
            RetrievalCase("q2", frozenset(), ("a",)),
            RetrievalCase("q3", frozenset({"b"}), ("a", "b")),
        ]
        summary = summarize_retrieval(cases, k=1)
        self.assertEqual(summary.counted, 2)
        self.assertEqual(summary.excluded, 1)
        self.assertAlmostEqual(summary.recall, 0.5)
        self.assertAlmostEqual(summary.precision, 0.5)
        self.assertAlmostEqual(summary.mrr, 0.75)
        self.assertAlmostEqual(summary.ndcg, 0.5)

    def test_summary_all_excluded_returns_none_means(self):
        summary = summarize_retrieval([RetrievalCase("q1", frozenset(), ("a",))], k=3)
        self.assertEqual((summary.counted, summary.excluded), (0, 1))
        self.assertIsNone(summary.recall)


class TestDomainPurity(unittest.TestCase):
    def test_module_imports_only_standard_library(self):
        tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue(imported <= _ALLOWED_IMPORTS, f"非標準庫匯入: {imported - _ALLOWED_IMPORTS}")


if __name__ == "__main__":
    unittest.main()
