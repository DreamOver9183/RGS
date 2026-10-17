import json
import os
import re
import shutil
import subprocess
import time
import unittest

from helpers import FAKE_AGY, TempDir, calls, git, make_repo, write

import rgs_common as rc


def pid_exists(pid):
    if os.name == 'nt':
        res = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'],
                             capture_output=True, text=True, stdin=subprocess.DEVNULL)
        for line in res.stdout.splitlines():
            if any(part == str(pid) for part in line.strip().split()):
                return True
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True


def kill_pid(pid):
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'],
                       capture_output=True, stdin=subprocess.DEVNULL)
    else:
        import signal
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


class CheckAgyArgsTest(unittest.TestCase):
    def test_forbidden_always_rejected_for_both_roles(self):
        for flag in rc.FORBIDDEN_ALWAYS:
            for role in ('implementer', 'reviewer'):
                with self.assertRaises(rc.RgsError) as ctx:
                    rc.check_agy_args([flag], role, 'gemini-3.8-flash-high')
                self.assertEqual(ctx.exception.code, 2)
                self.assertIn(flag, str(ctx.exception))

    def test_forbidden_always_with_equals(self):
        for role in ('implementer', 'reviewer'):
            with self.assertRaises(rc.RgsError) as ctx:
                rc.check_agy_args(['--sandbox=true'], role, 'gemini-3.8-flash-high')
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn('--sandbox', str(ctx.exception))

    def test_forbidden_for_reviewer(self):
        for flag in rc.FORBIDDEN_FOR_REVIEWER:
            with self.assertRaises(rc.RgsError) as ctx:
                rc.check_agy_args([flag], 'reviewer', 'gemini-3.8-flash-high')
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn(flag, str(ctx.exception))

    def test_implementer_allowed_and_forbidden_flags(self):
        # Allowed for implementer
        rc.check_agy_args(['--mode', 'accept-edits'], 'implementer', 'gemini-3.8-flash-high')
        rc.check_agy_args(['--conversation', 'conv-123'], 'implementer', 'gemini-3.8-flash-high')
        rc.check_agy_args(['--add-dir', 'src'], 'implementer', 'gemini-3.8-flash-high')

        # Rejected modes for implementer
        with self.assertRaises(rc.RgsError) as ctx:
            rc.check_agy_args(['--mode', 'auto'], 'implementer', 'gemini-3.8-flash-high')
        self.assertEqual(ctx.exception.code, 2)
        self.assertTrue('--mode' in str(ctx.exception) or 'auto' in str(ctx.exception))

        with self.assertRaises(rc.RgsError) as ctx:
            rc.check_agy_args(['--mode=plan'], 'implementer', 'gemini-3.8-flash-high')
        self.assertEqual(ctx.exception.code, 2)
        self.assertTrue('--mode' in str(ctx.exception) or 'plan' in str(ctx.exception))

    def test_prompt_content_not_mistaken_for_flags(self):
        rc.check_agy_args(['-p', 'please do not use --yolo or --sandbox'], 'reviewer', 'gemini-3.8-flash-high')
        rc.check_agy_args(['-p', '--dangerously-skip-permissions'], 'implementer', 'gemini-3.8-flash-high')

    def test_model_validation(self):
        for bad_model in (None, '', 'claude-opus-5-5', 'Gemini-4'):
            with self.assertRaises(rc.RgsError) as ctx:
                rc.check_agy_args([], 'reviewer', bad_model)
            self.assertEqual(ctx.exception.code, 2)
            if bad_model is not None:
                self.assertIn(str(bad_model), str(ctx.exception))

        # Valid model passes
        rc.check_agy_args([], 'reviewer', 'gemini-3.8-flash-high')

    def test_unknown_role(self):
        with self.assertRaises(rc.RgsError) as ctx:
            rc.check_agy_args([], 'admin', 'gemini-3.8-flash-high')
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn('admin', str(ctx.exception))


class CallAgyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        os.environ['RGS_AGY'] = FAKE_AGY
        os.environ['FAKE_AGY_DIR'] = os.path.join(self.tmp.path, 'state')
        self.schema = os.path.join(self.tmp.path, 'schema.json')
        write(self.schema, json.dumps({'type': 'object', 'properties': {'verdict': {}, 'findings': {}}}))

    def tearDown(self):
        for key in ('RGS_AGY', 'FAKE_AGY_DIR', 'FAKE_AGY_SCENARIO', 'FAKE_AGY_QUOTA_MODEL', 'FAKE_AGY_LABEL'):
            os.environ.pop(key, None)
        self.tmp.cleanup()

    def call(self, scenario, **kw):
        os.environ['FAKE_AGY_SCENARIO'] = scenario
        kw.setdefault('model', 'gemini-test-1')
        return rc.call_agy(prompt='hi', cwd=self.tmp.path, timeout_s=30, **kw)

    def test_text_success(self):
        result = self.call('ok')
        self.assertEqual(result.kind, 'ok')
        self.assertEqual(result.response, 'done')

    def test_structured_success(self):
        result = self.call('ok', schema_path=self.schema)
        self.assertTrue(result.ok)
        self.assertEqual(result.structured['verdict'], 'PASS')

    def test_timeout_reported_as_success_is_not_ok(self):
        result = self.call('timeout')
        self.assertEqual(result.kind, 'timeout')
        self.assertEqual(rc.exit_code_for(result), rc.EXIT_NO_RESULT)

    def test_error_status_even_with_pass_text(self):
        self.assertEqual(self.call('error').kind, 'error')

    def test_quota(self):
        result = self.call('quota')
        self.assertEqual(result.kind, 'quota')
        self.assertEqual(rc.exit_code_for(result), rc.EXIT_QUOTA)

    def test_missing_structured_output(self):
        self.assertEqual(self.call('no_struct', schema_path=self.schema).kind, 'empty')

    def test_fallback_to_next_model_on_quota(self):
        os.environ['FAKE_AGY_SCENARIO'] = 'quota_model'
        os.environ['FAKE_AGY_QUOTA_MODEL'] = 'gemini-test-1'
        result = rc.call_with_fallback(['gemini-test-1', 'gemini-test-2'], prompt='hi', cwd=self.tmp.path, timeout_s=30)
        self.assertTrue(result.ok)
        self.assertEqual(result.model, 'gemini-test-2')
        self.assertEqual(result.tried, [('gemini-test-1', 'quota'), ('gemini-test-2', 'ok')])

    def test_saves_raw_output(self):
        prefix = os.path.join(self.tmp.path, 'out', 'run')
        self.call('ok', save_as=prefix)
        for ext in ('.json', '.err', '.prompt.md', '.log'):
            self.assertTrue(os.path.exists(prefix + ext), ext)

    def test_invalid_model_raises_and_does_not_call_agy(self):
        with self.assertRaises(rc.RgsError) as ctx:
            rc.call_agy(prompt='hi', cwd=self.tmp.path, model='claude-opus-5-5')
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn('claude-opus-5-5', str(ctx.exception))
        calls_dir = os.path.join(self.tmp.path, 'state', 'calls')
        self.assertTrue(not os.path.exists(calls_dir) or len(os.listdir(calls_dir)) == 0)

    def test_role_and_mode_permissions(self):
        with self.assertRaises(rc.RgsError) as ctx:
            self.call('ok', role='reviewer', mode='accept-edits')
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn('--mode', str(ctx.exception))
        self.assertIn('reviewer', str(ctx.exception))

        result = self.call('ok', role='implementer', mode='accept-edits')
        self.assertTrue(result.ok)

    def test_log_file_arg_passed(self):
        self.call('ok')
        calls_list = calls(os.path.join(self.tmp.path, 'state'))
        self.assertTrue(len(calls_list) > 0)
        self.assertIn('--log-file', calls_list[0]['argv'])

    def test_reported_model_scenarios(self):
        # Default Fake <model>
        res1 = self.call('ok')
        self.assertEqual(res1.reported_model, 'Fake gemini-test-1')
        self.assertEqual(res1.summary()['reported_model'], 'Fake gemini-test-1')

        # FAKE_AGY_LABEL specified
        os.environ['FAKE_AGY_LABEL'] = 'Gemini 4 Argon (High)'
        res2 = self.call('ok')
        self.assertEqual(res2.reported_model, 'Gemini 4 Argon (High)')
        self.assertEqual(res2.summary()['reported_model'], 'Gemini 4 Argon (High)')

        # FAKE_AGY_LABEL empty string
        os.environ['FAKE_AGY_LABEL'] = ''
        res3 = self.call('ok')
        self.assertIsNone(res3.reported_model)
        self.assertIsNone(res3.summary()['reported_model'])

    def test_log_file_retention_and_cleanup(self):
        state_dir = os.path.join(self.tmp.path, 'state')
        prefix = os.path.join(self.tmp.path, 'saved_run')
        self.call('ok', save_as=prefix)
        dest_log = prefix + '.log'
        self.assertTrue(os.path.exists(dest_log))
        with open(dest_log, encoding='utf-8') as f:
            self.assertIn('label="Fake gemini-test-1"', f.read())

        call1 = calls(state_dir)[-1]
        temp_log1 = call1['argv'][call1['argv'].index('--log-file') + 1]
        norm_temp1 = os.path.normcase(os.path.abspath(temp_log1))
        norm_dest = os.path.normcase(os.path.abspath(dest_log))
        norm_tmp = os.path.normcase(os.path.abspath(self.tmp.path))

        self.assertNotEqual(norm_temp1, norm_dest)
        self.assertFalse(norm_temp1.startswith(norm_tmp + os.sep) or norm_temp1 == norm_tmp)
        self.assertFalse(os.path.exists(temp_log1))

        self.call('ok')
        call2 = calls(state_dir)[-1]
        temp_log2 = call2['argv'][call2['argv'].index('--log-file') + 1]
        self.assertFalse(os.path.exists(temp_log2))


class ReportedModelFromLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_reported_model_returns_last_label(self):
        path = os.path.join(self.tmp.path, 'multi_labels.log')
        content = (
            'I1017 00:00:00.000000 1 model.go:1] Propagating: label="A"\n'
            'Some irrelevant log text without label\n'
            'I1017 00:00:01.000000 1 model.go:2] Propagating: label="B (High)"\n'
            'I1017 00:00:02.000000 1 model.go:3] Propagating: label="C"\n'
        )
        write(path, content)
        self.assertEqual(rc.reported_model_from_log(path), 'C')

    def test_reported_model_no_label(self):
        path = os.path.join(self.tmp.path, 'no_label.log')
        write(path, 'Some irrelevant log text\nAnother line without label\n')
        self.assertIsNone(rc.reported_model_from_log(path))

    def test_reported_model_nonexistent_path(self):
        self.assertIsNone(rc.reported_model_from_log(os.path.join(self.tmp.path, 'nonexistent.log')))

    def test_reported_model_none_and_empty_path(self):
        self.assertIsNone(rc.reported_model_from_log(None))
        self.assertIsNone(rc.reported_model_from_log(''))


class KillTreeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.state = os.path.join(self.tmp.path, 'state')
        os.makedirs(self.state, exist_ok=True)
        os.environ['RGS_AGY'] = FAKE_AGY
        os.environ['FAKE_AGY_DIR'] = self.state
        os.environ['FAKE_AGY_SCENARIO'] = 'sleep_child'
        self.pids = {}

    def tearDown(self):
        for key in ('RGS_AGY', 'FAKE_AGY_DIR', 'FAKE_AGY_SCENARIO', 'FAKE_AGY_LABEL'):
            os.environ.pop(key, None)
        for p in (self.pids.get('child'), self.pids.get('parent')):
            if p and pid_exists(p):
                kill_pid(p)
        self.tmp.cleanup()

    def test_kill_tree_terminates_parent_and_child(self):
        started = time.time()
        result = rc.call_agy(prompt='hi', cwd=self.tmp.path, model='gemini-test-1',
                             timeout_s=1, grace_s=2)
        elapsed = time.time() - started
        self.assertEqual(result.kind, 'timeout')
        self.assertEqual(result.reported_model, 'Fake gemini-test-1')
        self.assertEqual(result.summary()['reported_model'], 'Fake gemini-test-1')
        self.assertLess(elapsed, 30)

        pids_file = os.path.join(self.state, 'pids.json')
        self.assertTrue(os.path.exists(pids_file))
        with open(pids_file, encoding='utf-8') as f:
            self.pids = json.load(f)
        parent_pid = self.pids['parent']
        child_pid = self.pids['child']

        deadline = time.time() + 10
        parent_dead = False
        child_dead = False
        while time.time() < deadline:
            if not parent_dead and not pid_exists(parent_pid):
                parent_dead = True
            if not child_dead and not pid_exists(child_pid):
                child_dead = True
            if parent_dead and child_dead:
                break
            time.sleep(0.5)

        self.assertTrue(parent_dead, f"parent process {parent_pid} still running")
        self.assertTrue(child_dead, f"child process {child_pid} still running")


class HelpersTest(unittest.TestCase):
    def test_parse_allowed_files(self):
        spec = ('# 任務\n\n## 可修改的檔案\n\n- `src/a.py`\n- `tests/test_*.py`：新增\n\n'
                '## 驗收條件\n\n- `not/this.py`\n')
        self.assertEqual(rc.parse_allowed_files(spec), ['src/a.py', 'tests/test_*.py'])

    def test_parse_allowed_files_english(self):
        spec = '### Files you may change\n* `app/x.kt`\n'
        self.assertEqual(rc.parse_allowed_files(spec), ['app/x.kt'])

    def test_match_any(self):
        self.assertTrue(rc.match_any('docs/rgs/specs/M1.md', ['docs/rgs/**']))
        self.assertTrue(rc.match_any('sub/local.properties', ['local.properties']))
        self.assertTrue(rc.match_any('RimTaiName_KEY_01.txt', ['*_KEY_*']))
        self.assertFalse(rc.match_any('src/app.py', ['tests/*.py']))

    def test_decode_output_utf8_and_ansi_code_page(self):
        text = '驗收條件 1 ... ok'
        self.assertEqual(rc.decode_output(text.encode('utf-8')), text)
        # Python children on a zh-TW Windows write piped output in cp950, not UTF-8.
        import locale
        encoding = locale.getencoding() if hasattr(locale, 'getencoding') else locale.getpreferredencoding(False)
        try:
            raw = text.encode(encoding)
        except (LookupError, UnicodeEncodeError):
            self.skipTest(f'the ANSI code page {encoding} cannot encode the sample')
        if raw == text.encode('utf-8'):
            self.skipTest('the ANSI code page is UTF-8 here')
        self.assertEqual(rc.decode_output(raw), text)

    def test_find_gh_override(self):
        os.environ['RGS_GH'] = 'fake_gh.py'
        try:
            self.assertEqual(rc.find_gh()[1:], ['fake_gh.py'])
        finally:
            os.environ.pop('RGS_GH')

    def test_render_template_fills_placeholders(self):
        text = rc.render_template('prompts/fix.md', fix='F', rules='R', extra_allowed='')
        self.assertIn('`F`', text)
        self.assertNotIn('{{', text)


class IsolatedWorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.created = []

    def tearDown(self):
        for path in self.created:
            if os.path.exists(path):
                def onerror(func, p, _):
                    os.chmod(p, 0o700)
                    func(p)
                shutil.rmtree(path, onerror=onerror)
        self.tmp.cleanup()

    def test_isolated_workspace_sealed(self):
        ws = rc.isolated_workspace(prefix='test_sealed_', files={'hello.txt': 'world'}, sealed=True)
        self.created.append(ws)
        guard_json = os.path.join(ws, '.agents', 'rgs-guard.json')
        self.assertTrue(os.path.exists(guard_json))
        with open(guard_json, encoding='utf-8') as f:
            policy = json.load(f)
        self.assertEqual(policy['role'], 'sealed')
        content_file = os.path.join(ws, 'hello.txt')
        self.assertTrue(os.path.exists(content_file))
        with open(content_file, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'world')

    def test_isolated_workspace_default_is_reviewer(self):
        ws = rc.isolated_workspace(prefix='test_reviewer_', files={'notes.txt': 'data'})
        self.created.append(ws)
        guard_json = os.path.join(ws, '.agents', 'rgs-guard.json')
        self.assertTrue(os.path.exists(guard_json))
        with open(guard_json, encoding='utf-8') as f:
            policy = json.load(f)
        self.assertEqual(policy['role'], 'reviewer')
        content_file = os.path.join(ws, 'notes.txt')
        self.assertTrue(os.path.exists(content_file))
        with open(content_file, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'data')


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.folder = os.path.join(self.tmp.path, 'files_folder')
        os.makedirs(self.folder)
        write(os.path.join(self.folder, 'f1.txt'), 'content1')
        write(os.path.join(self.folder, 'f2.txt'), 'content2')
        profile = {'knowledge_base': ['CLAUDE.md'], 'commands': {'quick': ['true'], 'verify': ['true']}}
        repo_root = os.path.join(self.tmp.path, 'repo_root')
        os.makedirs(repo_root)
        self.repo, _ = make_repo(repo_root, profile)

    def tearDown(self):
        self.tmp.cleanup()

    def test_files_no_changes_same_digest(self):
        s1 = rc.snapshot(self.folder)
        self.assertEqual(s1['kind'], 'files')
        s2 = rc.snapshot(self.folder)
        self.assertEqual(s1['digest'], s2['digest'])
        self.assertEqual(rc.snapshot_changes(s1, s2), [])

    def test_files_added(self):
        s1 = rc.snapshot(self.folder)
        write(os.path.join(self.folder, 'f3.txt'), 'content3')
        s2 = rc.snapshot(self.folder)
        self.assertNotEqual(s1['digest'], s2['digest'])
        self.assertEqual(rc.snapshot_changes(s1, s2), ['f3.txt'])

    def test_files_deleted(self):
        s1 = rc.snapshot(self.folder)
        os.remove(os.path.join(self.folder, 'f2.txt'))
        s2 = rc.snapshot(self.folder)
        self.assertNotEqual(s1['digest'], s2['digest'])
        self.assertEqual(rc.snapshot_changes(s1, s2), ['f2.txt'])

    def test_files_modified_size_changed(self):
        s1 = rc.snapshot(self.folder)
        write(os.path.join(self.folder, 'f1.txt'), 'longer_content')
        s2 = rc.snapshot(self.folder)
        self.assertNotEqual(s1['digest'], s2['digest'])
        self.assertEqual(rc.snapshot_changes(s1, s2), ['f1.txt'])

    def test_files_modified_mtime_changed(self):
        path = os.path.join(self.folder, 'f1.txt')
        s1 = rc.snapshot(self.folder)
        st = os.stat(path)
        new_mtime = st.st_mtime + 50
        os.utime(path, (new_mtime, new_mtime))
        s2 = rc.snapshot(self.folder)
        self.assertNotEqual(s1['digest'], s2['digest'])
        self.assertEqual(rc.snapshot_changes(s1, s2), ['f1.txt'])

    def test_files_ignore(self):
        write(os.path.join(self.folder, '.agents', 'hooks.json'), '{}')
        s1 = rc.snapshot(self.folder, ignore=('.agents/**',))
        self.assertNotIn('.agents/hooks.json', s1['entries'])
        write(os.path.join(self.folder, '.agents', 'rgs-guard.json'), '{}')
        s2 = rc.snapshot(self.folder, ignore=('.agents/**',))
        self.assertEqual(s1['digest'], s2['digest'])
        self.assertEqual(rc.snapshot_changes(s1, s2), [])

    def test_files_git_folder_skipped(self):
        git_dir = os.path.join(self.folder, '.git')
        os.makedirs(git_dir)
        write(os.path.join(git_dir, 'config'), 'dummy')
        s = rc.snapshot(self.folder)
        self.assertTrue(all(not k.startswith('.git') for k in s['entries']))

    def test_git_no_changes(self):
        s1 = rc.snapshot(self.repo)
        self.assertEqual(s1['kind'], 'git')
        s2 = rc.snapshot(self.repo)
        self.assertEqual(s1['digest'], s2['digest'])
        self.assertEqual(rc.snapshot_changes(s1, s2), [])

    def test_git_modified_tracked(self):
        s1 = rc.snapshot(self.repo)
        write(os.path.join(self.repo, 'calc.py'), 'def add(a, b):\n    return a + b + 1\n')
        s2 = rc.snapshot(self.repo)
        self.assertEqual(rc.snapshot_changes(s1, s2), ['calc.py'])

    def test_git_untracked_file(self):
        s1 = rc.snapshot(self.repo)
        write(os.path.join(self.repo, 'new_script.py'), 'print("hi")\n')
        s2 = rc.snapshot(self.repo)
        self.assertEqual(rc.snapshot_changes(s1, s2), ['new_script.py'])

    def test_git_deleted_tracked(self):
        s1 = rc.snapshot(self.repo)
        os.remove(os.path.join(self.repo, 'calc.py'))
        s2 = rc.snapshot(self.repo)
        self.assertEqual(rc.snapshot_changes(s1, s2), ['calc.py'])

    def test_git_already_modified_modified_again(self):
        write(os.path.join(self.repo, 'calc.py'), 'def add(a, b):\n    return a + b + 10\n')
        s1 = rc.snapshot(self.repo)
        write(os.path.join(self.repo, 'calc.py'), 'def add(a, b):\n    return a + b + 20\n')
        s2 = rc.snapshot(self.repo)
        self.assertNotEqual(s1['digest'], s2['digest'])
        self.assertEqual(rc.snapshot_changes(s1, s2), ['calc.py'])

    def test_git_new_commit_moves_head(self):
        s1 = rc.snapshot(self.repo)
        git(['commit', '--allow-empty', '-m', 'new commit'], self.repo)
        s2 = rc.snapshot(self.repo)
        changes = rc.snapshot_changes(s1, s2)
        self.assertIn('<HEAD>', changes)

    def test_snapshot_changes_incompatible_raises_rgs_error(self):
        s_git = rc.snapshot(self.repo)
        other_dir = os.path.join(self.tmp.path, 'other')
        os.makedirs(other_dir)
        s_file = rc.snapshot(other_dir)
        with self.assertRaises(rc.RgsError) as cm:
            rc.snapshot_changes(s_git, s_file)
        self.assertIn('cannot compare snapshots with different kind or root', str(cm.exception))
        another_dir = os.path.join(self.tmp.path, 'another')
        os.makedirs(another_dir)
        s_file2 = rc.snapshot(another_dir)
        with self.assertRaises(rc.RgsError) as cm:
            rc.snapshot_changes(s_file, s_file2)
        self.assertIn('cannot compare snapshots with different kind or root', str(cm.exception))


if __name__ == '__main__':
    unittest.main()
