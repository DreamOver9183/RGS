"""Tests for prompt module, review prompt template, and pre-review checks (M3)."""
import json
import os
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import prompt
from prompt import (
    MAX_PROMPT_CHARS,
    PromptError,
    build_prompt,
    load_plan,
    load_template,
    scan_secrets,
    strip_appendix,
    validate_prior,
)
import secret_scan


class TestStripAppendixAndLoadPlan(unittest.TestCase):
    """驗收條件 1: strip_appendix 與 load_plan 測試。"""

    def test_strip_appendix_with_marker(self):
        """附錄標記之後的內容被截掉，結尾空白被去掉。"""
        text = "計畫正文內容\n\n<!-- facet:appendix -->\n附錄一：補充資料"
        self.assertEqual(strip_appendix(text), "計畫正文內容")

    def test_strip_appendix_without_marker(self):
        """沒有標記時回傳整份，去掉結尾空白。"""
        text = "只有正文內容\n\n   \t"
        self.assertEqual(strip_appendix(text), "只有正文內容")

    def test_strip_appendix_two_markers(self):
        """標記出現兩次時以第一個為準。"""
        text = "正文\n<!-- facet:appendix -->\n附錄1\n<!-- facet:appendix -->\n附錄2"
        self.assertEqual(strip_appendix(text), "正文")

    def test_strip_appendix_trailing_whitespace(self):
        """正文結尾的多餘換行與空白皆被去掉。"""
        text = "正文最後有空白   \t\n  \n<!-- facet:appendix -->\n附錄"
        self.assertEqual(strip_appendix(text), "正文最後有空白")

    def test_load_plan_with_bom(self):
        """load_plan 能正確讀取帶有 UTF-8 BOM 的檔案。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = os.path.join(tmpdir, "plan_with_bom.md")
            with open(p, "wb") as f:
                f.write("\ufeff# 標題\n正文內容\n<!-- facet:appendix -->\n附錄".encode("utf-8"))
            res = load_plan(p)
            self.assertEqual(res, "# 標題\n正文內容")

    def test_load_plan_without_bom(self):
        """load_plan 能正確讀取無 BOM 的檔案。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = os.path.join(tmpdir, "plan_no_bom.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write("# 無BOM\n計畫正文\n<!-- facet:appendix -->\n附錄")
            res = load_plan(p)
            self.assertEqual(res, "# 無BOM\n計畫正文")


class TestScanSecrets(unittest.TestCase):
    """驗收條件 2 & 3: scan_secrets 命中、誤判與委派測試。"""

    def test_scan_secrets_all_builtin_patterns(self):
        """每種內建樣式各放一行假金鑰，斷言命中、遮蔽、排序、無完整金鑰洩漏。"""
        samples = [
            ("google-api-key", "AIza" + "0" * 35),
            ("openai-key", "s" + "k-" + "1" * 32),
            ("anthropic-key", "s" + "k-ant-" + "2" * 32),
            ("github-token", "gh" + "p_" + "3" * 36),
            ("aws-access-key", "AK" + "IA" + "4" * 16),
            ("slack-token", "xo" + "xb-" + "5" * 10),
            ("private-key", "-----BEGIN " + "RSA " + "PRIVATE KEY-----"),
            ("assigned-secret", 'api_' + 'key = "' + "6" * 16 + '"'),
        ]

        lines = [sample for _, sample in samples]
        text = "\n".join(lines)
        hits = scan_secrets(text)

        # 斷言每筆只有 kind, line, match 三個鍵
        for h in hits:
            self.assertEqual(set(h.keys()), {"kind", "line", "match"})

        # 斷言結果依 (line, kind) 排序
        self.assertEqual(
            hits, sorted(hits, key=lambda h: (h["line"], h["kind"]))
        )

        # 斷言每一行至少有一筆命中、kind 集合包含預期種類、match 等於 secret_scan.mask 的結果
        for line_no, (expected_kind, sample) in enumerate(samples, 1):
            line_hits = [h for h in hits if h["line"] == line_no]
            self.assertGreaterEqual(
                len(line_hits), 1, f"Line {line_no} should have at least one hit"
            )
            line_kinds = {h["kind"] for h in line_hits}
            self.assertIn(
                expected_kind,
                line_kinds,
                f"Line {line_no} kinds {line_kinds} should include {expected_kind}",
            )
            expected_mask = secret_scan.mask(sample)
            for h in line_hits:
                self.assertEqual(h["match"], expected_mask)

        # 斷言 json.dumps(hits) 不含任何完整金鑰
        hits_json = json.dumps(hits)
        for _, sample in samples:
            self.assertNotIn(sample, hits_json)

    def test_scan_secrets_clean_text(self):
        """正常計畫文字回傳空清單。"""
        clean_text = (
            "這是一份完全正常的計畫，沒有包含任何金鑰或敏感憑證資訊。\n"
            "步驟 1：開發模組。\n"
            "步驟 2：執行測試。"
        )
        self.assertEqual(scan_secrets(clean_text), [])

    def test_scan_secrets_no_false_positives(self):
        """不符合規格的短字串或相似詞不誤判。"""
        false_positives = [
            "task-" + "x" * 30,
            "AK" + "IA" + "1" * 10,
            "gh" + "p_" + "a" * 10,
            "s" + "k-" + "x" * 5,
            "請勿把 PRIVATE KEY 貼進計畫",
        ]
        text = "\n".join(false_positives)
        self.assertEqual(scan_secrets(text), [])

    def test_scan_secrets_delegates_to_scan_text(self):
        """同一段文字，prompt.scan_secrets(text) 的 (line, kind, match) 集合等於 secret_scan.scan_text(text) 的。"""
        text = (
            "說明段落\n"
            + ("AK" + "IA" + "Q" * 16)
            + "\n一般文字\n"
            + ("gh" + "p_" + "a" * 36)
            + "\n結尾"
        )
        prompt_hits = scan_secrets(text)
        core_hits = secret_scan.scan_text(text)
        prompt_set = {(h["line"], h["kind"], h["match"]) for h in prompt_hits}
        core_set = {(h["line"], h["kind"], h["match"]) for h in core_hits}
        self.assertEqual(prompt_set, core_set)


class TestLoadTemplate(unittest.TestCase):
    """驗收條件 4: load_template 解析與錯誤處理。"""

    def test_load_real_template(self):
        """實際範本檔能正確解析，五段都不是空字串。"""
        tpl = load_template()
        self.assertIn("base", tpl)
        self.assertIn("lens", tpl)
        self.assertIn("round2", tpl)
        self.assertIn("logic", tpl["lens"])
        self.assertIn("gaps", tpl["lens"])
        self.assertIn("verifiability", tpl["lens"])
        self.assertTrue(len(tpl["base"].strip()) > 0)
        self.assertTrue(len(tpl["lens"]["logic"].strip()) > 0)
        self.assertTrue(len(tpl["lens"]["gaps"].strip()) > 0)
        self.assertTrue(len(tpl["lens"]["verifiability"].strip()) > 0)
        self.assertTrue(len(tpl["round2"].strip()) > 0)

    def _make_valid_template_content(self):
        return (
            "# Title\n\n"
            "## base\n```text\nbase content {LENS} {LENS_CHECKLIST} {ROUND2_BLOCK} {PLAN}\n```\n\n"
            "## lens: logic\n```text\nlogic checklist\n```\n\n"
            "## lens: gaps\n```text\ngaps checklist\n```\n\n"
            "## lens: verifiability\n```text\nverifiability checklist\n```\n\n"
            "## round2\n```text\nround2 content {PRIOR_JSON}\n```\n"
        )

    def test_load_template_missing_section(self):
        """缺段時丟出 ValueError，訊息含段落名稱。"""
        content = self._make_valid_template_content().replace(
            "## round2\n```text\nround2 content {PRIOR_JSON}\n```\n", ""
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            p = os.path.join(tmpdir, "bad_template.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            with self.assertRaises(ValueError) as cm:
                load_template(p)
            self.assertIn("round2", str(cm.exception))

    def test_load_template_duplicate_section(self):
        """段落重複時丟出 ValueError，訊息含段落名稱。"""
        content = self._make_valid_template_content() + "## base\n```text\ndup base\n```\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            p = os.path.join(tmpdir, "dup_template.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            with self.assertRaises(ValueError) as cm:
                load_template(p)
            self.assertIn("base", str(cm.exception))

    def test_load_template_missing_text_block(self):
        """某段缺 ```text 區塊時丟出 ValueError，訊息含段落名稱。"""
        content = self._make_valid_template_content().replace(
            "## lens: logic\n```text\nlogic checklist\n```\n",
            "## lens: logic\njust plain text\n",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            p = os.path.join(tmpdir, "missing_fence.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            with self.assertRaises(ValueError) as cm:
                load_template(p)
            self.assertIn("lens: logic", str(cm.exception))

    def test_load_template_unclosed_text_block(self):
        """某段 ```text 區塊沒有結束行時丟出 ValueError，訊息含段落名稱。"""
        content = self._make_valid_template_content().replace(
            "## lens: gaps\n```text\ngaps checklist\n```\n",
            "## lens: gaps\n```text\nunclosed gaps\n",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            p = os.path.join(tmpdir, "unclosed_fence.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            with self.assertRaises(ValueError) as cm:
                load_template(p)
            self.assertIn("lens: gaps", str(cm.exception))


class TestBuildPromptRound1(unittest.TestCase):
    """驗收條件 5: 第一輪 prompt 組裝。"""

    def test_build_prompt_round1_three_lenses(self):
        """三個視角各一個案例，驗證視角內容、無混入、無前輪區塊、無佔位符殘留。"""
        logic_first = "- 步驟之間、步驟與目標或驗收條件之間，有沒有互相矛盾。"
        gaps_first = "- 遺漏的邊界條件與異常輸入（空值、超長、編碼、權限、同時執行）。"
        verif_first = "- 每條驗收條件能不能客觀判定通過或失敗；「正常」「完全相同」這類寫法要附上比對方式。"

        cases = [
            ("logic", logic_first, [gaps_first, verif_first]),
            ("gaps", gaps_first, [logic_first, verif_first]),
            ("verifiability", verif_first, [logic_first, gaps_first]),
        ]

        for lens, expected_line, other_lines in cases:
            with self.subTest(lens=lens):
                prompt_text = build_prompt("這是待審核的計畫內文。", lens, round_no=1)
                self.assertIn(f"從「{lens}」角度審查以下計畫", prompt_text)
                self.assertIn(expected_line, prompt_text)
                for other_line in other_lines:
                    self.assertNotIn(other_line, prompt_text)
                self.assertIn("這是待審核的計畫內文。", prompt_text)
                self.assertIn('"verdict":"APPROVED|REVISE|BLOCKED"', prompt_text)
                self.assertNotIn("===== 前輪處置 =====", prompt_text)
                self.assertNotIn("{LENS}", prompt_text)
                self.assertNotIn("{LENS_CHECKLIST}", prompt_text)
                self.assertNotIn("{ROUND2_BLOCK}", prompt_text)
                self.assertNotIn("{PLAN}", prompt_text)


class TestBuildPromptRound2(unittest.TestCase):
    """驗收條件 6: 第二輪 prompt 組裝。"""

    def test_build_prompt_round2(self):
        """第二輪含前輪處置、中文未跳脫之 JSON、resolved 要求，無 PRIOR_JSON 殘留。"""
        prior = {
            "changes_summary": "依前輪建議補強錯誤處理與邊界條件說明",
            "prior_findings": [
                {
                    "id": "F1",
                    "severity": "high",
                    "issue": "缺少例外處理說明",
                    "disposition": "accepted",
                    "reason": "已在第 3 步加入例外處理流程",
                }
            ],
        }
        prompt_text = build_prompt("新版修訂計畫正文", "logic", round_no=2, prior=prior)
        self.assertIn("===== 前輪處置 =====", prompt_text)
        self.assertIn("===== 前輪處置結束 =====", prompt_text)
        self.assertIn("依前輪建議補強錯誤處理與邊界條件說明", prompt_text)
        self.assertIn("缺少例外處理說明", prompt_text)
        self.assertIn("已在第 3 步加入例外處理流程", prompt_text)
        self.assertIn('"resolved"', prompt_text)
        self.assertNotIn("{PRIOR_JSON}", prompt_text)


class TestPlaceholderSinglePass(unittest.TestCase):
    """驗收條件 7: 佔位符替換只做一次，計畫內文含佔位符字樣原樣保留。"""

    def test_placeholder_single_pass(self):
        """計畫內文含有 {PLAN}、{LENS}、{PRIOR_JSON} 時原樣保留在第一輪與第二輪輸出中。"""
        tricky_plan = "步驟 {PLAN} 與 {LENS} 與 {PRIOR_JSON} 測試"

        p1 = build_prompt(tricky_plan, "logic", round_no=1)
        self.assertIn(tricky_plan, p1)

        prior = {"changes_summary": "修訂計畫", "prior_findings": []}
        p2 = build_prompt(tricky_plan, "logic", round_no=2, prior=prior)
        self.assertIn(tricky_plan, p2)


class TestPriorValidation(unittest.TestCase):
    """驗收條件 8: 前輪資料驗證與錯誤處理。"""

    def test_round1_with_prior_raises_error(self):
        """第一輪提供 prior 丟出 PromptError(kind='invalid_prior')。"""
        prior = {"changes_summary": "修訂", "prior_findings": []}
        with self.assertRaises(PromptError) as cm:
            build_prompt("計畫", "logic", round_no=1, prior=prior)
        self.assertEqual(cm.exception.kind, "invalid_prior")
        self.assertIn("Round 1", str(cm.exception))

    def test_round2_without_prior_raises_error(self):
        """第二輪未提供 prior 丟出 PromptError(kind='invalid_prior')。"""
        with self.assertRaises(PromptError) as cm:
            build_prompt("計畫", "logic", round_no=2, prior=None)
        self.assertEqual(cm.exception.kind, "invalid_prior")
        self.assertIn("Round 2", str(cm.exception))

    def test_prior_missing_required_field(self):
        """前輪資料缺少必要欄位丟出 PromptError，訊息含欄位路徑。"""
        bad_prior = {
            "changes_summary": "修訂",
            "prior_findings": [
                {
                    "id": "F1",
                    "severity": "high",
                    "issue": "缺少說明",
                    "reason": "已修復",
                }
            ],
        }
        with self.assertRaises(PromptError) as cm:
            build_prompt("計畫", "logic", round_no=2, prior=bad_prior)
        self.assertEqual(cm.exception.kind, "invalid_prior")
        self.assertIn("$.prior_findings[0].disposition", str(cm.exception))

    def test_prior_invalid_disposition(self):
        """前輪資料 disposition 不合法丟出 PromptError，訊息含欄位路徑。"""
        bad_prior = {
            "changes_summary": "修訂",
            "prior_findings": [
                {
                    "id": "F1",
                    "severity": "high",
                    "issue": "缺少說明",
                    "disposition": "postponed",
                    "reason": "已修復",
                }
            ],
        }
        with self.assertRaises(PromptError) as cm:
            build_prompt("計畫", "logic", round_no=2, prior=bad_prior)
        self.assertEqual(cm.exception.kind, "invalid_prior")
        self.assertIn("$.prior_findings[0].disposition", str(cm.exception))

    def test_prior_empty_findings_accepted(self):
        """prior_findings 為空陣列時可以通過驗證。"""
        empty_prior = {"changes_summary": "修訂計畫", "prior_findings": []}
        p = build_prompt("計畫內文", "logic", round_no=2, prior=empty_prior)
        self.assertIn('"prior_findings": []', p)


class TestPromptLengthLimit(unittest.TestCase):
    """驗收條件 9: 長度上限邊界檢查。"""

    def test_prompt_length_limit(self):
        """剛好等於上限通過，多 1 個字元丟出 PromptError(kind='plan_too_long')。"""
        overhead = len(build_prompt("x", "logic", round_no=1)) - 1
        exact_len = MAX_PROMPT_CHARS - overhead
        exact_plan = "a" * exact_len

        p = build_prompt(exact_plan, "logic", round_no=1)
        self.assertEqual(len(p), MAX_PROMPT_CHARS)

        too_long_plan = "a" * (exact_len + 1)
        with self.assertRaises(PromptError) as cm:
            build_prompt(too_long_plan, "logic", round_no=1)
        self.assertEqual(cm.exception.kind, "plan_too_long")
        self.assertIn(str(MAX_PROMPT_CHARS + 1), str(cm.exception))
        self.assertIn(str(MAX_PROMPT_CHARS), str(cm.exception))


class TestInvalidArguments(unittest.TestCase):
    """驗收條件 10: 參數型別與邊界錯誤檢查。"""

    def test_unknown_lens(self):
        """未知視角丟出 ValueError。"""
        with self.assertRaises(ValueError):
            build_prompt("計畫", "security")

    def test_invalid_round_no(self):
        """round_no 為 0、True 或字串皆丟出 ValueError。"""
        for bad_round in [0, -1, True, False, "2", 1.5]:
            with self.subTest(bad_round=bad_round):
                with self.assertRaises(ValueError):
                    build_prompt("計畫", "logic", round_no=bad_round)

    def test_invalid_plan_text(self):
        """空白或非字串計畫丟出 ValueError。"""
        for bad_plan in ["", "   ", " \t \n ", 12345, None, []]:
            with self.subTest(bad_plan=bad_plan):
                with self.assertRaises(ValueError):
                    build_prompt(bad_plan, "logic")


if __name__ == "__main__":
    unittest.main()
