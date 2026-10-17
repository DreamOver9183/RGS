import json
import os
import shutil
import subprocess
import sys
import unittest

from helpers import SCRIPTS, TempDir, write

import guard


class DecideTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.ws = os.path.join(self.tmp.path, 'ws')
        self.extra = os.path.join(self.tmp.path, 'run')
        os.makedirs(self.ws)
        os.makedirs(self.extra)
        self.policy = {'role': 'implementer', 'roots': [self.ws, self.extra], 'write_allow': ['src/app.py', 'tests/*.py'],
                       'deny_read': ['local.properties', '*_KEY_*', '.env*'], 'read_commands': True, 'allow_commands': []}

    def tearDown(self):
        self.tmp.cleanup()

    def decide(self, name, policy=None, **args):
        return guard.decide(policy or self.policy, {'name': name, 'args': args})

    def p(self, *parts):
        return os.path.join(self.ws, *parts)

    def test_read_inside_allowed(self):
        self.assertIsNone(self.decide('view_file', AbsolutePath=self.p('src', 'app.py')))
        self.assertIsNone(self.decide('view_file', AbsolutePath=os.path.join(self.extra, 'spec.md')))

    def test_read_outside_denied(self):
        self.assertIn('outside', self.decide('view_file', AbsolutePath=os.path.join(self.tmp.path, 'other.txt')))

    def test_secret_read_denied(self):
        self.assertIn('protected', self.decide('view_file', AbsolutePath=self.p('local.properties')))
        self.assertIn('protected', self.decide('view_file', AbsolutePath=self.p('App_KEY_01.txt')))
        self.assertIn('protected', self.decide('view_file', AbsolutePath=self.p('.env.local')))

    def test_forward_slash_and_file_uri(self):
        uri = 'file:///' + self.p('src', 'app.py').replace('\\', '/')
        self.assertIsNone(self.decide('view_file', AbsolutePath=uri))

    def test_write_allowed_and_glob(self):
        self.assertIsNone(self.decide('replace_file_content', TargetFile=self.p('src', 'app.py')))
        self.assertIsNone(self.decide('write_to_file', TargetFile=self.p('tests', 'test_app.py')))

    def test_write_not_listed_denied(self):
        self.assertIn('not in the list', self.decide('write_to_file', TargetFile=self.p('notes.txt')))

    def test_write_to_extra_root_denied(self):
        self.assertIsNotNone(self.decide('write_to_file', TargetFile=os.path.join(self.extra, 'src', 'app.py')))

    def test_write_into_agents_denied(self):
        self.assertIn('.agents', self.decide('write_to_file', TargetFile=self.p('.agents', 'rgs-guard.json')))

    def test_reviewer_cannot_write(self):
        policy = dict(self.policy, role='reviewer')
        self.assertIn('read-only', self.decide('write_to_file', policy, TargetFile=self.p('src', 'app.py')))

    def test_neutral_tools(self):
        for name in ('invoke_subagent', 'send_message', 'manage_subagents', 'finish', 'wait'):
            self.assertIsNone(self.decide(name, Prompt='x'), name)

    def test_quoted_path_with_spaces(self):
        spaced = os.path.join(self.tmp.path, 'my work')
        os.makedirs(spaced)
        policy = dict(self.policy, roots=[spaced])
        inside = f'Get-ChildItem -Recurse "{os.path.join(spaced, "src")}"'
        outside = f'Get-ChildItem -Recurse "{os.path.join(self.tmp.path, "other dir")}"'
        self.assertIsNone(self.decide('run_command', policy, CommandLine=inside, Cwd=spaced))
        self.assertIn('outside', self.decide('run_command', policy, CommandLine=outside, Cwd=spaced))

    def test_unknown_tool_denied(self):
        self.assertIn('not allowed', self.decide('search_web', Query='x'))
        self.assertIn('not allowed', self.decide('browser_open', Url='x'))

    def test_read_commands(self):
        ok = ['Get-ChildItem -Name', 'Select-String -Path .\\* -Pattern "def add"', 'rg -n foo src',
              'git grep -n foo', 'git log --oneline -5', 'Get-ChildItem -Recurse | Select-Object -First 5',
              f'Get-Content "{self.p("src", "app.py")}"']
        for command in ok:
            self.assertIsNone(self.decide('run_command', CommandLine=command, Cwd=self.ws), command)

    def test_unsafe_commands(self):
        bad = ['python app.py', 'gradlew test', 'Get-ChildItem | Remove-Item', 'Get-Content a.txt > b.txt',
               'Get-ChildItem; Remove-Item x', 'Where-Object { Remove-Item x }', 'git diff --output=x.patch',
               'rg --pre cat foo', 'Get-Content ..\\other\\x.txt', 'Get-Content local.properties',
               f'Get-Content "{os.path.join(self.tmp.path, "secret.txt")}"', 'git commit -m x', '']
        for command in bad:
            self.assertIsNotNone(self.decide('run_command', CommandLine=command, Cwd=self.ws), command)

    def test_command_cwd_outside_denied(self):
        self.assertIsNotNone(self.decide('run_command', CommandLine='Get-ChildItem', Cwd=self.tmp.path))

    def test_allow_commands_for_implementer(self):
        policy = dict(self.policy, allow_commands=['gradlew compileKotlin'])
        self.assertIsNone(self.decide('run_command', policy, CommandLine='gradlew compileKotlin', Cwd=self.ws))
        reviewer = dict(policy, role='reviewer')
        self.assertIsNotNone(self.decide('run_command', reviewer, CommandLine='gradlew compileKotlin', Cwd=self.ws))


class HookProcessTest(unittest.TestCase):
    """The guard as agy runs it: JSON on stdin, decision on stdout, cwd = .agents."""

    def setUp(self):
        self.tmp = TempDir()
        self.agents = os.path.join(self.tmp.path, '.agents')
        os.makedirs(self.agents)
        shutil.copyfile(os.path.join(SCRIPTS, 'guard.py'), os.path.join(self.agents, 'rgs-guard.py'))

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, call, policy=True):
        if policy:
            write(os.path.join(self.agents, 'rgs-guard.json'), json.dumps(
                {'role': 'implementer', 'roots': [self.tmp.path], 'write_allow': ['a.py'], 'deny_read': []}))
        proc = subprocess.run([sys.executable, '-I', 'rgs-guard.py'], cwd=self.agents, capture_output=True,
                              input=json.dumps({'toolCall': call, 'stepIdx': 1}).encode('utf-8'))
        return json.loads(proc.stdout.decode('utf-8'))

    def test_allow_and_log(self):
        out = self.run_hook({'name': 'write_to_file', 'args': {'TargetFile': os.path.join(self.tmp.path, 'a.py')}})
        self.assertEqual(out['decision'], 'allow')
        with open(os.path.join(self.agents, 'rgs-guard.log'), encoding='utf-8') as f:
            self.assertEqual(json.loads(f.readline())['decision'], 'allow')

    def test_deny_has_reason(self):
        out = self.run_hook({'name': 'write_to_file', 'args': {'TargetFile': os.path.join(self.tmp.path, 'b.py')}})
        self.assertEqual(out['decision'], 'deny')
        self.assertTrue(out['reason'].startswith('rgs-guard:'))

    def test_missing_policy_fails_closed(self):
        out = self.run_hook({'name': 'view_file', 'args': {}}, policy=False)
        self.assertEqual(out['decision'], 'deny')


class SealedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.ws = os.path.join(self.tmp.path, 'ws')
        os.makedirs(self.ws)
        self.policy = {'role': 'sealed', 'roots': [self.ws]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_finish_and_wait_allowed(self):
        for name in ('finish', 'wait'):
            self.assertIsNone(guard.decide(self.policy, {'name': name, 'args': {}}))

    def test_other_tools_denied(self):
        tools = [
            ('write_to_file', {'TargetFile': os.path.join(self.ws, 'a.txt')}),
            ('view_file', {'AbsolutePath': os.path.join(self.ws, 'a.txt')}),
            ('list_dir', {'DirectoryPath': self.ws}),
            ('grep_search', {'Pattern': 'foo'}),
            ('run_command', {'CommandLine': 'Get-ChildItem', 'Cwd': self.ws}),
            ('invoke_subagent', {'Prompt': 'foo'}),
            ('send_message', {'Message': 'bar'}),
            ('task_boundary', {}),
            ('unknown_tool', {}),
        ]
        for name, args in tools:
            reason = guard.decide(self.policy, {'name': name, 'args': args})
            self.assertIsNotNone(reason, f'{name} should be denied')
            self.assertIn(name, reason)
            self.assertIn('only finish and wait are allowed in a sealed run', reason)

    def test_policy_without_roots(self):
        policy = {'role': 'sealed'}
        self.assertIsNone(guard.decide(policy, {'name': 'finish', 'args': {}}))
        self.assertIsNone(guard.decide(policy, {'name': 'wait', 'args': {}}))
        reason = guard.decide(policy, {'name': 'view_file', 'args': {'AbsolutePath': 'foo'}})
        self.assertIsNotNone(reason)
        self.assertIn('view_file', reason)
        self.assertIn('only finish and wait are allowed in a sealed run', reason)

    def test_hook_process_with_sealed_policy_and_log(self):
        agents = os.path.join(self.tmp.path, '.agents')
        os.makedirs(agents, exist_ok=True)
        shutil.copyfile(os.path.join(SCRIPTS, 'guard.py'), os.path.join(agents, 'rgs-guard.py'))
        write(os.path.join(agents, 'rgs-guard.json'), json.dumps({'role': 'sealed'}))

        def run(call):
            proc = subprocess.run([sys.executable, '-I', 'rgs-guard.py'], cwd=agents, capture_output=True,
                                  input=json.dumps({'toolCall': call, 'stepIdx': 1}).encode('utf-8'))
            return json.loads(proc.stdout.decode('utf-8'))

        out1 = run({'name': 'finish', 'args': {}})
        self.assertEqual(out1['decision'], 'allow')

        out2 = run({'name': 'view_file', 'args': {'AbsolutePath': os.path.join(self.tmp.path, 'a.py')}})
        self.assertEqual(out2['decision'], 'deny')
        self.assertIn('rgs-guard:', out2['reason'])
        self.assertIn('only finish and wait are allowed in a sealed run', out2['reason'])

        log_path = os.path.join(agents, 'rgs-guard.log')
        with open(log_path, encoding='utf-8') as f:
            lines = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]['tool'], 'finish')
        self.assertEqual(lines[0]['decision'], 'allow')
        self.assertEqual(lines[1]['tool'], 'view_file')
        self.assertEqual(lines[1]['decision'], 'deny')


if __name__ == '__main__':
    unittest.main()
