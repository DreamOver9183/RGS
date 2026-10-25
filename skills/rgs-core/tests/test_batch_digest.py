import json
import os
import unittest

from helpers import TempDir, calls, run_script, write

import digest


class BatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.state = os.path.join(self.tmp.path, 'fake')
        self.input = os.path.join(self.tmp.path, 'items.jsonl')
        write(self.input, ''.join(json.dumps({'id': f'n{i}', 'text': f'name {i}', 'secret_col': 'x'}) + '\n'
                                  for i in range(1, 8)))
        self.prompt = os.path.join(self.tmp.path, 'prompt.md')
        write(self.prompt, 'Translate each name.\n')
        self.out = os.path.join(self.tmp.path, 'out')

    def tearDown(self):
        self.tmp.cleanup()

    def batch(self, *extra, env=None):
        args = ['--input', self.input, '--prompt', self.prompt, '--out', self.out, '--batch', '3', '--workers', '2',
                '--fields', 'id,text', *extra]
        return run_script('batch.py', args, self.tmp.path, 'batch_echo', {'FAKE_AGY_DIR': self.state, **(env or {})})

    def test_all_items_and_retry_of_dropped_id(self):
        code, data, out = self.batch(env={'FAKE_AGY_DROP': 'n5'})
        self.assertEqual(code, 0, out)
        self.assertEqual((data['done'], data['missing']), (7, 0))
        self.assertEqual(len(calls(self.state)), 4)  # 3 batches + 1 retry for n5
        prompts = ' '.join(c['argv'][c['argv'].index('-p') + 1] for c in calls(self.state))
        self.assertNotIn('secret_col', prompts)
        with open(os.path.join(self.out, 'results.jsonl'), encoding='utf-8') as f:
            rows = [json.loads(line) for line in f]
        self.assertEqual([r['input']['id'] for r in rows], [f'n{i}' for i in range(1, 8)])
        self.assertEqual(rows[0]['result']['output'], 'out-n1')

    def test_prompt_asks_for_finish(self):
        # --json-schema adds a finish tool; "use no tools" made the model answer in text and redo it.
        self.batch()
        argv = calls(self.state)[0]['argv']
        prompt = argv[argv.index('-p') + 1]
        self.assertIn('--json-schema', argv)
        self.assertIn('呼叫 finish', prompt)
        self.assertNotIn('不要使用任何工具', prompt)
        self.assertIn('Translate each name.', prompt)

    def test_rerun_resumes_without_new_calls(self):
        self.batch()
        before = len(calls(self.state))
        code, data, _ = self.batch()
        self.assertEqual(code, 0)
        self.assertEqual(len(calls(self.state)), before)

    def test_quota_stops(self):
        code, data, out = run_script('batch.py', ['--input', self.input, '--prompt', self.prompt, '--out', self.out,
                                                  '--batch', '3', '--workers', '1'], self.tmp.path, 'quota',
                                     {'FAKE_AGY_DIR': self.state})
        self.assertEqual(code, 3, out)
        self.assertTrue(data['quota_stop'])

    def test_validator_warnings(self):
        validator = os.path.join(self.tmp.path, 'check.py')
        write(validator, 'def validate(item, result):\n    return ["odd"] if item["id"] == "n3" else []\n')
        code, data, _ = self.batch('--validator', validator)
        self.assertEqual(data['with_warnings'], 1)


class DigestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.log = os.path.join(self.tmp.path, 'app.log')
        lines = [f'INFO step {i}' for i in range(1, 2001)]
        lines[1499] = 'ERROR disk full on /data'
        write(self.log, '\n'.join(lines) + '\n')

    def tearDown(self):
        self.tmp.cleanup()

    def test_select_ranges_merges_context(self):
        lines = ['a', 'ERR', 'b', 'c', 'ERR', 'd', 'e', 'f', 'g', 'ERR']
        self.assertEqual(digest.select_ranges(lines, ['err'], 1), [(1, 6), (9, 10)])

    def test_chunks_keep_line_numbers(self):
        chunks = digest.build_chunks([self.log], [], 0, 800)
        self.assertEqual(len(chunks), 3)
        self.assertIn('L1500: ERROR disk full on /data', chunks[1])

    def test_verify_quote(self):
        good = {'file': self.log, 'line_start': 1500, 'quote': 'ERROR disk full'}
        moved = {'file': 'app.log', 'line_start': 1502, 'quote': 'ERROR  disk full on /data'}
        wrong = {'file': self.log, 'line_start': 10, 'quote': 'ERROR disk full'}
        self.assertTrue(digest.verify(good, [self.log]))
        self.assertTrue(digest.verify(moved, [self.log]))
        self.assertFalse(digest.verify(wrong, [self.log]))

    def test_run_with_grep_flags_unverified_claims(self):
        out = os.path.join(self.tmp.path, 'out')
        code, data, text = run_script('digest.py', [self.log, '--question', 'what failed?', '--grep', 'ERROR',
                                                    '--out', out], self.tmp.path, 'digest_echo',
                                      {'FAKE_AGY_DIR': os.path.join(self.tmp.path, 'fake')})
        self.assertEqual(code, 0, text)
        self.assertEqual((data['chunks'], data['findings'], data['verified']), (1, 2, 1))

    def test_refuses_protected_files(self):
        key = os.path.join(self.tmp.path, 'App_KEY_01.txt')
        write(key, 'x\n')
        code, data, _ = run_script('digest.py', [key, '--question', 'q'], self.tmp.path, 'ok', {})
        self.assertEqual(code, 7)
        self.assertIn('protected', data['error'])


if __name__ == '__main__':
    unittest.main()
