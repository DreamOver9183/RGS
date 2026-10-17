"""End-to-end runs of rgs.py and review.py against a temp repo with a bare remote and the fake agy."""
import json
import os
import re
import unittest

from helpers import TempDir, calls, git, make_repo, run_script, write

PROFILE = {
    'knowledge_base': ['CLAUDE.md'],
    'shell': 'bash',
    'commands': {'quick': ['python -c "import calc"'], 'verify': ['python -c "print(42)"']},
    'agy': {'implementer': {'models': ['m-impl']}, 'reviewer': {'models': ['m-review']}},
}
SPEC = """# 任務：加上 sub

## 目標

新增 sub。

## 可修改的檔案

- `calc.py`

## 驗收條件

- sub(3, 1) == 2
"""


class FlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.repo, self.remote = make_repo(self.tmp.path, PROFILE)
        self.state = os.path.join(self.tmp.path, 'fake')
        self.env = {'FAKE_AGY_DIR': self.state, 'FAKE_AGY_WRITE': 'calc.py'}
        self.spec = os.path.join(self.tmp.path, 'spec.md')
        write(self.spec, SPEC)

    def tearDown(self):
        self.tmp.cleanup()

    def rgs(self, *args, scenario='implement', env=None):
        return run_script('rgs.py', list(args), self.repo, scenario, {**self.env, **(env or {})})

    def prepare(self, task='t1'):
        code, data, out = self.rgs('prepare', '--task', task, '--spec', self.spec)
        self.assertEqual(code, 0, out)
        return data

    def assert_agy_saw_only_the_worktree(self, label, in_prompt):
        """implement/fix: agy gets paths in the task worktree only; the run dir keeps a copy of every input."""
        call = calls(self.state)[-1]
        argv, prompt = call['argv'], call['argv'][1]
        wt = os.path.join(self.tmp.path, 'repo.rgs', 't1')
        io = os.path.join(wt, '.rgs-task')
        self.assertEqual(os.path.normcase(call['cwd']), os.path.normcase(wt))
        for name in in_prompt:
            self.assertIn(f'`{os.path.join(io, name)}`', prompt)
        self.assertNotIn('--add-dir', argv)
        self.assertEqual(call['missing_paths'], [])
        self.assertEqual([os.path.normcase(r) for r in call['guard']['roots']], [os.path.normcase(wt)])
        with open(os.path.join(io, 'implementer-rules.md'), encoding='utf-8') as f:
            rules = f.read()
        # repo.rgs/ also starts with "repo", so look for the main checkout as a whole folder name.
        top = git(['rev-parse', '--show-toplevel'], self.repo)
        roots = {p.replace('\\', '/').rstrip('/').lower() for p in (self.repo, top)}
        for text in [*argv, call['cwd'], rules]:
            text = text.replace('\\', '/').lower()
            for root in roots:
                self.assertIsNone(re.search(re.escape(root) + r'(?![\w.-])', text), text[:300])
        rd = os.path.join(self.repo, '.rgs', 'runs', 't1')
        for name in [*in_prompt, 'spec.md', 'implementer-rules.md', f'{label}.prompt.md', f'{label}.guard.log']:
            self.assertTrue(os.path.isfile(os.path.join(rd, name)), name)

    def test_main_flow_lands_on_remote(self):
        data = self.prepare()
        wt = data['worktree']
        self.assertTrue(os.path.exists(os.path.join(wt, '.agents', 'rgs-guard.json')))
        self.assertEqual(data['allowed'], ['calc.py'])

        code, data, out = self.rgs('implement', '--task', 't1')
        self.assertEqual(code, 0, out)
        self.assertEqual(data['scope']['changed'], ['calc.py'])
        first = calls(self.state)[-1]['argv']
        self.assertIn('accept-edits', first)
        self.assertNotIn('--conversation', first)
        self.assert_agy_saw_only_the_worktree('implement', ['implementer-rules.md', 'spec.md'])

        notes = os.path.join(self.tmp.path, 'fix.md')
        write(notes, '1. calc.py: rename\n')
        code, data, out = self.rgs('fix', '--task', 't1', '--notes', notes)
        self.assertEqual(code, 0, out)
        self.assertEqual(data['round'], 1)
        self.assertFalse(data['fresh_conversation'])
        self.assertIn('--conversation', calls(self.state)[-1]['argv'])
        self.assert_agy_saw_only_the_worktree('fix-1', ['fix-1.md', 'implementer-rules.md'])

        code, data, out = self.rgs('check', '--task', 't1', '--level', 'all')
        self.assertEqual(code, 0, out)

        msg = os.path.join(self.tmp.path, 'msg.txt')
        write(msg, 'feat(calc): add sub\n')
        code, data, out = self.rgs('land', '--task', 't1', '--message-file', msg)
        self.assertEqual(code, 0, out)
        self.assertTrue(data['landed'])
        self.assertTrue(data['worktree_removed'])
        self.assertTrue(data['main_checkout_synced'])
        self.assertEqual(git(['rev-parse', 'main'], self.remote), data['commit'])
        self.assertEqual(git(['log', '-1', '--format=%s', 'main'], self.remote), 'feat(calc): add sub')
        tree = git(['ls-tree', '-r', '--name-only', 'main'], self.remote).split()
        self.assertNotIn('.agents/hooks.json', tree)
        self.assertNotIn('.agents/rgs-guard.log', tree)
        self.assertEqual([p for p in tree if p.startswith('.rgs-task/')], [])

    def test_task_inputs_stay_out_of_scope_and_commits(self):
        self.prepare()
        self.rgs('implement', '--task', 't1')
        wt = os.path.join(self.tmp.path, 'repo.rgs', 't1')
        self.assertTrue(os.path.isfile(os.path.join(wt, '.rgs-task', 'spec.md')))
        exclude = os.path.join(self.repo, '.git', 'info', 'exclude')
        with open(exclude, encoding='utf-8') as f:
            lines = f.read().splitlines()
        self.assertIn('/.rgs-task/', lines)
        # Even with the exclude line gone, scope checks skip .rgs-task/ and commits leave it out.
        write(exclude, '\n'.join(l for l in lines if l != '/.rgs-task/') + '\n')
        self.assertIn('.rgs-task/spec.md', git(['status', '--porcelain', '--untracked-files=all'], wt))
        code, data, out = self.rgs('check', '--task', 't1')
        self.assertEqual(code, 0, out)
        self.assertEqual(data['scope']['changed'], ['calc.py'])
        msg = os.path.join(self.tmp.path, 'msg.txt')
        write(msg, 'feat: x\n')
        code, data, out = self.rgs('ship', '--task', 't1', '--message-file', msg, '--no-pr')
        self.assertEqual(code, 0, out)
        self.assertEqual(git(['show', '--name-only', '--format=', data['commit']], self.repo).split(), ['calc.py'])
        self.assertTrue(os.path.isfile(os.path.join(wt, '.rgs-task', 'spec.md')))

    def test_land_rebases_when_remote_moved(self):
        self.prepare()
        self.rgs('implement', '--task', 't1')
        other = os.path.join(self.tmp.path, 'other')
        git(['clone', '-q', self.remote, other], self.tmp.path)
        git(['config', 'user.email', 'o@example.com'], other)
        git(['config', 'user.name', 'Other'], other)
        write(os.path.join(other, 'README.md'), 'hello\n')
        git(['add', '-A'], other)
        git(['commit', '-q', '-m', 'docs: readme'], other)
        git(['push', '-q', 'origin', 'main'], other)
        msg = os.path.join(self.tmp.path, 'msg.txt')
        write(msg, 'feat: x\n')
        code, data, out = self.rgs('land', '--task', 't1', '--message-file', msg)
        self.assertEqual(code, 0, out)
        self.assertTrue(data['rebased'])
        self.assertEqual(git(['log', '--format=%s', '-2', 'main'], self.remote).splitlines(), ['feat: x', 'docs: readme'])

    def test_out_of_scope_change_blocks_land(self):
        self.prepare()
        code, data, out = self.rgs('implement', '--task', 't1', env={'FAKE_AGY_WRITE': 'calc.py,CLAUDE.md'})
        self.assertEqual(code, 4, out)
        self.assertEqual(data['scope']['outside_allowed'], ['CLAUDE.md'])
        msg = os.path.join(self.tmp.path, 'msg.txt')
        write(msg, 'x\n')
        code, data, out = self.rgs('land', '--task', 't1', '--message-file', msg)
        self.assertEqual(code, 4, out)
        self.assertEqual(git(['log', '--format=%s', '-1', 'main'], self.remote), 'init')

    def test_agy_timeout_is_not_success(self):
        self.prepare()
        code, data, out = self.rgs('implement', '--task', 't1', scenario='timeout')
        self.assertEqual(code, 5, out)
        self.assertEqual(data['agy']['kind'], 'timeout')

    def test_fix_round_limit_escalates(self):
        self.prepare()
        self.rgs('implement', '--task', 't1')
        notes = os.path.join(self.tmp.path, 'fix.md')
        write(notes, 'x\n')
        for _ in range(4):
            code, _, out = self.rgs('fix', '--task', 't1', '--notes', notes)
            self.assertEqual(code, 0, out)
        code, data, out = self.rgs('fix', '--task', 't1', '--notes', notes)
        self.assertEqual(code, 6, out)

    def test_fix_fresh_and_allow(self):
        self.prepare()
        self.rgs('implement', '--task', 't1')
        notes = os.path.join(self.tmp.path, 'fix.md')
        write(notes, 'add a test\n')
        code, data, out = self.rgs('fix', '--task', 't1', '--notes', notes, '--fresh', '--allow', 'test_calc.py',
                                   env={'FAKE_AGY_WRITE': 'test_calc.py'})
        self.assertEqual(code, 0, out)
        self.assertTrue(data['fresh_conversation'])
        argv = calls(self.state)[-1]['argv']
        self.assertNotIn('--conversation', argv)
        self.assert_agy_saw_only_the_worktree(
            'fix-1', ['implementer-rules.md', 'spec.md', 'before-fix-1.diff', 'fix-1.md'])
        self.assertIn('test_calc.py', calls(self.state)[-1]['guard']['write_allow'])
        policy_path = os.path.join(self.tmp.path, 'repo.rgs', 't1', '.agents', 'rgs-guard.json')
        with open(policy_path, encoding='utf-8') as f:
            policy = json.load(f)
        self.assertIn('test_calc.py', policy['write_allow'])

    def test_status_and_cleanup(self):
        self.prepare()
        code, data, _ = self.rgs('status')
        self.assertIn('t1', data['tasks'])
        code, data, _ = self.rgs('cleanup', '--task', 't1', '--delete-branch')
        self.assertTrue(data['worktree_removed'])
        self.assertEqual(git(['branch', '--list', 'rgs/t1'], self.repo), '')

    def test_review_task_records_ledger(self):
        self.prepare()
        self.rgs('implement', '--task', 't1')
        code, data, out = run_script('review.py', ['--task', 't1'], self.repo, 'review_findings', self.env)
        self.assertEqual(code, 0, out)
        self.assertEqual(data['verdict'], 'CHANGES_REQUESTED')
        self.assertEqual(data['model_verdict'], 'PASS')
        self.assertEqual(data['counts'], {'blocker': 0, 'major': 1, 'minor': 1})
        with open(os.path.join(os.path.dirname(data['report']), 'review.json'), encoding='utf-8') as f:
            review = json.load(f)
        self.assertEqual(review['findings'][0]['file'], 'calc.py')
        with open(data['ledger'], encoding='utf-8') as f:
            self.assertIn('待裁決', f.read())
        argv = calls(self.state)[-1]['argv']
        self.assertIn('--json-schema', argv)
        self.assertNotIn('--conversation', argv)
        self.assertFalse(os.path.isdir(os.path.join(self.tmp.path, 'repo.rgs', 'review-task-t1')))

    def test_review_without_findings_passes(self):
        self.prepare()
        self.rgs('implement', '--task', 't1')
        code, data, out = run_script('review.py', ['--task', 't1'], self.repo, 'ok', self.env)
        self.assertEqual((code, data['verdict']), (0, 'PASS'), out)

    def test_review_no_result_is_not_pass(self):
        self.prepare()
        self.rgs('implement', '--task', 't1')
        code, data, out = run_script('review.py', ['--task', 't1'], self.repo, 'no_struct', self.env)
        self.assertEqual(code, 5, out)
        self.assertNotIn('verdict', data)

    def test_ship_without_pr(self):
        self.prepare()
        self.rgs('implement', '--task', 't1')
        msg = os.path.join(self.tmp.path, 'msg.txt')
        write(msg, 'feat: x\n')
        write(os.path.join(self.tmp.path, 'repo.rgs', 't1', 'docs', 'rgs', 'specs', 'M1.md'), SPEC)
        code, data, out = self.rgs('ship', '--task', 't1', '--message-file', msg, '--no-pr')
        self.assertEqual(code, 0, out)
        self.assertEqual(git(['rev-parse', 'rgs/t1'], self.remote), data['commit'])
        files = git(['show', '--name-only', '--format=', data['commit']], self.repo).split()
        self.assertEqual(sorted(files), ['calc.py', 'docs/rgs/specs/M1.md'])


if __name__ == '__main__':
    unittest.main()
