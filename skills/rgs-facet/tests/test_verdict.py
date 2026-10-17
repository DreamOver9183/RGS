"""Tests for verdict parser, schema validator, and evidence checker (M2)."""

import json
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from verdict import VerdictError, evidence_found, load_schema, parse_response, validate


def make_valid_round1_verdict():
    """回傳全新的合法第一輪 verdict 物件。"""
    return {
        "verdict": "APPROVED",
        "findings": [
            {
                "id": "F-001",
                "severity": "medium",
                "evidence": "step 1 implementation plan",
                "issue": "needs clearer error handling",
                "suggestion": "specify exception types",
            }
        ],
        "coverage": "covers all milestones",
        "limitations": "none observed",
    }


def make_valid_round2_verdict():
    """回傳全新的合法第二輪 verdict 物件（含 resolved）。"""
    v = make_valid_round1_verdict()
    v["resolved"] = [
        {
            "id": "F-001",
            "status": "resolved",
            "note": "exception types specified in revision",
        }
    ]
    return v


class TestVerdictParser(unittest.TestCase):
    """驗收條件 1 & 2: parse_response 測試。"""

    def test_parse_response_pure_json(self):
        """驗收條件 1: 純 JSON 成功解析。"""
        data = make_valid_round1_verdict()
        text = json.dumps(data)
        result = parse_response(text)
        self.assertEqual(result, data)

    def test_parse_response_markdown_json_fence(self):
        """驗收條件 1: ```json 包住的 JSON 成功解析。"""
        data = make_valid_round1_verdict()
        text = f"```json\n{json.dumps(data, indent=2)}\n```"
        result = parse_response(text)
        self.assertEqual(result, data)

    def test_parse_response_markdown_fence_with_whitespace(self):
        """驗收條件 1: ``` 包住且前後有空白與換行的 JSON 成功解析。"""
        data = make_valid_round1_verdict()
        text = f"  \r\n\n```\r\n{json.dumps(data)}\r\n```  \n\n"
        result = parse_response(text)
        self.assertEqual(result, data)

    def test_parse_response_empty_or_whitespace(self):
        """驗收條件 2: 空字串與只有空白丟出 parse_error。"""
        for empty_text in ["", "   ", "\n\t  \r\n"]:
            with self.assertRaises(VerdictError) as cm:
                parse_response(empty_text)
            self.assertEqual(cm.exception.kind, "parse_error")

    def test_parse_response_none(self):
        """驗收條件 2: None 丟出 parse_error。"""
        with self.assertRaises(VerdictError) as cm:
            parse_response(None)
        self.assertEqual(cm.exception.kind, "parse_error")

    def test_parse_response_malformed_json(self):
        """驗收條件 2: 壞掉的 JSON 丟出 parse_error，訊息含原始說明。"""
        bad_texts = [
            '{"verdict": "APPROVED"',
            "```json\n{\"verdict\":\n```",
            "not a json at all",
        ]
        for bad_text in bad_texts:
            with self.assertRaises(VerdictError) as cm:
                parse_response(bad_text)
            self.assertEqual(cm.exception.kind, "parse_error")
            self.assertIsInstance(cm.exception.__cause__, json.JSONDecodeError)
            self.assertIn(cm.exception.__cause__.msg, str(cm.exception))


class TestVerdictValidate(unittest.TestCase):
    """驗收條件 3, 4, 5, 6: validate 測試。"""

    def test_validate_round1_success(self):
        """驗收條件 3: 合法第一輪 verdict 通過，回傳值 is 原物件。"""
        v = make_valid_round1_verdict()
        result = validate(v)
        self.assertIs(result, v)

    def test_validate_missing_coverage(self):
        """驗收條件 4: 缺 coverage ($.coverage)。"""
        v = make_valid_round1_verdict()
        del v["coverage"]
        with self.assertRaises(VerdictError) as cm:
            validate(v)
        self.assertEqual(cm.exception.kind, "schema_error")
        self.assertIn("$.coverage", str(cm.exception))

    def test_validate_findings_is_string(self):
        """驗收條件 4: findings 是字串 ($.findings)。"""
        v = make_valid_round1_verdict()
        v["findings"] = "not a list"
        with self.assertRaises(VerdictError) as cm:
            validate(v)
        self.assertEqual(cm.exception.kind, "schema_error")
        self.assertIn("$.findings", str(cm.exception))

    def test_validate_verdict_enum_error(self):
        """驗收條件 4: verdict 為 OK ($.verdict)。"""
        v = make_valid_round1_verdict()
        v["verdict"] = "OK"
        with self.assertRaises(VerdictError) as cm:
            validate(v)
        self.assertEqual(cm.exception.kind, "schema_error")
        self.assertIn("$.verdict", str(cm.exception))

    def test_validate_severity_enum_error(self):
        """驗收條件 4: severity 為 critical ($.findings[0].severity)。"""
        v = make_valid_round1_verdict()
        v["findings"][0]["severity"] = "critical"
        with self.assertRaises(VerdictError) as cm:
            validate(v)
        self.assertEqual(cm.exception.kind, "schema_error")
        self.assertIn("$.findings[0].severity", str(cm.exception))

    def test_validate_finding_missing_evidence(self):
        """驗收條件 4: finding 缺 evidence ($.findings[0].evidence)。"""
        v = make_valid_round1_verdict()
        del v["findings"][0]["evidence"]
        with self.assertRaises(VerdictError) as cm:
            validate(v)
        self.assertEqual(cm.exception.kind, "schema_error")
        self.assertIn("$.findings[0].evidence", str(cm.exception))

    def test_validate_round2_missing_resolved(self):
        """驗收條件 5: 第二輪缺 resolved ($.resolved)。"""
        v = make_valid_round1_verdict()
        with self.assertRaises(VerdictError) as cm:
            validate(v, round_no=2)
        self.assertEqual(cm.exception.kind, "schema_error")
        self.assertIn("$.resolved", str(cm.exception))

    def test_validate_round2_success(self):
        """驗收條件 5: 第二輪 resolved 合法通過。"""
        v2 = make_valid_round2_verdict()
        result = validate(v2, round_no=2)
        self.assertIs(result, v2)

    def test_validate_round2_status_enum_error(self):
        """驗收條件 5: resolved[0].status 為 done ($.resolved[0].status)。"""
        v2 = make_valid_round2_verdict()
        v2["resolved"][0]["status"] = "done"
        with self.assertRaises(VerdictError) as cm:
            validate(v2, round_no=2)
        self.assertEqual(cm.exception.kind, "schema_error")
        self.assertIn("$.resolved[0].status", str(cm.exception))

    def test_validate_round2_does_not_mutate_caller_schema(self):
        """驗收條件 5: 同一個 schema 物件先跑第二輪再跑第一輪，第一輪仍不要求 resolved。"""
        schema = load_schema()
        self.assertNotIn("resolved", schema.get("required", []))

        v2 = make_valid_round2_verdict()
        validate(v2, schema=schema, round_no=2)
        self.assertNotIn("resolved", schema.get("required", []))

        v1 = make_valid_round1_verdict()
        result1 = validate(v1, schema=schema, round_no=1)
        self.assertIs(result1, v1)
        self.assertNotIn("resolved", schema.get("required", []))

    def test_validate_unsupported_keyword_raises_value_error(self):
        """驗收條件 6: 自訂 schema 含 additionalProperties → ValueError 且 not VerdictError。"""
        custom_schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {"foo": {"type": "string"}},
        }
        with self.assertRaises(ValueError) as cm:
            validate({"foo": "bar"}, schema=custom_schema)
        self.assertNotIsInstance(cm.exception, VerdictError)
        self.assertIn("additionalProperties", str(cm.exception))

    def test_validate_unsupported_type_raises_value_error(self):
        """驗收條件 6: 自訂 schema 的 type 為 null → ValueError。"""
        custom_schema = {"type": "null"}
        with self.assertRaises(ValueError) as cm:
            validate(None, schema=custom_schema)
        self.assertNotIsInstance(cm.exception, VerdictError)
        self.assertIn("null", str(cm.exception))

    def test_validate_integer_type_rejects_bool(self):
        """驗收條件 6: {'type': 'integer'} 對 True → schema_error。"""
        int_schema = {"type": "integer"}
        with self.assertRaises(VerdictError) as cm:
            validate(True, schema=int_schema)
        self.assertEqual(cm.exception.kind, "schema_error")
        self.assertIn("expected integer", str(cm.exception))

    def test_validate_number_type_rejects_bool(self):
        """驗收條件 6: {'type': 'number'} 對 True → schema_error。"""
        num_schema = {"type": "number"}
        with self.assertRaises(VerdictError) as cm:
            validate(True, schema=num_schema)
        self.assertEqual(cm.exception.kind, "schema_error")
        self.assertIn("expected number", str(cm.exception))

    def test_validate_extra_properties_allowed(self):
        """不在 properties 中的多餘欄位不報錯。"""
        v = make_valid_round1_verdict()
        v["extra_custom_field"] = "arbitrary value"
        result = validate(v)
        self.assertIs(result, v)

    def test_validate_unsupported_keyword_in_unvisited_branch(self):
        """未走訪分支中的不支援關鍵字在 schema 檢查階段丟出 ValueError。"""
        custom_schema = {
            "type": "object",
            "properties": {
                "opt": {
                    "type": "string",
                    "additionalProperties": False,
                }
            },
        }
        with self.assertRaises(ValueError) as cm:
            validate({}, schema=custom_schema)
        self.assertNotIsInstance(cm.exception, VerdictError)
        self.assertIn("additionalProperties", str(cm.exception))
        self.assertIn("$.opt", str(cm.exception))

    def test_validate_non_dict_schema_round2(self):
        """第二輪傳入非 dict schema 丟出 ValueError 而非 AttributeError。"""
        with self.assertRaises(ValueError) as cm:
            validate({}, schema="invalid", round_no=2)
        self.assertNotIsInstance(cm.exception, VerdictError)

    def test_validate_enum_int_rejects_bool(self):
        """schema enum 含整數 1 時，傳入 1 通過，傳入 True 丟出 schema_error。"""
        enum_schema = {"enum": [1]}
        result = validate(1, schema=enum_schema)
        self.assertEqual(result, 1)

        with self.assertRaises(VerdictError) as cm:
            validate(True, schema=enum_schema)
        self.assertEqual(cm.exception.kind, "schema_error")
        self.assertIn("$", str(cm.exception))


class TestEvidenceFound(unittest.TestCase):
    """驗收條件 7: evidence_found 測試。"""

    def test_evidence_found_with_newlines_and_spaces(self):
        """驗收條件 7: 計畫中有換行與多個空格、evidence 是單一空格版本 → True。"""
        plan = (
            "# Milestone 1\n\n"
            "The system    shall   verify   all\n\n"
            "\t\tinputs before processing.\n"
        )
        evidence = "The system shall verify all inputs before processing."
        self.assertTrue(evidence_found(evidence, plan))

    def test_evidence_not_found(self):
        """驗收條件 7: evidence 不存在於計畫中 → False。"""
        plan = "The system shall verify all inputs before processing."
        evidence = "The system shall delete all files."
        self.assertFalse(evidence_found(evidence, plan))

    def test_evidence_empty_or_whitespace(self):
        """驗收條件 7: 空字串與只有空白 → False。"""
        plan = "Some plan text here."
        self.assertFalse(evidence_found("", plan))
        self.assertFalse(evidence_found("   ", plan))
        self.assertFalse(evidence_found("\t\n  \r\n", plan))
        self.assertFalse(evidence_found("", ""))
        self.assertFalse(evidence_found("evidence", ""))
        self.assertFalse(evidence_found(None, plan))
        self.assertFalse(evidence_found("evidence", None))


class TestLoadSchema(unittest.TestCase):
    """驗收條件 8: load_schema 測試。"""

    def test_load_schema_default(self):
        """驗收條件 8: load_schema() 不帶參數時讀到 M1 的 schema 檔，含 verdict, findings, coverage, limitations, resolved。"""
        schema = load_schema()
        self.assertIsInstance(schema, dict)
        self.assertEqual(schema.get("type"), "object")
        props = schema.get("properties")
        self.assertIsInstance(props, dict)
        for field in ["verdict", "findings", "coverage", "limitations", "resolved"]:
            self.assertIn(field, props)


if __name__ == "__main__":
    unittest.main()
