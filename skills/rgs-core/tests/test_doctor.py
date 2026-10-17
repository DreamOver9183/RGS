"""doctor.py checks that need a real repository."""
import os
import unittest

from helpers import TempDir, git, make_repo, run_script

PROFILE = {'knowledge_base': ['CLAUDE.md'], 'commands': {'quick': ['true'], 'verify': ['true']}}


class DoctorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.repo, _ = make_repo(self.tmp.path, PROFILE)

    def tearDown(self):
        self.tmp.cleanup()

    def identity(self):
        code, data, out = run_script('doctor.py', ['--quick', '--json'], self.repo)
        return code, next(c for c in data['checks'] if c['check'] == 'git identity'), out

    def test_git_identity_ok(self):
        code, check, out = self.identity()
        self.assertEqual(code, 0, out)
        self.assertEqual((check['status'], check['detail']), ('ok', 'Test <test@example.com>'))

    def test_missing_git_identity_fails(self):
        # Without an identity, land/ship cannot commit; useConfigOnly stops git from guessing one.
        git(['config', '--unset', 'user.name'], self.repo)
        git(['config', '--unset', 'user.email'], self.repo)
        git(['config', 'user.useConfigOnly', 'true'], self.repo)
        empty = os.path.join(self.tmp.path, 'empty.gitconfig')
        open(empty, 'w').close()
        env = {'GIT_CONFIG_GLOBAL': empty, 'GIT_CONFIG_NOSYSTEM': '1'}
        code, data, out = run_script('doctor.py', ['--quick', '--json'], self.repo, extra_env=env)
        check = next(c for c in data['checks'] if c['check'] == 'git identity')
        self.assertEqual(code, 1, out)
        self.assertEqual(check['status'], 'fail')
        self.assertIn('user.email', check['detail'])


class PermissionRulesTest(unittest.TestCase):
    def test_path_with_spaces_is_quoted_like_the_command(self):
        import doctor
        rules = doctor.permission_rules('D:\\Claude Code\\RGS_skills\\skills\\rgs-core')
        self.assertEqual(rules[0], 'Bash(python -I "D:/Claude Code/RGS_skills/skills/rgs-core/scripts/rgs.py":*)')
        # The rule is a prefix of the command Claude runs.
        command = 'python -I "D:/Claude Code/RGS_skills/skills/rgs-core/scripts/review.py" --pr 1'
        self.assertTrue(command.startswith(rules[1][len('Bash('):-len(':*)')]))
        self.assertEqual(len(rules), 7)
        self.assertTrue(all(r.count('"') == 2 for r in rules))

    def test_path_without_spaces_is_not_quoted(self):
        import doctor
        rules = doctor.permission_rules('C:/tools/rgs-core')
        self.assertEqual(rules[0], 'Bash(python -I C:/tools/rgs-core/scripts/rgs.py:*)')
        self.assertFalse(any('"' in r for r in rules))


class DoctorFacetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.folder = os.path.join(self.tmp.path, 'plain_dir')
        os.makedirs(self.folder)

    def tearDown(self):
        self.tmp.cleanup()

    def test_facet_quick_ok(self):
        code, data, out = run_script('doctor.py', ['--flow', 'facet', '--model', 'gemini-4-argon-high', '--quick', '--json'], self.folder)
        self.assertEqual(code, 0, out)
        checks = {c['check']: c for c in data['checks']}
        for expected in ('python', 'agy', 'model', 'agy models'):
            self.assertIn(expected, checks)
            self.assertNotEqual(checks[expected]['status'], 'fail')
        self.assertNotIn('git repo', checks)

    def test_facet_model_not_listed(self):
        code, data, out = run_script('doctor.py', ['--flow', 'facet', '--model', 'gemini-9-x', '--quick', '--json'], self.folder)
        self.assertEqual(code, 1, out)
        check = next(c for c in data['checks'] if c['check'] == 'agy models')
        self.assertEqual(check['status'], 'fail')
        self.assertIn('not listed: gemini-9-x', check['detail'])

    def test_facet_not_substring_match(self):
        env = {'FAKE_AGY_MODELS': 'gemini-4-argon-high'}
        code, data, out = run_script('doctor.py', ['--flow', 'facet', '--model', 'gemini-4-argon', '--quick', '--json'], self.folder, extra_env=env)
        self.assertEqual(code, 1, out)
        check = next(c for c in data['checks'] if c['check'] == 'agy models')
        self.assertEqual(check['status'], 'fail')
        self.assertIn('not listed: gemini-4-argon', check['detail'])

    def test_facet_non_gemini_model(self):
        code, data, out = run_script('doctor.py', ['--flow', 'facet', '--model', 'claude-opus-5-5', '--quick', '--json'], self.folder)
        self.assertEqual(code, 1, out)
        check = next(c for c in data['checks'] if c['check'] == 'model')
        self.assertEqual(check['status'], 'fail')

    def test_facet_missing_model(self):
        code, data, out = run_script('doctor.py', ['--flow', 'facet', '--quick', '--json'], self.folder)
        self.assertEqual(code, 1, out)
        check = next(c for c in data['checks'] if c['check'] == 'model')
        self.assertEqual(check['status'], 'fail')

    def test_facet_with_init_exits_2(self):
        code, data, out = run_script('doctor.py', ['--flow', 'facet', '--init'], self.folder)
        self.assertEqual(code, 2, out)


if __name__ == '__main__':
    unittest.main()
