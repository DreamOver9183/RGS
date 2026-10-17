"""Tests for guard_agy.py PreToolUse hook (M5)."""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.normpath(os.path.join(HERE, '..', 'scripts'))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import guard_agy
from guard_agy import is_direct_agy


class TestIsDirectAgy(unittest.TestCase):
    """驗收條件 4: 直接測 is_direct_agy 的真與假判定。"""

    def test_direct_agy_true_cases(self):
        """直接呼叫 agy 的各種語法皆應回傳 True。"""
        cases = [
            'agy -p hi',
            'agy.exe --version',
            r'"C:\Users\x\AppData\Local\agy\bin\agy.exe" -p hi',
            '/usr/local/bin/agy -p x',
            'cd x && agy -p y',
            'echo a; agy',
            'cat f | agy -p -',
            'FOO=1 agy -p x',
            r'& "C:\agy\agy.exe" -p x',
            '$(agy --version)',
            # 額外邊界情境
            '`agy --version`',
            'BAR=1 BAZ=2 agy -p foo',
            'call agy.exe -p test',
            'exec agy -p test',
            'env agy -p test',
            '& agy',
            'echo $(agy)',
            # M7 新增語法案例：子 shell、群組指令、前綴指令
            '(agy -p x)',
            '( agy -p x )',
            '{ agy -p x; }',
            'command agy -p x',
            'eval agy -p x',
            'eval "agy -p x"',
            'time agy --version',
            'nohup agy -p x',
            'sudo agy --version',
            # 含空白的引號路徑（雙引號與單引號）
            '"C:\\Program Files\\agy\\agy.exe" -p x',
            '"/opt/my tools/agy" -p x',
            "'C:\\Program Files\\agy\\agy.exe' --version",
            # fix-2: eval 內帶路徑與含空白路徑的 agy 呼叫
            'eval "/usr/bin/agy -p x"',
            'eval "C:\\tools\\agy.exe -p x"',
            'eval "C:\\Program Files\\agy\\agy.exe -p x"',
            "eval '/usr/bin/agy --version'",
        ]
        for cmd in cases:
            with self.subTest(cmd=cmd):
                self.assertTrue(
                    is_direct_agy(cmd),
                    f"Check failed: expected is_direct_agy to return True for {cmd!r}",
                )

    def test_direct_agy_false_cases(self):
        """合法指令、其他指令或 agy 僅作為參數時應回傳 False。"""
        cases = [
            'python -I /x/rgs-facet/scripts/facet_review.py --plan-file p --lens logic --round 1 --model gemini-4-argon-high',
            'grep agy notes.md',
            'echo agy',
            'ls',
            'git log',
            'python agy_helper.py',
            'echo "agy"',
            'cat agy.txt',
            '',
            None,
            123,
            # M7 新增放行案例
            '(cd sub && ls)',
            'command -v python',
            'eval echo hi',
            'time python -I x.py',
            # 引號內合法指令（避免將引號內路徑片段誤判為 agy）
            'eval "echo foo/agy"',
            'eval "git checkout feat/agy"',
            'eval "cat /path/to/agy"',
            "eval 'echo foo/agy'",
            '"echo foo/agy"',
            # fix-2: eval 內帶路徑的其他合法程式
            'eval "/usr/bin/python -I x.py"',
            'eval "C:\\Program Files\\Git\\bin\\git.exe log"',
        ]
        for cmd in cases:
            with self.subTest(cmd=cmd):
                self.assertFalse(
                    is_direct_agy(cmd),
                    f"Check failed: expected is_direct_agy to return False for {cmd!r}",
                )


class TestGuardAgySubprocess(unittest.TestCase):
    """驗收條件 4: 透過 subprocess 實際執行 guard_agy.py 驗證 PreToolUse hook 行為。"""

    def setUp(self):
        self.guard_script = os.path.join(SCRIPTS_DIR, 'guard_agy.py')
        self.assertTrue(
            os.path.isfile(self.guard_script),
            f"Check failed: guard_agy.py not found at {self.guard_script}",
        )

    def run_hook(self, payload_bytes):
        return subprocess.run(
            [sys.executable, '-I', self.guard_script],
            input=payload_bytes,
            capture_output=True,
            timeout=10,
        )

    def test_direct_agy_denied(self):
        """直接呼叫 agy 應輸出 deny JSON，exit 0，且 reason 包含 facet_review.py。"""
        for cmd in ["agy -p 'test'", "(agy -p x)"]:
            with self.subTest(cmd=cmd):
                payload = {
                    "tool_name": "Bash",
                    "tool_input": {"command": cmd},
                }
                raw = json.dumps(payload).encode('utf-8')
                proc = self.run_hook(raw)
                self.assertEqual(proc.returncode, 0, "Check failed: guard_agy must exit 0 on deny")
                stdout = proc.stdout.decode('utf-8', errors='replace').strip()
                self.assertTrue(stdout, "Check failed: guard_agy must output JSON on deny")
                data = json.loads(stdout)
                hso = data.get('hookSpecificOutput', {})
                self.assertEqual(hso.get('hookEventName'), 'PreToolUse')
                self.assertEqual(hso.get('permissionDecision'), 'deny')
                reason = hso.get('permissionDecisionReason', '')
                self.assertIn(
                    'facet_review.py',
                    reason,
                    "Check failed: deny reason must mention 'facet_review.py' as instructed in rules",
                )

    def test_allowed_bash_command(self):
        """合法指令放行：stdout 為空，exit 0。"""
        payload = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "python -I /x/rgs-facet/scripts/facet_review.py --plan-file p --lens logic --round 1 --model gemini-4-argon-high"
            },
        }
        raw = json.dumps(payload).encode('utf-8')
        proc = self.run_hook(raw)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.decode('utf-8').strip(), '')

    def test_non_bash_tool_allowed(self):
        """非 Bash 工具（如 Read）放行：stdout 為空，exit 0。"""
        payload = {
            "tool_name": "Read",
            "tool_input": {"file_path": "scripts/guard_agy.py"},
        }
        raw = json.dumps(payload).encode('utf-8')
        proc = self.run_hook(raw)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.decode('utf-8').strip(), '')

    def test_corrupt_json_allowed(self):
        """壞掉的 JSON 放行：stdout 為空，exit 0。"""
        raw = b'{"tool_name": "Bash", invalid json'
        proc = self.run_hook(raw)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.decode('utf-8').strip(), '')

    def test_empty_input_allowed(self):
        """空輸入放行：stdout 為空，exit 0。"""
        proc = self.run_hook(b'')
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.decode('utf-8').strip(), '')

    def test_missing_command_allowed(self):
        """tool_input 缺 command 放行：stdout 為空，exit 0。"""
        payload = {
            "tool_name": "Bash",
            "tool_input": {},
        }
        raw = json.dumps(payload).encode('utf-8')
        proc = self.run_hook(raw)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.decode('utf-8').strip(), '')

    def test_non_string_command_allowed(self):
        """command 非字串放行：stdout 為空，exit 0。"""
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": 12345},
        }
        raw = json.dumps(payload).encode('utf-8')
        proc = self.run_hook(raw)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.decode('utf-8').strip(), '')

    def test_non_dict_tool_input_allowed(self):
        """tool_input 非 dict 放行：stdout 為空，exit 0。"""
        payload = {
            "tool_name": "Bash",
            "tool_input": "invalid",
        }
        raw = json.dumps(payload).encode('utf-8')
        proc = self.run_hook(raw)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.decode('utf-8').strip(), '')


if __name__ == '__main__':
    unittest.main()
