"""End-to-end tests for facet_review.py (M4)."""

import json
import os
import shutil
import subprocess
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
FACET_DIR = os.path.dirname(TESTS_DIR)
SCRIPTS_DIR = os.path.join(FACET_DIR, 'scripts')
FACET_REVIEW_PY = os.path.join(SCRIPTS_DIR, 'facet_review.py')
CORE_DIR = os.path.normpath(os.path.join(FACET_DIR, '..', 'rgs-core'))
FAKE_AGY = os.path.join(CORE_DIR, 'tests', 'fake_agy.py')
CORE_TESTS = os.path.join(CORE_DIR, 'tests')
if CORE_TESTS not in sys.path:
    sys.path.insert(0, CORE_TESTS)

import helpers

SAMPLE_PLAN = """# Architecture Plan

## Authentication
User authentication system using JWT tokens.
All requests will validate the JWT signature and claims.

<!-- facet:appendix -->
## Appendix
This is confidential internal notes that must be stripped before sending to reviewer.
"""

VALID_VERDICT = {
    'verdict': 'APPROVED',
    'coverage': 'Covers all critical security aspects.',
    'limitations': 'External auth provider not tested.',
    'findings': [
        {
            'id': 'F-1',
            'severity': 'medium',
            'evidence': 'User authentication system using JWT tokens',
            'issue': 'Token expiration not configured',
            'suggestion': 'Configure 15-minute expiration',
        },
        {
            'id': 'F-2',
            'severity': 'low',
            'evidence': 'This text definitely does not appear in the plan at all',
            'issue': 'Consider using refresh tokens',
            'suggestion': 'Add refresh token rotation',
        },
    ],
}


class BaseFacetReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = helpers.TempDir()
        self.state_dir = os.path.join(self.tmp.path, 'state')
        os.makedirs(self.state_dir, exist_ok=True)
        self.run_dir = os.path.join(self.tmp.path, 'runs')
        os.makedirs(self.run_dir, exist_ok=True)
        self.repo_dir = os.path.join(self.tmp.path, 'repo')
        os.makedirs(self.repo_dir, exist_ok=True)
        self.plan_file = os.path.join(self.tmp.path, 'plan.md')
        with open(self.plan_file, 'w', encoding='utf-8', newline='\n') as f:
            f.write(SAMPLE_PLAN)

    def tearDown(self):
        self.tmp.cleanup()

    def get_recorded_calls(self):
        calls_dir = os.path.join(self.state_dir, 'calls')
        if not os.path.isdir(calls_dir):
            return []
        calls = []
        for f in sorted(os.listdir(calls_dir)):
            if f.endswith('.json'):
                with open(os.path.join(calls_dir, f), 'r', encoding='utf-8') as fp:
                    calls.append(json.load(fp))
        return calls

    def run_review(self, args, input_text=None, scenario='structured', extra_env=None):
        env = dict(os.environ)
        env['RGS_AGY'] = FAKE_AGY
        env['FAKE_AGY_DIR'] = self.state_dir
        if scenario is not None:
            env['FAKE_AGY_SCENARIO'] = scenario
        if extra_env:
            env.update(extra_env)

        proc = subprocess.run(
            [sys.executable, '-I', FACET_REVIEW_PY, *args],
            cwd=self.repo_dir,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env,
            input=input_text,
        )
        return proc


class TestFacetReviewOkAndBasics(BaseFacetReviewTest):
    """驗收條件 1, 3, 6, 7: ok, evidence_found, sealed workspace, meta.json, appendix stripping."""

    def test_ok_flow(self):
        extra_env = {'FAKE_AGY_STRUCTURED': json.dumps(VALID_VERDICT)}
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'logic',
            '--round', '1',
            '--model', 'gemini-3.8-flash-high',
            '--run-dir', self.run_dir,
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args, scenario='structured', extra_env=extra_env)
        self.assertEqual(proc.returncode, 0, f'Expected exit code 0, got {proc.returncode}: {proc.stderr}')

        # 驗收條件 7: stdout 只有一行 JSON
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, f'Expected 1 line in stdout, got {len(lines)}: {proc.stdout}')
        data = json.loads(lines[0])

        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['verdict'], 'APPROVED')
        self.assertEqual(data['coverage'], 'Covers all critical security aspects.')
        self.assertEqual(data['limitations'], 'External auth provider not tested.')
        self.assertEqual(data['lens'], 'logic')
        self.assertEqual(data['round'], 1)
        self.assertEqual(data['requested_model'], 'gemini-3.8-flash-high')
        self.assertEqual(data['reported_model'], 'Fake gemini-3.8-flash-high')
        self.assertTrue(data['test_double'])
        self.assertEqual(data['detail'], '')
        self.assertEqual(data['resolved'], [])

        # evidence_found: 一真一假
        findings = data['findings']
        self.assertEqual(len(findings), 2)
        self.assertTrue(findings[0]['evidence_found'])
        self.assertFalse(findings[1]['evidence_found'])

        # 條件不符合時不該出現的欄位
        self.assertNotIn('secret_hits', data)
        self.assertNotIn('repo_changes', data)
        self.assertNotIn('workspace_new_files', data)

        # 驗收條件 3: agy 在 sealed 暫存工作區執行
        calls = self.get_recorded_calls()
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual(call['guard']['role'], 'sealed')
        self.assertIn('--json-schema', call['argv'])
        self.assertIn('--model', call['argv'])
        self.assertNotIn('--mode', call['argv'])

        # 結束後工作區已刪除
        self.assertFalse(os.path.exists(call['cwd']))

        # call 目錄與檔案
        call_dir = os.path.join(self.run_dir, 'r1-logic')
        self.assertEqual(os.path.normpath(data['raw_dir']), os.path.normpath(call_dir))
        self.assertTrue(os.path.isfile(os.path.join(call_dir, 'prompt.md')))
        self.assertTrue(os.path.isfile(os.path.join(call_dir, 'guard.log')))
        self.assertTrue(os.path.isfile(os.path.join(call_dir, 'meta.json')))
        self.assertTrue(os.path.isfile(os.path.join(call_dir, 'agy.prompt.md')))
        self.assertTrue(os.path.isfile(os.path.join(call_dir, 'agy.json')))
        self.assertTrue(os.path.isfile(os.path.join(call_dir, 'agy.err')))
        self.assertTrue(os.path.isfile(os.path.join(call_dir, 'agy.log')))

        # 驗收條件 7: meta.json 欄位齊全
        with open(os.path.join(call_dir, 'meta.json'), 'r', encoding='utf-8') as fp:
            meta = json.load(fp)

        expected_meta_fields = [
            'status', 'exit_code', 'lens', 'round', 'plan_file', 'plan_chars',
            'prompt_chars', 'requested_model', 'reported_model', 'reported_model_note',
            'agy_executable', 'agy_version', 'agy', 'repo', 'repo_snapshot_kind',
            'repo_changes', 'workspace_new_files', 'guard_denials', 'test_double',
            'started', 'finished', 'duration_s',
        ]
        for f in expected_meta_fields:
            self.assertIn(f, meta, f'Field {f!r} missing from meta.json')

        self.assertEqual(meta['status'], 'ok')
        self.assertEqual(meta['exit_code'], 0)
        self.assertEqual(meta['lens'], 'logic')
        self.assertEqual(meta['round'], 1)
        self.assertEqual(meta['reported_model_note'], 'agy 用戶端解析，伺服器端未確認')
        self.assertEqual(meta['repo_changes'], [])
        self.assertEqual(meta['workspace_new_files'], [])
        self.assertEqual(meta['guard_denials'], [])
        self.assertTrue(meta['test_double'])
        self.assertGreater(meta['plan_chars'], 0)
        self.assertGreater(meta['prompt_chars'], 0)
        self.assertIsInstance(meta['duration_s'], (int, float))

        # 驗收條件 6: 附錄標記之後的內容不在送給 agy 的 prompt 裡
        prompt_arg = call['argv'][call['argv'].index('-p') + 1]
        self.assertIn('User authentication system using JWT tokens.', prompt_arg)
        self.assertNotIn('This is confidential internal notes', prompt_arg)


class TestFacetReviewFailureStatuses(BaseFacetReviewTest):
    """驗收條件 1: timeout, agy_error (error/quota), empty_output, parse_error, schema_error."""

    def test_timeout(self):
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'gaps',
            '--round', '1',
            '--model', 'gemini-3.8-flash-high',
            '--run-dir', self.run_dir,
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args, scenario='timeout')
        self.assertEqual(proc.returncode, 2)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'timeout')
        self.assertIsNone(data['verdict'])
        self.assertIn('timeout', data['detail'].lower())

    def test_error(self):
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'verifiability',
            '--round', '1',
            '--model', 'gemini-3.8-flash-high',
            '--run-dir', self.run_dir,
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args, scenario='error')
        self.assertEqual(proc.returncode, 3)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'agy_error')
        self.assertIsNone(data['verdict'])

    def test_quota(self):
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'logic',
            '--round', '1',
            '--model', 'gemini-3.8-flash-high',
            '--run-dir', self.run_dir,
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args, scenario='quota')
        self.assertEqual(proc.returncode, 3)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'agy_error')
        self.assertIsNone(data['verdict'])
        self.assertIn('quota', data['detail'].lower())

    def test_no_struct(self):
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'logic',
            '--round', '1',
            '--model', 'gemini-3.8-flash-high',
            '--run-dir', self.run_dir,
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args, scenario='no_struct')
        self.assertEqual(proc.returncode, 4)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'empty_output')
        self.assertIsNone(data['verdict'])
        self.assertIn('structured_output', data['detail'])

    def test_schema_error(self):
        bad_verdict = dict(VALID_VERDICT)
        bad_verdict['verdict'] = 'INVALID_CHOICE'
        extra_env = {'FAKE_AGY_STRUCTURED': json.dumps(bad_verdict)}
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'logic',
            '--round', '1',
            '--model', 'gemini-3.8-flash-high',
            '--run-dir', self.run_dir,
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args, scenario='structured', extra_env=extra_env)
        self.assertEqual(proc.returncode, 5)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'schema_error')
        self.assertIsNone(data['verdict'])
        self.assertIn('enum', data['detail'])

    def test_parse_error(self):
        extra_env = {'FAKE_AGY_STRUCTURED': json.dumps('```json\n{broken json\n```')}
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'logic',
            '--round', '1',
            '--model', 'gemini-3.8-flash-high',
            '--run-dir', self.run_dir,
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args, scenario='structured', extra_env=extra_env)
        self.assertEqual(proc.returncode, 5)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'parse_error')
        self.assertIsNone(data['verdict'])
        self.assertIn('Failed to parse JSON', data['detail'])


class TestFacetReviewNoAgyInvocations(BaseFacetReviewTest):
    """驗收條件 1, 2: secret_suspected, plan_too_long, forbidden_flag, usage_error (不呼叫 agy)."""

    def test_secret_suspected(self):
        # 執行時字串相加組出假金鑰（機密規則）
        fake_secret = 'AIza' + 'Sy' + 'FakeTestingKeySecret1234567890'
        secret_plan = os.path.join(self.tmp.path, 'secret_plan.md')
        with open(secret_plan, 'w', encoding='utf-8', newline='\n') as f:
            f.write(f'# Secret Plan\nAPI_KEY = "{fake_secret}"\n')

        args = [
            '--plan-file', secret_plan,
            '--lens', 'logic',
            '--round', '1',
            '--model', 'gemini-3.8-flash-high',
            '--run-dir', self.run_dir,
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args)
        self.assertEqual(proc.returncode, 7)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'secret_suspected')
        self.assertIn('secret_hits', data)
        self.assertEqual(len(data['secret_hits']), 1)
        self.assertEqual(data['secret_hits'][0]['line'], 2)

        # 輸出不含完整金鑰
        self.assertNotIn(fake_secret, proc.stdout)
        self.assertNotIn(fake_secret, proc.stderr)

        # 未呼叫 agy
        self.assertEqual(len(self.get_recorded_calls()), 0)

    def test_plan_too_long(self):
        long_plan = os.path.join(self.tmp.path, 'long_plan.md')
        with open(long_plan, 'w', encoding='utf-8', newline='\n') as f:
            f.write('# Long Plan\n' + 'word ' * 8000)

        args = [
            '--plan-file', long_plan,
            '--lens', 'logic',
            '--round', '1',
            '--model', 'gemini-3.8-flash-high',
            '--run-dir', self.run_dir,
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args)
        self.assertEqual(proc.returncode, 9)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'plan_too_long')
        self.assertIn('limit is 30000', data['detail'])

        # 未呼叫 agy
        self.assertEqual(len(self.get_recorded_calls()), 0)

    def test_forbidden_model(self):
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'logic',
            '--round', '1',
            '--model', 'claude-3-opus',
            '--run-dir', self.run_dir,
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args)
        self.assertEqual(proc.returncode, 8)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'forbidden_flag')
        self.assertIn('gemini-', data['detail'])

        # 未呼叫 agy
        self.assertEqual(len(self.get_recorded_calls()), 0)

    def test_usage_error_missing_param(self):
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'logic',
            '--round', '1',
            # missing --model
            '--run-dir', self.run_dir,
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args)
        self.assertEqual(proc.returncode, 10)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'usage_error')
        self.assertEqual(len(self.get_recorded_calls()), 0)

    def test_usage_error_wrong_lens(self):
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'security',  # prompt.LENSES does not have 'security'
            '--round', '1',
            '--model', 'gemini-3.8-flash-high',
            '--run-dir', self.run_dir,
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args)
        self.assertEqual(proc.returncode, 10)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'usage_error')
        self.assertIn('unknown lens', data['detail'])
        self.assertEqual(len(self.get_recorded_calls()), 0)

    def test_usage_error_plan_not_found(self):
        args = [
            '--plan-file', os.path.join(self.tmp.path, 'missing_plan.md'),
            '--lens', 'logic',
            '--round', '1',
            '--model', 'gemini-3.8-flash-high',
            '--run-dir', self.run_dir,
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args)
        self.assertEqual(proc.returncode, 10)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'usage_error')
        self.assertIn('plan file not found', data['detail'])
        self.assertEqual(len(self.get_recorded_calls()), 0)


class TestFacetReviewWorkspaceModified(BaseFacetReviewTest):
    """驗收條件 4: workspace_modified 優先於其他 status (ws_write, git repo, plain dir)."""

    def test_workspace_modified_ws_write_preempts_ok(self):
        extra_env = {'FAKE_AGY_STRUCTURED': json.dumps(VALID_VERDICT)}
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'logic',
            '--round', '1',
            '--model', 'gemini-3.8-flash-high',
            '--run-dir', self.run_dir,
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args, scenario='ws_write', extra_env=extra_env)
        self.assertEqual(proc.returncode, 6)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'workspace_modified')
        # 即使被改動，合法的 verdict 仍保留在欄位中
        self.assertEqual(data['verdict'], 'APPROVED')
        self.assertEqual(data['workspace_new_files'], ['probe.txt'])
        self.assertEqual(data['repo_changes'], [])

    def test_workspace_modified_touch_git_repo(self):
        # 建立 git repo
        git_root = os.path.join(self.tmp.path, 'git_root')
        os.makedirs(git_root, exist_ok=True)
        repo_path, _ = helpers.make_repo(git_root, files={'calc.py': 'def add(a, b): return a + b\n'})

        target_file = os.path.join(repo_path, 'calc.py')
        extra_env = {
            'FAKE_AGY_STRUCTURED': json.dumps(VALID_VERDICT),
            'FAKE_AGY_TOUCH': target_file,
        }
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'logic',
            '--round', '1',
            '--model', 'gemini-3.8-flash-high',
            '--run-dir', self.run_dir,
            '--repo', repo_path,
        ]
        proc = self.run_review(args, scenario='structured', extra_env=extra_env)
        self.assertEqual(proc.returncode, 6)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'workspace_modified')
        self.assertIn('calc.py', data['repo_changes'])

    def test_workspace_modified_touch_plain_folder(self):
        plain_repo = os.path.join(self.tmp.path, 'plain_repo')
        os.makedirs(plain_repo, exist_ok=True)
        file_path = os.path.join(plain_repo, 'notes.txt')
        with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write('initial note\n')

        extra_env = {
            'FAKE_AGY_STRUCTURED': json.dumps(VALID_VERDICT),
            'FAKE_AGY_TOUCH': file_path,
        }
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'logic',
            '--round', '1',
            '--model', 'gemini-3.8-flash-high',
            '--run-dir', self.run_dir,
            '--repo', plain_repo,
        ]
        proc = self.run_review(args, scenario='structured', extra_env=extra_env)
        self.assertEqual(proc.returncode, 6)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'workspace_modified')
        self.assertIn('notes.txt', data['repo_changes'])


class TestFacetReviewRound2(BaseFacetReviewTest):
    """驗收條件 5: 第二輪處置、schema resolved 必填與 verdict 驗證."""

    def test_round2_missing_prior_stdin_flag(self):
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'logic',
            '--round', '2',
            '--model', 'gemini-3.8-flash-high',
            '--run-dir', self.run_dir,
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args)
        self.assertEqual(proc.returncode, 10)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'usage_error')
        self.assertIn('Round 2 or later requires prior findings', data['detail'])
        self.assertEqual(len(self.get_recorded_calls()), 0)

    def test_round2_prior_invalid_json(self):
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'logic',
            '--round', '2',
            '--model', 'gemini-3.8-flash-high',
            '--run-dir', self.run_dir,
            '--repo', self.repo_dir,
            '--prior-stdin',
        ]
        proc = self.run_review(args, input_text='not valid json {')
        self.assertEqual(proc.returncode, 10)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'usage_error')
        self.assertIn('failed to read/parse prior from stdin', data['detail'])
        self.assertEqual(len(self.get_recorded_calls()), 0)

    def test_round2_ok_with_resolved(self):
        prior_data = {
            'changes_summary': 'Addressed previous comments on token expiration.',
            'prior_findings': [
                {
                    'id': 'F-1',
                    'severity': 'medium',
                    'issue': 'Token expiration not configured',
                    'disposition': 'accepted',
                    'reason': 'Configured 15 minutes',
                }
            ],
        }
        round2_verdict = dict(VALID_VERDICT)
        round2_verdict['resolved'] = [
            {
                'id': 'F-1',
                'status': 'resolved',
                'note': 'Token expiration configured properly.',
            }
        ]
        extra_env = {'FAKE_AGY_STRUCTURED': json.dumps(round2_verdict)}
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'logic',
            '--round', '2',
            '--model', 'gemini-3.8-flash-high',
            '--run-dir', self.run_dir,
            '--repo', self.repo_dir,
            '--prior-stdin',
        ]
        proc = self.run_review(args, input_text=json.dumps(prior_data), scenario='structured', extra_env=extra_env)
        self.assertEqual(proc.returncode, 0, f'Expected 0, got {proc.returncode}: {proc.stderr}')
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(len(data['resolved']), 1)
        self.assertEqual(data['resolved'][0]['id'], 'F-1')

        # 檢查 call 目錄的 prior.json 與 schema.json
        call_dir = os.path.join(self.run_dir, 'r2-logic')
        prior_path = os.path.join(call_dir, 'prior.json')
        schema_path = os.path.join(call_dir, 'schema.json')
        self.assertTrue(os.path.isfile(prior_path))
        self.assertTrue(os.path.isfile(schema_path))

        with open(schema_path, 'r', encoding='utf-8') as fp:
            schema_data = json.load(fp)
        self.assertIn('resolved', schema_data.get('required', []))

    def test_round2_verdict_missing_resolved(self):
        prior_data = {
            'changes_summary': 'Updated auth spec.',
            'prior_findings': [
                {
                    'id': 'F-1',
                    'severity': 'medium',
                    'issue': 'Token expiration not configured',
                    'disposition': 'accepted',
                    'reason': 'Configured 15 minutes',
                }
            ],
        }
        # VALID_VERDICT 沒有 resolved
        extra_env = {'FAKE_AGY_STRUCTURED': json.dumps(VALID_VERDICT)}
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'logic',
            '--round', '2',
            '--model', 'gemini-3.8-flash-high',
            '--run-dir', self.run_dir,
            '--repo', self.repo_dir,
            '--prior-stdin',
        ]
        proc = self.run_review(args, input_text=json.dumps(prior_data), scenario='structured', extra_env=extra_env)
        self.assertEqual(proc.returncode, 5)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'schema_error')
        self.assertIn('resolved', data['detail'])


class TestFacetReviewSessionAndRunDir(BaseFacetReviewTest):
    """驗收條件 7: session 與 run-dir 解析 (abc-1, CLAUDE_SESSION_ID, manual, ../x)."""

    def test_explicit_session_without_run_dir(self):
        env_override = {
            'TEMP': self.tmp.path,
            'TMP': self.tmp.path,
            'TMPDIR': self.tmp.path,
            'FAKE_AGY_STRUCTURED': json.dumps(VALID_VERDICT),
        }
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'logic',
            '--round', '1',
            '--model', 'gemini-3.8-flash-high',
            '--session', 'abc-1',
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args, scenario='structured', extra_env=env_override)
        self.assertEqual(proc.returncode, 0)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        expected_prefix = os.path.join(self.tmp.path, 'rgs-facet', 'abc-1')
        self.assertTrue(
            os.path.normpath(data['raw_dir']).startswith(os.path.normpath(expected_prefix)),
            f"Expected raw_dir to start with {expected_prefix}, got {data['raw_dir']}",
        )

    def test_session_from_env_without_run_dir(self):
        env_override = {
            'TEMP': self.tmp.path,
            'TMP': self.tmp.path,
            'TMPDIR': self.tmp.path,
            'CLAUDE_SESSION_ID': 'env-sess-99',
            'FAKE_AGY_STRUCTURED': json.dumps(VALID_VERDICT),
        }
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'logic',
            '--round', '1',
            '--model', 'gemini-3.8-flash-high',
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args, scenario='structured', extra_env=env_override)
        self.assertEqual(proc.returncode, 0)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        expected_prefix = os.path.join(self.tmp.path, 'rgs-facet', 'env-sess-99')
        self.assertTrue(
            os.path.normpath(data['raw_dir']).startswith(os.path.normpath(expected_prefix)),
            f"Expected raw_dir to start with {expected_prefix}, got {data['raw_dir']}",
        )

    def test_default_manual_session_without_run_dir(self):
        env_override = {
            'TEMP': self.tmp.path,
            'TMP': self.tmp.path,
            'TMPDIR': self.tmp.path,
            'CLAUDE_SESSION_ID': '',
            'FAKE_AGY_STRUCTURED': json.dumps(VALID_VERDICT),
        }
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'logic',
            '--round', '1',
            '--model', 'gemini-3.8-flash-high',
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args, scenario='structured', extra_env=env_override)
        self.assertEqual(proc.returncode, 0)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        expected_prefix = os.path.join(self.tmp.path, 'rgs-facet', 'manual')
        self.assertTrue(
            os.path.normpath(data['raw_dir']).startswith(os.path.normpath(expected_prefix)),
            f"Expected raw_dir to start with {expected_prefix}, got {data['raw_dir']}",
        )

    def test_invalid_session_traversal(self):
        args = [
            '--plan-file', self.plan_file,
            '--lens', 'logic',
            '--round', '1',
            '--model', 'gemini-3.8-flash-high',
            '--session', '../x',
            '--repo', self.repo_dir,
        ]
        proc = self.run_review(args)
        self.assertEqual(proc.returncode, 10)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data['status'], 'usage_error')
        self.assertIn('invalid session', data['detail'])
        self.assertEqual(len(self.get_recorded_calls()), 0)


if __name__ == '__main__':
    unittest.main()
