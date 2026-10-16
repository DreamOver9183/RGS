import json
import os
import shutil
import subprocess
import sys
import tempfile

TESTS = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(TESTS), 'scripts')
FAKE_AGY = os.path.join(TESTS, 'fake_agy.py')
FAKE_GH = os.path.join(TESTS, 'fake_gh.py')
sys.path.insert(0, SCRIPTS)


def git(args, cwd):
    proc = subprocess.run(['git', *args], cwd=cwd, capture_output=True, encoding='utf-8', errors='replace')
    if proc.returncode != 0:
        raise AssertionError(f'git {" ".join(args)} failed: {proc.stderr}')
    return proc.stdout.strip()


class TempDir:
    def __init__(self):
        self.path = tempfile.mkdtemp(prefix='rgs_test_')

    def cleanup(self):
        # Worktrees and git objects can be read-only on Windows.
        def onerror(func, path, _):
            os.chmod(path, 0o700)
            func(path)
        shutil.rmtree(self.path, onerror=onerror)


def make_repo(root, profile=None, files=None):
    """A clone ('repo') of a bare remote ('remote.git') with one commit on main."""
    remote = os.path.join(root, 'remote.git')
    repo = os.path.join(root, 'repo')
    git(['init', '-q', '--bare', '-b', 'main', remote], root)
    git(['clone', '-q', remote, repo], root)
    for args in (['config', 'user.name', 'Test'], ['config', 'user.email', 'test@example.com'],
                 ['config', 'core.autocrlf', 'false']):
        git(args, repo)
    files = files or {'calc.py': 'def add(a, b):\n    return a + b\n', 'CLAUDE.md': '# KB\n'}
    for rel, text in files.items():
        path = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
    if profile is not None:
        os.makedirs(os.path.join(repo, '.rgs'), exist_ok=True)
        with open(os.path.join(repo, '.rgs', 'profile.json'), 'w', encoding='utf-8') as f:
            json.dump(profile, f)
        with open(os.path.join(repo, '.rgs', '.gitignore'), 'w', encoding='utf-8', newline='\n') as f:
            f.write('state.json\nruns/\n')
    git(['add', '-A'], repo)
    git(['commit', '-q', '-m', 'init'], repo)
    git(['push', '-q', '-u', 'origin', 'main'], repo)
    return repo, remote


def run_script(name, args, cwd, scenario='ok', extra_env=None):
    env = dict(os.environ, RGS_AGY=FAKE_AGY, RGS_GH=FAKE_GH, FAKE_AGY_SCENARIO=scenario)
    env.update(extra_env or {})
    proc = subprocess.run([sys.executable, '-I', os.path.join(SCRIPTS, name), *args], cwd=cwd,
                          capture_output=True, encoding='utf-8', errors='replace', env=env)
    out = proc.stdout.strip()
    data = None
    if out:
        try:
            data = json.loads(out)
        except ValueError:
            data = None
    return proc.returncode, data, proc.stdout + proc.stderr


def calls(state_dir):
    """Recorded fake agy (or fake gh) invocations, oldest first."""
    folder = os.path.join(state_dir, 'calls')
    if not os.path.isdir(folder):
        return []
    result = []
    for name in sorted(os.listdir(folder), key=lambda n: int(n.split('-')[0])):
        with open(os.path.join(folder, name), encoding='utf-8') as f:
            result.append(json.load(f))
    return result


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
