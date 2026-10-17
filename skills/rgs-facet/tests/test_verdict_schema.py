"""Tests for verdict JSON schema (M1)."""

import json
import os
import unittest


def get_schema_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "references", "verdict.schema.json")


def load_verdict_schema():
    path = get_schema_path()
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestVerdictSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema_path = get_schema_path()
        cls.schema = load_verdict_schema()

    def test_load_and_top_level_type(self):
        """驗收條件 1: verdict.schema.json 是合法 JSON，頂層 type 為 object，結構與「設計」一節完全相同。"""
        self.assertTrue(os.path.isfile(self.schema_path))
        self.assertIsInstance(self.schema, dict)
        self.assertEqual(self.schema.get("type"), "object")
        self.assertIn("properties", self.schema)
        self.assertIsInstance(self.schema["properties"], dict)

        expected_schema = {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["APPROVED", "REVISE", "BLOCKED"]},
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                            "evidence": {"type": "string"},
                            "issue": {"type": "string"},
                            "suggestion": {"type": "string"},
                        },
                        "required": ["id", "severity", "evidence", "issue", "suggestion"],
                    },
                },
                "coverage": {"type": "string"},
                "limitations": {"type": "string"},
                "resolved": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "status": {"type": "string", "enum": ["resolved", "unresolved"]},
                            "note": {"type": "string"},
                        },
                        "required": ["id", "status", "note"],
                    },
                },
            },
            "required": ["verdict", "findings", "coverage", "limitations"],
        }
        self.assertEqual(self.schema, expected_schema)

    def test_top_level_required(self):
        """驗收條件 2: 頂層 required 恰為 verdict, findings, coverage, limitations，不含 resolved；resolved 在 properties 中。"""
        expected_required = {"verdict", "findings", "coverage", "limitations"}
        actual_required = self.schema.get("required")
        self.assertIsInstance(actual_required, list)
        self.assertEqual(set(actual_required), expected_required)
        self.assertEqual(len(actual_required), len(expected_required))
        self.assertNotIn("resolved", actual_required)
        self.assertIn("resolved", self.schema["properties"])

    def test_verdict_enum(self):
        """驗收條件 3: verdict 的 enum 恰為 APPROVED, REVISE, BLOCKED。"""
        verdict_prop = self.schema["properties"]["verdict"]
        self.assertEqual(verdict_prop.get("type"), "string")
        expected_enum = ["APPROVED", "REVISE", "BLOCKED"]
        self.assertEqual(verdict_prop.get("enum"), expected_enum)

    def test_findings_schema(self):
        """驗收條件 4: finding required 與 severity enum 相等；每個 finding 欄位的 type 為 string。"""
        findings_prop = self.schema["properties"]["findings"]
        self.assertEqual(findings_prop.get("type"), "array")
        items = findings_prop.get("items")
        self.assertIsInstance(items, dict)
        self.assertEqual(items.get("type"), "object")

        expected_finding_required = {"id", "severity", "evidence", "issue", "suggestion"}
        actual_finding_required = items.get("required")
        self.assertIsInstance(actual_finding_required, list)
        self.assertEqual(set(actual_finding_required), expected_finding_required)
        self.assertEqual(len(actual_finding_required), len(expected_finding_required))

        finding_props = items.get("properties")
        self.assertIsInstance(finding_props, dict)
        self.assertEqual(set(finding_props.keys()), expected_finding_required)

        for prop_name, prop_def in finding_props.items():
            self.assertEqual(
                prop_def.get("type"),
                "string",
                f"Expected finding property '{prop_name}' to have type 'string'",
            )

        expected_severity_enum = ["high", "medium", "low"]
        self.assertEqual(finding_props["severity"].get("enum"), expected_severity_enum)

    def test_resolved_schema(self):
        """驗收條件 5: resolved 是陣列，項目的 required 恰為 id, status, note；status 的 enum 恰為 resolved, unresolved。"""
        resolved_prop = self.schema["properties"]["resolved"]
        self.assertEqual(resolved_prop.get("type"), "array")
        items = resolved_prop.get("items")
        self.assertIsInstance(items, dict)
        self.assertEqual(items.get("type"), "object")

        expected_resolved_required = {"id", "status", "note"}
        actual_resolved_required = items.get("required")
        self.assertIsInstance(actual_resolved_required, list)
        self.assertEqual(set(actual_resolved_required), expected_resolved_required)
        self.assertEqual(len(actual_resolved_required), len(expected_resolved_required))

        resolved_props = items.get("properties")
        self.assertIsInstance(resolved_props, dict)
        self.assertEqual(set(resolved_props.keys()), expected_resolved_required)

        self.assertEqual(resolved_props["id"].get("type"), "string")
        self.assertEqual(resolved_props["note"].get("type"), "string")
        self.assertEqual(resolved_props["status"].get("type"), "string")
        expected_status_enum = ["resolved", "unresolved"]
        self.assertEqual(resolved_props["status"].get("enum"), expected_status_enum)

    def test_recursive_only_d1_keywords(self):
        """驗收條件 6: 遞迴檢查只用五個關鍵字（type, properties, required, enum, items）。"""
        allowed_keywords = {"type", "properties", "required", "enum", "items"}
        visited_nodes = 0

        def check_node(node, path="root"):
            nonlocal visited_nodes
            visited_nodes += 1
            self.assertIsInstance(node, dict, f"Schema node at {path} must be a dict")
            extra_keys = set(node.keys()) - allowed_keywords
            self.assertEqual(
                extra_keys,
                set(),
                f"Disallowed keywords at {path}: {extra_keys}",
            )

            if "properties" in node:
                self.assertIsInstance(
                    node["properties"], dict, f"'properties' at {path} must be a dict"
                )
                for prop_name, prop_schema in node["properties"].items():
                    check_node(prop_schema, path=f"{path}.properties['{prop_name}']")

            if "items" in node:
                check_node(node["items"], path=f"{path}.items")

        check_node(self.schema)
        self.assertGreaterEqual(visited_nodes, 10)


if __name__ == "__main__":
    unittest.main()
