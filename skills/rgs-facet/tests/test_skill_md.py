"""Tests for rgs-facet SKILL.md structure, frontmatter, and referenced files (M5)."""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
FACET_DIR = os.path.normpath(os.path.join(HERE, '..'))
SKILLS_DIR = os.path.normpath(os.path.join(FACET_DIR, '..'))
CORE_DIR = os.path.normpath(os.path.join(SKILLS_DIR, 'rgs-core'))
SKILL_MD_PATH = os.path.join(FACET_DIR, 'SKILL.md')
SUMMARY_FORMAT_PATH = os.path.join(FACET_DIR, 'references', 'summary-format.md')


def parse_frontmatter(content):
    parts = content.split('---', 2)
    if len(parts) < 3:
        return {}, ""
    fm_text = parts[1]
    data = {}
    for line in fm_text.splitlines():
        if line and not line[0].isspace() and ':' in line:
            key, val = line.split(':', 1)
            data[key.strip()] = val.strip()
    return data, fm_text


class TestSkillMdStructure(unittest.TestCase):
    """驗收條件 1 & 2: SKILL.md 的結構、frontmatter 與內容檢查。"""

    def setUp(self):
        self.assertTrue(
            os.path.isfile(SKILL_MD_PATH),
            f"Check failed: SKILL.md does not exist at {SKILL_MD_PATH}",
        )
        with open(SKILL_MD_PATH, 'r', encoding='utf-8') as f:
            self.content = f.read()
        self.fm, self.fm_text = parse_frontmatter(self.content)

    def test_frontmatter_name(self):
        """Frontmatter name 必須是 'rgs-facet'。"""
        self.assertEqual(
            self.fm.get('name'),
            'rgs-facet',
            "Check failed: frontmatter 'name' must be exactly 'rgs-facet'",
        )

    def test_frontmatter_description(self):
        """Frontmatter description 存在、長度 <= 1024、不含角括號，且含指定觸發關鍵字。"""
        self.assertIn(
            'description',
            self.fm,
            "Check failed: frontmatter must contain 'description'",
        )
        desc = self.fm['description']
        self.assertLessEqual(
            len(desc),
            1024,
            f"Check failed: description length ({len(desc)}) must be <= 1024",
        )
        self.assertNotIn(
            '<',
            desc,
            "Check failed: description must not contain '<'",
        )
        self.assertNotIn(
            '>',
            desc,
            "Check failed: description must not contain '>'",
        )
        self.assertIn(
            '/rgs-facet',
            desc,
            "Check failed: description must contain '/rgs-facet'",
        )
        self.assertIn(
            'Plan 模式',
            desc,
            "Check failed: description must contain 'Plan 模式'",
        )
        self.assertIn(
            'Gemini',
            desc,
            "Check failed: description must contain 'Gemini'",
        )
        self.assertIn(
            'diff',
            desc,
            "Check failed: description must contain 'diff'",
        )
        self.assertIn(
            'PR',
            desc,
            "Check failed: description must contain 'PR'",
        )

    def test_frontmatter_fields(self):
        """Frontmatter 不得有 when_to_use，必須有 allowed-tools 與正確的 hooks 設定。"""
        self.assertNotIn(
            'when_to_use',
            self.fm,
            "Check failed: frontmatter must not contain 'when_to_use'",
        )
        self.assertIn(
            'allowed-tools',
            self.fm,
            "Check failed: frontmatter must contain 'allowed-tools'",
        )
        self.assertIn(
            'hooks:',
            self.fm_text,
            "Check failed: frontmatter must contain 'hooks:'",
        )
        self.assertIn(
            'PreToolUse',
            self.fm_text,
            "Check failed: frontmatter must contain 'PreToolUse'",
        )
        self.assertIn(
            'guard_agy.py',
            self.fm_text,
            "Check failed: frontmatter must contain 'guard_agy.py'",
        )
        self.assertIn(
            '|| true',
            self.fm_text,
            "Check failed: frontmatter hook command must contain '|| true'",
        )
        self.assertIn(
            '$HOME/.claude/skills/rgs-facet/scripts/guard_agy.py',
            self.fm_text,
            "Check failed: frontmatter must contain '$HOME/.claude/skills/rgs-facet/scripts/guard_agy.py'",
        )
        command_lines = [
            line for line in self.fm_text.splitlines() if line.strip().startswith('command:')
        ]
        self.assertTrue(
            command_lines,
            "Check failed: frontmatter must contain at least one 'command:' line",
        )
        for cmd_line in command_lines:
            self.assertNotIn(
                '${CLAUDE_SKILL_DIR}',
                cmd_line,
                "Check failed: frontmatter hook command line must not contain '${CLAUDE_SKILL_DIR}'",
            )

    def test_line_count(self):
        """SKILL.md 總行數不得超過 500 行。"""
        lines = self.content.splitlines()
        self.assertLessEqual(
            len(lines),
            500,
            f"Check failed: SKILL.md total lines ({len(lines)}) must be <= 500",
        )

    def test_parameters_block_verbatim(self):
        """參數區塊必須逐字包含指定的常數定義。"""
        self.assertIn(
            'REVIEWER_MODEL = gemini-4-argon-high',
            self.content,
            "Check failed: SKILL.md must contain exact 'REVIEWER_MODEL = gemini-4-argon-high'",
        )
        self.assertIn(
            'MAX_ROUNDS     = 3',
            self.content,
            "Check failed: SKILL.md must contain exact 'MAX_ROUNDS     = 3'",
        )
        self.assertIn(
            'AGY_TIMEOUT    = 900',
            self.content,
            "Check failed: SKILL.md must contain exact 'AGY_TIMEOUT    = 900'",
        )

    def test_review_runs_in_background(self):
        """送審一律在背景執行，不再設定 Bash 前景 timeout。"""
        self.assertIn(
            'run_in_background: true',
            self.content,
            "Check failed: SKILL.md must tell Claude to run facet_review.py with 'run_in_background: true'",
        )
        self.assertNotIn(
            '360000',
            self.content,
            "Check failed: SKILL.md must not set a foreground Bash timeout (360000)",
        )

    def test_timeout_is_not_retried(self):
        """status 表的 timeout 列不自動重試。"""
        rows = [line for line in self.content.splitlines() if line.startswith('| `timeout` |')]
        self.assertEqual(
            len(rows),
            1,
            "Check failed: SKILL.md status table must have exactly one '| `timeout` |' row",
        )
        self.assertIn(
            '不自動重試',
            rows[0],
            "Check failed: the timeout row must say '不自動重試'",
        )
        self.assertNotIn(
            '重試 1 次',
            rows[0],
            "Check failed: the timeout row must not allow '重試 1 次'",
        )

    def test_parameters_appear_before_flow(self):
        """參數區塊必須出現在流程章節之前。"""
        param_pos = self.content.find('REVIEWER_MODEL = gemini-4-argon-high')
        flow_pos = self.content.find('流程')
        self.assertNotEqual(
            param_pos,
            -1,
            "Check failed: parameter block was not found in SKILL.md",
        )
        self.assertNotEqual(
            flow_pos,
            -1,
            "Check failed: '流程' was not found in SKILL.md",
        )
        self.assertLess(
            param_pos,
            flow_pos,
            "Check failed: parameter block must appear before '流程' section",
        )

    def test_referenced_files_exist(self):
        """SKILL.md 中引用的 scripts、references 與 rgs-core scripts 檔案皆存在。"""
        facet_scripts = set(re.findall(r'(?<!rgs-core/)(?<!<core>/)scripts/([A-Za-z0-9_.-]+\.py)', self.content))
        self.assertTrue(
            facet_scripts,
            "Check failed: expected to find scripts references in SKILL.md",
        )
        for s in facet_scripts:
            path = os.path.join(FACET_DIR, 'scripts', s)
            self.assertTrue(
                os.path.isfile(path),
                f"Check failed: referenced script does not exist: {path}",
            )

        facet_refs = set(re.findall(r'references/([A-Za-z0-9_.-]+\.(?:md|json))', self.content))
        self.assertTrue(
            facet_refs,
            "Check failed: expected to find references references in SKILL.md",
        )
        for r in facet_refs:
            path = os.path.join(FACET_DIR, 'references', r)
            self.assertTrue(
                os.path.isfile(path),
                f"Check failed: referenced file does not exist: {path}",
            )

        core_scripts = set(re.findall(r'rgs-core/scripts/([A-Za-z0-9_.-]+\.py)', self.content))
        self.assertTrue(
            core_scripts,
            "Check failed: expected to find rgs-core scripts references in SKILL.md",
        )
        for cs in core_scripts:
            path = os.path.join(CORE_DIR, 'scripts', cs)
            self.assertTrue(
                os.path.isfile(path),
                f"Check failed: referenced core script does not exist: {path}",
            )

    def test_commands_use_parameters(self):
        """流程與呼叫指令中的模型與逾時應使用參數佔位符，路徑使用完整變數。"""
        self.assertEqual(
            self.content.count('gemini-4-argon-high'),
            1,
            "Check failed: 'gemini-4-argon-high' must appear exactly once in SKILL.md (in parameters block only)",
        )
        self.assertIn(
            '--model <REVIEWER_MODEL>',
            self.content,
            "Check failed: commands must use '--model <REVIEWER_MODEL>' instead of hardcoded model",
        )
        self.assertIn(
            '--timeout <AGY_TIMEOUT>',
            self.content,
            "Check failed: commands must use '--timeout <AGY_TIMEOUT>' instead of hardcoded timeout",
        )
        self.assertIn(
            '${CLAUDE_SKILL_DIR}/../rgs-core/scripts/doctor.py --flow facet',
            self.content,
            "Check failed: doctor.py command must use '${CLAUDE_SKILL_DIR}/../rgs-core/scripts/doctor.py --flow facet' to match allowed-tools",
        )


class TestSummaryFormatDoc(unittest.TestCase):
    """驗收條件 3: summary-format.md 存在且包含必要段落。"""

    def test_summary_format_exists_and_content(self):
        self.assertTrue(
            os.path.isfile(SUMMARY_FORMAT_PATH),
            f"Check failed: summary-format.md does not exist at {SUMMARY_FORMAT_PATH}",
        )
        with open(SUMMARY_FORMAT_PATH, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn(
            '## 審查摘要',
            content,
            "Check failed: summary-format.md must contain '## 審查摘要'",
        )
        self.assertIn(
            '<!-- facet:appendix -->',
            content,
            "Check failed: summary-format.md must contain '<!-- facet:appendix -->'",
        )
        self.assertIn(
            '未確認',
            content,
            "Check failed: summary-format.md must contain '未確認'",
        )


if __name__ == '__main__':
    unittest.main()
