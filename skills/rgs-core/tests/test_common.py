import json
import os
import unittest

from helpers import FAKE_AGY, TempDir, write

import rgs_common as rc


class CallAgyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        os.environ['RGS_AGY'] = FAKE_AGY
        os.environ['FAKE_AGY_DIR'] = os.path.join(self.tmp.path, 'state')
        self.schema = os.path.join(self.tmp.path, 'schema.json')
        write(self.schema, json.dumps({'type': 'object', 'properties': {'verdict': {}, 'findings': {}}}))

    def tearDown(self):
        for key in ('RGS_AGY', 'FAKE_AGY_DIR', 'FAKE_AGY_SCENARIO', 'FAKE_AGY_QUOTA_MODEL'):
            os.environ.pop(key, None)
        self.tmp.cleanup()

    def call(self, scenario, **kw):
        os.environ['FAKE_AGY_SCENARIO'] = scenario
        kw.setdefault('model', 'm1')
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
        os.environ['FAKE_AGY_QUOTA_MODEL'] = 'm1'
        result = rc.call_with_fallback(['m1', 'm2'], prompt='hi', cwd=self.tmp.path, timeout_s=30)
        self.assertTrue(result.ok)
        self.assertEqual(result.model, 'm2')
        self.assertEqual(result.tried, [('m1', 'quota'), ('m2', 'ok')])

    def test_saves_raw_output(self):
        prefix = os.path.join(self.tmp.path, 'out', 'run')
        self.call('ok', save_as=prefix)
        for ext in ('.json', '.err', '.prompt.md'):
            self.assertTrue(os.path.exists(prefix + ext), ext)


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

    def test_render_template_fills_placeholders(self):
        text = rc.render_template('prompts/fix.md', fix='F', rules='R', extra_allowed='')
        self.assertIn('`F`', text)
        self.assertNotIn('{{', text)


if __name__ == '__main__':
    unittest.main()
