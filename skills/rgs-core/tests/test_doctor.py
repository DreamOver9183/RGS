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


if __name__ == '__main__':
    unittest.main()
