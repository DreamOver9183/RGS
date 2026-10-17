import os
import unittest

from helpers import TempDir, git, make_repo, write

import scope_check
import secret_scan
import rgs_common as rc


class ScopeCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.repo, _ = make_repo(self.tmp.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_clean_when_only_allowed_files_change(self):
        write(os.path.join(self.repo, 'calc.py'), 'def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n')
        write(os.path.join(self.repo, 'tests', 'test_calc.py'), 'import calc\n')
        result = scope_check.check(self.repo, ['calc.py', 'tests/*.py'])
        self.assertTrue(result['ok'], result)
        self.assertEqual(sorted(result['changed']), ['calc.py', 'tests/test_calc.py'])

    def test_outside_files_reported(self):
        write(os.path.join(self.repo, 'calc.py'), 'x = 1\n')
        write(os.path.join(self.repo, 'CLAUDE.md'), '# changed\n')
        result = scope_check.check(self.repo, ['calc.py'])
        self.assertFalse(result['ok'])
        self.assertEqual(result['outside_allowed'], ['CLAUDE.md'])

    def test_guard_files_ignored(self):
        write(os.path.join(self.repo, '.agents', 'rgs-guard.log'), '{}\n')
        write(os.path.join(self.repo, '.agents', 'hooks.json'), '{}\n')
        self.assertTrue(scope_check.check(self.repo, [])['ok'])

    def test_formatting_problems(self):
        with open(os.path.join(self.repo, 'calc.py'), 'w', encoding='utf-8', newline='\n') as f:
            f.write('x = 1')
        write(os.path.join(self.repo, 'b.py'), 'y = 2\n\n\n')
        result = scope_check.check(self.repo, ['calc.py', 'b.py'])
        self.assertEqual(result['formatting']['calc.py'], ['missing final newline'])
        self.assertEqual(result['formatting']['b.py'], ['extra blank line(s) at end of file'])

    def test_deleted_file_counts_as_change(self):
        os.remove(os.path.join(self.repo, 'calc.py'))
        result = scope_check.check(self.repo, [])
        self.assertEqual(result['deleted'], ['calc.py'])
        self.assertFalse(result['ok'])


class SecretScanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.repo, _ = make_repo(self.tmp.path)
        # Built at runtime so the repository never contains a key-shaped literal.
        self.fake_key = 'AIza' + 'Q' * 35

    def tearDown(self):
        self.tmp.cleanup()

    def test_clean_stage(self):
        write(os.path.join(self.repo, 'calc.py'), 'x = 1\n')
        git(['add', '-A'], self.repo)
        self.assertTrue(secret_scan.scan(cwd=self.repo)['ok'])

    def test_key_in_staged_line_is_masked(self):
        write(os.path.join(self.repo, 'config.py'), f'KEY = "{self.fake_key}"\n')
        git(['add', '-A'], self.repo)
        result = secret_scan.scan(cwd=self.repo)
        self.assertFalse(result['ok'])
        hit = result['hits'][0]
        self.assertEqual((hit['file'], hit['line']), ('config.py', 1))
        self.assertNotIn(self.fake_key, str(result))

    def test_protected_file_staged(self):
        write(os.path.join(self.repo, 'local.properties'), 'sdk.dir=x\n')
        git(['add', '-A'], self.repo)
        profile = rc.deep_merge(rc.DEFAULT_PROFILE, {'worktree_copy': ['local.properties']})
        result = secret_scan.scan(cwd=self.repo, profile=profile)
        self.assertEqual(result['protected_files'], ['local.properties'])

    def test_profile_pattern_and_files_mode(self):
        path = os.path.join(self.repo, 'notes.md')
        write(path, 'token: corp-1234567890\n')
        profile = rc.deep_merge(rc.DEFAULT_PROFILE, {'secrets': {'patterns': [r'corp-\d{10}']}})
        self.assertFalse(secret_scan.scan(files=[path], profile=profile)['ok'])


class ScanTextTest(unittest.TestCase):
    def test_all_builtin_patterns_hit_and_masked(self):
        samples = [
            ('google-api-key', 'AIza' + '0' * 35),
            ('openai-key', 's' + 'k-' + '1' * 32),
            ('anthropic-key', 's' + 'k-ant-' + '2' * 32),
            ('github-token', 'gh' + 'p_' + '3' * 36),
            ('aws-access-key', 'AK' + 'IA' + '4' * 16),
            ('slack-token', 'xo' + 'xb-' + '5' * 10),
            ('private-key', '-----BEGIN ' + 'RSA ' + 'PRIVATE KEY-----'),
            ('assigned-secret', 'api_' + 'key = "' + '6' * 16 + '"'),
        ]
        text = '\n'.join(sample for _, sample in samples)
        hits = secret_scan.scan_text(text)

        for line_no, (expected_kind, _) in enumerate(samples, 1):
            line_hits = [h for h in hits if h['line'] == line_no]
            self.assertGreaterEqual(len(line_hits), 1, f"Line {line_no} should have at least one hit")
            kinds = {h['kind'] for h in line_hits}
            self.assertIn(expected_kind, kinds, f"Line {line_no} kinds {kinds} should include {expected_kind}")
            for h in line_hits:
                self.assertEqual(h['file'], '<text>')
                self.assertEqual(h['line'], line_no)

        hits_str = str(hits)
        for _, sample in samples:
            self.assertNotIn(sample, hits_str)

    def test_clean_text_returns_empty(self):
        clean = "This is a clean plan.\nNo secrets here.\nStep 1: do something."
        self.assertEqual(secret_scan.scan_text(clean), [])

    def test_custom_name(self):
        text = "Key: " + ("AK" + "IA" + "0" * 16)
        hits = secret_scan.scan_text(text, name='plan.md')
        self.assertTrue(hits)
        for h in hits:
            self.assertEqual(h['file'], 'plan.md')

    def test_profile_custom_pattern(self):
        token = "corp-" + "1234567890"
        profile = rc.deep_merge(rc.DEFAULT_PROFILE, {'secrets': {'patterns': [r'corp-\d{10}']}})
        hits_with_profile = secret_scan.scan_text(token, profile=profile)
        self.assertEqual(len(hits_with_profile), 1)
        self.assertEqual(hits_with_profile[0]['kind'], 'profile-1')

        hits_without_profile = secret_scan.scan_text(token)
        self.assertEqual(hits_without_profile, [])

    def test_line_number_with_unicode_line_separator(self):
        fake_key = "AK" + "IA" + "0" * 16
        text = "line1 with unicode separator \u2028 still line 1\n" + fake_key
        hits = secret_scan.scan_text(text)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]['line'], 2)


if __name__ == '__main__':
    unittest.main()
