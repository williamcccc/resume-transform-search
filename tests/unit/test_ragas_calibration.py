"""tests/eval/run_ragas_faithfulness.calibrate 白箱單元測試（手算小例子；不需安裝 ragas）。"""
import tempfile
import unittest
from pathlib import Path

from tests.eval.run_ragas_faithfulness import calibrate, extract_verdicts, read_labeled_csv


def _run(rid, parent, name, outputs=None, metadata=None, start="2026-11-12T00:00:00"):
    return {"id": rid, "parent_run_id": parent, "name": name, "outputs": outputs,
            "metadata": metadata or {}, "start_time": start}


def _nli(*items):
    return {"output": [{"statements": [dict(zip(("statement", "verdict", "reason"), i)) for i in items]}]}


class TestExtractVerdicts(unittest.TestCase):
    def test_maps_nli_statements_to_row_through_ancestors(self):
        runs = [
            _run("root", None, "faithfulness-x"),
            _run("r1", "root", "row 1", metadata={"type": "row", "row_index": 1}),
            _run("m1", "r1", "faithfulness-1"),
            _run("g1", "m1", "statement_generator_prompt", {"output": [{"statements": ["甲", "乙"]}]}),
            _run("n1", "m1", "n_l_i_statement_prompt", _nli(("甲", 1, "有寫"), ("乙", 0, "未提及"))),
            _run("r0", "root", "row 0"),  # 無 metadata，以名稱辨識
            _run("n0", "r0", "n_l_i_statement_prompt", _nli(("丙", 1, "ok"))),
        ]

        result = extract_verdicts(runs)

        self.assertEqual([(v["row"], v["statement_no"], v["statement"], v["verdict"]) for v in result],
                         [(0, 1, "丙", 1), (1, 1, "甲", 1), (1, 2, "乙", 0)])
        self.assertEqual(result[2]["reason"], "未提及")

    def test_retry_keeps_latest_nli_run_per_row(self):
        runs = [
            _run("r0", None, "row 0", metadata={"row_index": 0}),
            _run("old", "r0", "n_l_i_statement_prompt", _nli(("舊", 0, "")), start="2026-11-12T00:00:01"),
            _run("new", "r0", "n_l_i_statement_prompt", _nli(("新", 1, "")), start="2026-11-12T00:00:02"),
        ]

        self.assertEqual([v["statement"] for v in extract_verdicts(runs)], ["新"])

    def test_orphan_and_malformed_outputs_are_skipped(self):
        runs = [
            _run("n_orphan", None, "n_l_i_statement_prompt", _nli(("孤兒", 0, ""))),
            _run("r0", None, "row 0"),
            _run("n_bad", "r0", "n_l_i_statement_prompt", {"output": []}),
            _run("r1", None, "row 1"),
            _run("n_none", "r1", "n_l_i_statement_prompt", None),
        ]

        self.assertEqual(extract_verdicts(runs), [])

    def test_parent_cycle_does_not_loop_forever(self):
        runs = [_run("a", "b", "x"), _run("b", "a", "y"), _run("n", "a", "n_l_i_statement_prompt", _nli(("s", 1, "")))]

        self.assertEqual(extract_verdicts(runs), [])


class TestReadLabeledCsv(unittest.TestCase):
    def _read(self, data: bytes):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.csv"
            path.write_bytes(data)
            return read_labeled_csv(path)

    def test_utf8_bom_comma(self):
        rows = self._read("case_id,faithfulness,human_label\nf01,1.0,faithful\n".encode("utf-8-sig"))
        self.assertEqual(rows, [{"case_id": "f01", "faithfulness": "1.0", "human_label": "faithful"}])

    def test_excel_cp950_tab_delimited(self):
        text = "case_id\tresponse\tfaithfulness\thuman_label\r\nf01\t候選人 #1 帶領團隊, 4 人\t0.5\texaggerated\r\n"
        rows = self._read(text.encode("cp950"))
        self.assertEqual(rows[0]["response"], "候選人 #1 帶領團隊, 4 人")
        self.assertEqual(rows[0]["human_label"], "exaggerated")

    def test_missing_columns_raises(self):
        with self.assertRaisesRegex(ValueError, "human_label"):
            self._read("case_id,score\nf01,1\n".encode("utf-8"))


def _row(case_id, score, human):
    return {"case_id": case_id, "faithfulness": score, "human_label": human}


class TestCalibrate(unittest.TestCase):
    def test_hand_computed_agreement_recall_precision(self):
        rows = [
            _row("a", "1.0", "faithful"),       # 評審 faithful，一致
            _row("b", "0.5", "faithful"),       # 評審誤報
            _row("c", "0.25", "exaggerated"),   # 抓到
            _row("d", "1", "exaggerated"),      # 漏抓
            _row("e", "0", "Exaggerated "),     # 抓到（大小寫與空白容忍）
        ]

        result = calibrate(rows, threshold=1.0)

        self.assertEqual(result["matrix_human_to_judge"]["faithful"], {"faithful": 1, "exaggerated": 1, "nan": 0})
        self.assertEqual(result["matrix_human_to_judge"]["exaggerated"], {"faithful": 1, "exaggerated": 2, "nan": 0})
        self.assertAlmostEqual(result["agreement"], 3 / 5)
        self.assertAlmostEqual(result["exaggerated_recall"], 2 / 3)
        self.assertAlmostEqual(result["exaggerated_precision"], 2 / 3)
        self.assertEqual(result["labeled"], 5)

    def test_nan_and_blank_scores_counted_separately_not_in_agreement(self):
        rows = [_row("a", "", "faithful"), _row("b", "nan", "exaggerated"), _row("c", "1.0", "faithful")]

        result = calibrate(rows, threshold=1.0)

        self.assertEqual(result["judge_nan"], 2)
        self.assertEqual(result["labeled"], 3)
        self.assertEqual(result["agreement"], 1.0)
        self.assertIsNone(result["exaggerated_recall"])

    def test_unlabeled_rows_skipped_and_empty_gives_none(self):
        result = calibrate([_row("a", "0.3", ""), _row("b", "1.0", None)], threshold=1.0)

        self.assertEqual(result["unlabeled"], 2)
        self.assertEqual(result["labeled"], 0)
        self.assertIsNone(result["agreement"])
        self.assertIsNone(result["exaggerated_precision"])

    def test_threshold_boundary_is_strictly_less_than(self):
        rows = [_row("a", "0.8", "faithful"), _row("b", "0.79", "exaggerated")]

        result = calibrate(rows, threshold=0.8)

        self.assertEqual(result["agreement"], 1.0)

    def test_invalid_human_label_raises(self):
        with self.assertRaisesRegex(ValueError, "x1"):
            calibrate([_row("x1", "1.0", "maybe")], threshold=1.0)


if __name__ == "__main__":
    unittest.main()
