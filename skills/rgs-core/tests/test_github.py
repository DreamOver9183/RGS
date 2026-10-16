"""The /rgs-pr GitHub steps (ship, review --pr --post, stacking) against fake_gh.py and a bare remote."""
import json
import os
import unittest

from helpers import TempDir, calls, git, make_repo, run_script, write

PROFILE = {
    'knowledge_base': ['CLAUDE.md'],
    'shell': 'bash',
    'commands': {'quick': ['python -c "import calc"'], 'verify': ['python -c "print(42)"']},
    'agy': {'implementer': {'models': ['m-impl']}, 'reviewer': {'models': ['m-review']}},
}
SPEC = """# M{n}

## 可修改的檔案

- `{file}`

## 驗收條件

- 有改到
"""


class GitHubFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.repo, self.remote = make_repo(self.tmp.path, PROFILE, files={
            'calc.py': 'def add(a, b):\n    return a + b\n', 'more.py': 'X = 1\n', 'CLAUDE.md': '# KB\n'})
        self.agy_dir = os.path.join(self.tmp.path, 'agy')
        self.gh_dir = os.path.join(self.tmp.path, 'gh')
        self.env = {'FAKE_AGY_DIR': self.agy_dir, 'FAKE_GH_DIR': self.gh_dir}
        self.msg = os.path.join(self.tmp.path, 'msg.txt')
        write(self.msg, 'feat: change\n')
        self.body = os.path.join(self.tmp.path, 'body.md')
        write(self.body, '## 變更摘要\n\n- 測試用 PR\n')

    def tearDown(self):
        self.tmp.cleanup()

    def rgs(self, *args, scenario='implement', env=None):
        return run_script('rgs.py', list(args), self.repo, scenario, {**self.env, **(env or {})})

    def gh_calls(self):
        return [c['argv'] for c in calls(self.gh_dir)]

    def pr(self, number):
        with open(os.path.join(self.gh_dir, 'prs', f'{number}.json'), encoding='utf-8') as f:
            return json.load(f)

    def task_state(self, task):
        with open(os.path.join(self.repo, '.rgs', 'state.json'), encoding='utf-8') as f:
            return json.load(f)['tasks'][task]

    def ship(self, task, env=None):
        return self.rgs('ship', '--task', task, '--message-file', self.msg, '--title', f'feat: {task}',
                        '--body-file', self.body, env=env)

    def prepare_and_implement(self, task, branch, file, stack_on=None):
        spec = os.path.join(self.tmp.path, f'{task}.md')
        write(spec, SPEC.format(n=task, file=file))
        args = ['prepare', '--task', task, '--spec', spec, '--flow', 'pr', '--branch', branch]
        code, data, out = self.rgs(*args, *(['--stack-on', stack_on] if stack_on else []))
        self.assertEqual(code, 0, out)
        code, data, out = self.rgs('implement', '--task', task, env={'FAKE_AGY_WRITE': file})
        self.assertEqual(code, 0, out)

    def shipped(self, task, branch, file='calc.py', stack_on=None):
        self.prepare_and_implement(task, branch, file, stack_on)
        code, data, out = self.ship(task)
        self.assertEqual(code, 0, out)
        return data

    def test_ship_opens_pr_and_records_number(self):
        data = self.shipped('m1', 'feat/m1-sub')
        self.assertTrue(data['shipped'])
        self.assertEqual(data['pr'], 1)
        self.assertEqual(data['base'], 'main')
        self.assertTrue(data['url'].endswith('/pull/1'))
        state = self.task_state('m1')
        self.assertEqual((state['pr'], state['pr_url'], state['step']), (1, data['url'], 'pr-open'))
        pr = self.pr(1)
        self.assertEqual((pr['base'], pr['head'], pr['title']), ('main', 'feat/m1-sub', 'feat: m1'))
        self.assertIn('測試用 PR', pr['body'])
        self.assertEqual(git(['rev-parse', 'refs/heads/feat/m1-sub'], self.remote), data['commit'])

    def test_ship_again_pushes_to_the_existing_pr(self):
        first = self.shipped('m1', 'feat/m1-sub')
        notes = os.path.join(self.tmp.path, 'fix.md')
        write(notes, '# 修正\n\n1. 再改一次\n')
        code, data, out = self.rgs('fix', '--task', 'm1', '--notes', notes, env={'FAKE_AGY_WRITE': 'calc.py'})
        self.assertEqual(code, 0, out)
        # The PR exists, so no title or body is needed.
        code, data, out = self.rgs('ship', '--task', 'm1', '--message-file', self.msg)
        self.assertEqual(code, 0, out)
        self.assertEqual(data['pr'], 1)
        self.assertIn('existing PR', data['note'])
        self.assertEqual([a[:2] for a in self.gh_calls()].count(['pr', 'create']), 1)
        self.assertEqual(git(['rev-parse', 'refs/heads/feat/m1-sub'], self.remote), data['commit'])
        self.assertEqual(git(['rev-parse', data['commit'] + '^'], self.remote), first['commit'])

    def test_stacked_pr_targets_the_parent_branch(self):
        self.shipped('m1', 'feat/m1-sub')
        data = self.shipped('m2', 'feat/m2-more', file='more.py', stack_on='m1')
        self.assertEqual((data['pr'], data['base']), (2, 'feat/m1-sub'))
        self.assertEqual(self.pr(2)['base'], 'feat/m1-sub')
        diff = run_script('review.py', ['--pr', '2', '--task', 'm2'], self.repo, 'ok', self.env)[1]
        self.assertEqual(diff['verdict'], 'PASS')
        with open(os.path.join(os.path.dirname(diff['report']), 'pr.diff'), encoding='utf-8') as f:
            reviewed = f.read()
        self.assertIn('more.py', reviewed)
        self.assertNotIn('calc.py', reviewed)

    def merge_pr1(self, squash=False):
        """What the user does on GitHub: merge PR #1 into main."""
        git(['fetch', '-q', 'origin'], self.repo)
        if squash:
            git(['merge', '-q', '--squash', 'origin/feat/m1-sub'], self.repo)
            git(['commit', '-q', '-m', 'feat: m1 (#1)'], self.repo)
        else:
            git(['merge', '-q', '--no-ff', '-m', 'Merge pull request #1', 'origin/feat/m1-sub'], self.repo)
        git(['push', '-q', 'origin', 'main'], self.repo)
        pr = self.pr(1)
        pr['state'] = 'MERGED'
        write(os.path.join(self.gh_dir, 'prs', '1.json'), json.dumps(pr))

    def remote_diff(self, rev_range):
        return git(['diff', '--name-only', rev_range], self.remote).split()

    def test_retarget_after_a_merge_commit(self):
        self.shipped('m1', 'feat/m1-sub')
        m2 = self.shipped('m2', 'feat/m2-more', file='more.py', stack_on='m1')
        self.merge_pr1()
        code, data, out = self.rgs('retarget', '--task', 'm2')
        self.assertEqual(code, 0, out)
        self.assertFalse(data['rebased'])
        self.assertEqual((data['pr'], data['pr_base']), (2, 'main'))
        self.assertEqual(self.pr(2)['base'], 'main')
        state = self.task_state('m2')
        self.assertEqual((state['base'], state.get('stack_on'), state['step']), ('origin/main', None, 'retargeted'))
        self.assertEqual(git(['rev-parse', 'refs/heads/feat/m2-more'], self.remote), m2['commit'])
        self.assertEqual(self.remote_diff('main...feat/m2-more'), ['more.py'])
        # m1 can now be cleaned up (as in "merged") without breaking m2's diff.
        code, _, out = self.rgs('cleanup', '--task', 'm1', '--delete-branch')
        self.assertEqual(code, 0, out)
        code, data, out = self.rgs('diff', '--task', 'm2')
        self.assertEqual(code, 0, out)
        self.assertEqual([line.split('|')[0].strip() for line in data['stat'][:-1]], ['more.py'])

    def test_retarget_after_a_squash_merge_rebases_onto_main(self):
        self.shipped('m1', 'feat/m1-sub')
        self.shipped('m2', 'feat/m2-more', file='more.py', stack_on='m1')
        self.merge_pr1(squash=True)
        code, data, out = self.rgs('retarget', '--task', 'm2')
        self.assertEqual(code, 0, out)
        self.assertTrue(data['rebased'])
        self.assertTrue(data['pushed'])
        main = git(['rev-parse', 'refs/heads/main'], self.remote)
        self.assertEqual(git(['rev-parse', 'refs/heads/feat/m2-more^'], self.remote), main)
        self.assertEqual(git(['rev-parse', 'refs/heads/feat/m2-more'], self.remote), data['commit'])
        self.assertEqual(self.task_state('m2')['commit'], data['commit'])
        self.assertEqual(self.remote_diff('main...feat/m2-more'), ['more.py'])
        self.assertIn(['pr', 'edit', '2', '--base', 'main'], self.gh_calls())

    def test_retarget_leaves_a_closed_pr_alone(self):
        self.shipped('m1', 'feat/m1-sub')
        m2 = self.shipped('m2', 'feat/m2-more', file='more.py', stack_on='m1')
        self.merge_pr1(squash=True)
        pr = self.pr(2)
        pr['state'] = 'CLOSED'
        write(os.path.join(self.gh_dir, 'prs', '2.json'), json.dumps(pr))
        code, data, out = self.rgs('retarget', '--task', 'm2')
        self.assertEqual(code, 10, out)
        self.assertEqual(data['pr_state'], 'CLOSED')
        self.assertFalse(data['rebased'])
        wt = os.path.join(self.tmp.path, 'repo.rgs', 'm2')
        self.assertEqual(git(['rev-parse', 'HEAD'], wt), m2['commit'])
        self.assertEqual(self.task_state('m2')['stack_on'], 'm1')

    def test_retarget_waits_for_the_parent_merge(self):
        self.shipped('m1', 'feat/m1-sub')
        m2 = self.shipped('m2', 'feat/m2-more', file='more.py', stack_on='m1')
        code, data, out = self.rgs('retarget', '--task', 'm2')
        self.assertEqual(code, 1, out)
        self.assertIn('not merged', data['error'])
        self.assertEqual(self.pr(2)['base'], 'feat/m1-sub')
        self.assertEqual(self.task_state('m2')['stack_on'], 'm1')
        self.assertEqual(git(['rev-parse', 'refs/heads/feat/m2-more'], self.remote), m2['commit'])

    def test_new_pr_needs_title_and_body_before_committing(self):
        self.prepare_and_implement('m1', 'feat/m1-sub', 'calc.py')
        code, data, out = self.rgs('ship', '--task', 'm1', '--message-file', self.msg)
        self.assertEqual(code, 2, out)
        self.assertIn('--title', data['error'])
        self.assertEqual(git(['rev-list', '--count', 'feat/m1-sub'], self.repo), '1')
        self.assertEqual(self.gh_calls(), [])

    def test_failed_pr_create_is_reported(self):
        self.prepare_and_implement('m1', 'feat/m1-sub', 'calc.py')
        code, data, out = self.ship('m1', env={'FAKE_GH_FAIL': 'pr create'})
        self.assertEqual(code, 10, out)
        self.assertFalse(data['shipped'])
        self.assertIn('pr create failed', data['stderr'])
        self.assertIsNone(self.task_state('m1').get('pr'))
        self.assertEqual(git(['rev-parse', 'refs/heads/feat/m1-sub'], self.remote), data['commit'])

    def test_review_pr_posts_the_report_and_appends_the_ledger(self):
        self.shipped('m1', 'feat/m1-sub')
        ledger = os.path.join(self.repo, 'docs', 'rgs', 'reviews', 'PR-1.md')
        args = ['--pr', '1', '--task', 'm1', '--ledger', ledger, '--post']
        code, data, out = run_script('review.py', args, self.repo, 'review_findings', self.env)
        self.assertEqual(code, 0, out)
        self.assertEqual((data['verdict'], data['posted'], data['round']), ('CHANGES_REQUESTED', True, 1))
        with open(data['report'], encoding='utf-8') as f:
            report = f.read()
        self.assertIn('PR #1「feat: m1」', report)
        self.assertEqual(self.pr(1)['comments'], [report])
        with open(ledger, encoding='utf-8') as f:
            text = f.read()
        self.assertIn('第 1 輪審查', text)
        self.assertIn('PR 留言：https://github.com/owner/repo/pull/1#issuecomment-1', text)
        self.assertIn('報告：`.rgs/runs/m1/review-1/review.md`', text)
        self.assertEqual(text.count('待裁決'), 2)
        prompt = calls(self.agy_dir)[-1]['argv'][1]
        review_wt = os.path.join(self.tmp.path, 'repo.rgs', 'review-pr-1')
        self.assertIn(f'`{os.path.join(review_wt, "CLAUDE.md")}`', prompt)
        self.assertNotIn(f'`{os.path.join(self.repo, "CLAUDE.md")}`', prompt)

        note = os.path.join(self.tmp.path, 'note.md')
        write(note, '# 審查備註\n\n上一輪：採納 1、不採納 2\n')
        code, data, out = run_script('review.py', args + ['--note', note], self.repo, 'ok', self.env)
        self.assertEqual(code, 0, out)
        self.assertEqual((data['verdict'], data['round']), ('PASS', 2))
        self.assertEqual(len(self.pr(1)['comments']), 2)
        with open(ledger, encoding='utf-8') as f:
            text = f.read()
        self.assertIn('第 2 輪審查', text)
        self.assertTrue(text.startswith('# 審查裁決紀錄：PR #1'))

    def test_failed_post_keeps_the_verdict_and_the_ledger(self):
        self.shipped('m1', 'feat/m1-sub')
        ledger = os.path.join(self.repo, 'docs', 'rgs', 'reviews', 'PR-1.md')
        code, data, out = run_script('review.py', ['--pr', '1', '--task', 'm1', '--ledger', ledger, '--post'],
                                     self.repo, 'review_findings', {**self.env, 'FAKE_GH_FAIL': 'pr comment'})
        self.assertEqual(code, 0, out)
        self.assertEqual((data['verdict'], data['posted']), ('CHANGES_REQUESTED', False))
        self.assertIn('pr comment failed', data['post_error'])
        with open(ledger, encoding='utf-8') as f:
            text = f.read()
        self.assertIn('判定 CHANGES_REQUESTED', text)
        self.assertNotIn('PR 留言', text)

    def test_review_without_post_leaves_the_pr_alone(self):
        self.shipped('m1', 'feat/m1-sub')
        code, data, out = run_script('review.py', ['--pr', '1', '--task', 'm1'], self.repo, 'ok', self.env)
        self.assertEqual(code, 0, out)
        self.assertFalse(data['posted'])
        self.assertEqual(self.pr(1)['comments'], [])
        self.assertNotIn(['pr', 'comment'], [a[:2] for a in self.gh_calls()])


if __name__ == '__main__':
    unittest.main()
