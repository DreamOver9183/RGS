"""Shared helpers for the rgs scripts: profile, state, git, templates and the agy (Antigravity CLI) call.

Every agy call goes through call_agy()/call_with_fallback(), which never trusts agy's own status:
agy exits 0 with status SUCCESS and an empty response when --print-timeout expires, and still says
SUCCESS when a tool was denied. A result counts only when the expected payload is really there.
"""
import copy
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(CORE, 'templates')
GUARD_SRC = os.path.join(CORE, 'scripts', 'guard.py')

# Exit codes shared by the scripts (2 is left to argparse usage errors).
EXIT_OK = 0
EXIT_QUOTA = 3        # every model in the fallback chain is out of quota
EXIT_SCOPE = 4        # files outside the allowed list changed
EXIT_NO_RESULT = 5    # agy returned nothing usable (timeout, error, empty payload)
EXIT_ESCALATE = 6     # too many fix rounds; ask the user
EXIT_SECRET = 7       # a secret-looking string or protected file is staged
EXIT_CONFLICT = 8     # rebase onto the base branch hit conflicts
EXIT_TESTS = 9        # build or tests failed

DEFAULT_PROFILE = {
    'version': 1,
    'language': {'docs': 'zh-TW', 'commits': 'zh-TW', 'prompts': 'zh-TW'},
    'knowledge_base': ['CLAUDE.md'],
    'remote': 'origin',
    'base_branch': 'main',
    'docs_dir': 'docs/rgs',
    'worktree_root': None,
    'worktree_copy': [],
    'shell': 'bash',
    'env': {},
    'secrets': {
        'deny_read': ['.env', '.env.*', '*.pem', '*.key', '*_KEY_*', '*.keystore', '*.jks'],
        'patterns': [],
    },
    'commands': {'quick': [], 'verify': []},
    'agy': {
        'implementer': {'models': ['gemini-3.8-flash-high'], 'timeout_s': 3600, 'allow_commands': []},
        'reviewer': {
            'models': ['gemini-3.8-flash-high'], 'timeout_s': 1800,
            'lenses': ['security', 'correctness', 'architecture', 'spec-tests-docs'],
        },
        'batch': {'models': ['gemini-3.8-flash-low'], 'workers': 8, 'batch_size': 40, 'timeout_s': 900},
        'digest': {'models': ['gemini-3.8-flash-high'], 'workers': 4, 'chunk_lines': 800, 'timeout_s': 900},
        'max_fix_rounds': 4,
        'fresh_after_input_tokens': 400000,
    },
    'pr': {'post_review_comment': True},
}

QUOTA_MARKERS = re.compile(
    r'RESOURCE_EXHAUSTED|individual quota|quota (reached|exceeded)|rate.?limit|out of credits|\b429\b', re.I)


class RgsError(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


def emit(obj):
    """Print a JSON summary for Claude to read."""
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- processes and git

def run(cmd, cwd=None, check=True, env=None, input_text=None, timeout=None):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, encoding='utf-8', errors='replace',
                          env=env, input=input_text, timeout=timeout,
                          stdin=None if input_text is not None else subprocess.DEVNULL)
    if check and proc.returncode != 0:
        shown = ' '.join(str(c) for c in cmd[:4])
        raise RgsError(f'{shown} failed ({proc.returncode}): {(proc.stderr or proc.stdout).strip()[:800]}')
    return proc


def git(args, cwd, check=True):
    return run(['git', *args], cwd=cwd, check=check).stdout.strip()


def find_gh():
    """argv prefix for the GitHub CLI. RGS_GH overrides it (a .py file runs with this Python; used by tests)."""
    override = os.environ.get('RGS_GH')
    if override:
        return [sys.executable, override] if override.endswith('.py') else [override]
    found = shutil.which('gh')
    if found:
        return [found]
    raise RgsError('GitHub CLI (gh) not found; install it and run gh auth login')


def gh(args, cwd, check=True):
    return run([*find_gh(), *args], cwd=cwd, check=check)


def decode_output(data):
    """Child process output: UTF-8 when it decodes as UTF-8, else the Windows ANSI code page (e.g. cp950)."""
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        import locale
        encoding = locale.getencoding() if hasattr(locale, 'getencoding') else locale.getpreferredencoding(False)
        return data.decode(encoding or 'utf-8', 'replace')


def repo_root(path='.'):
    try:
        return os.path.normpath(git(['rev-parse', '--show-toplevel'], cwd=path))
    except RgsError:
        raise RgsError(f'{os.path.abspath(path)} is not inside a git repository')


def main_checkout(path='.'):
    """The primary checkout, even when called from inside a linked worktree."""
    common = git(['rev-parse', '--path-format=absolute', '--git-common-dir'], cwd=path)
    return os.path.normpath(os.path.dirname(common))


def has_remote(repo, remote):
    return remote in git(['remote'], cwd=repo, check=False).split()


def changed_files(cwd):
    """Paths changed in the working tree (tracked and untracked), relative to cwd, '/' separated."""
    out = run(['git', 'status', '--porcelain', '--untracked-files=all', '-z'], cwd=cwd).stdout
    files, parts, i = [], out.split('\0'), 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if not entry:
            continue
        status, path = entry[:2], entry[3:]
        if status[0] in 'RC':
            i += 1  # the original path of a rename follows
        files.append((status, path.replace('\\', '/')))
    return files


# ---------------------------------------------------------------- profile, state, paths

def deep_merge(base, extra):
    out = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def rgs_dir(repo):
    return os.path.join(repo, '.rgs')


def load_profile(repo):
    path = os.path.join(rgs_dir(repo), 'profile.json')
    if not os.path.exists(path):
        return copy.deepcopy(DEFAULT_PROFILE), False
    with open(path, encoding='utf-8') as f:
        return deep_merge(DEFAULT_PROFILE, json.load(f)), True


def worktree_root(repo, profile):
    root = profile.get('worktree_root')
    if root:
        return os.path.normpath(os.path.join(repo, root))
    return os.path.normpath(os.path.join(os.path.dirname(repo), os.path.basename(repo) + '.rgs'))


def run_dir(repo, task):
    path = os.path.join(rgs_dir(repo), 'runs', task)
    os.makedirs(path, exist_ok=True)
    return path


def ensure_rgs_gitignore(repo):
    os.makedirs(rgs_dir(repo), exist_ok=True)
    path = os.path.join(rgs_dir(repo), '.gitignore')
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write('# rgs working files: run logs, agy output and resume state\nstate.json\nruns/\n')


def load_state(repo):
    path = os.path.join(rgs_dir(repo), 'state.json')
    if not os.path.exists(path):
        return {'tasks': {}}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save_state(repo, state):
    ensure_rgs_gitignore(repo)
    path = os.path.join(rgs_dir(repo), 'state.json')
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def get_task(repo, task):
    state = load_state(repo)
    if task not in state['tasks']:
        raise RgsError(f'unknown task {task!r}; run prepare first (known: {", ".join(state["tasks"]) or "none"})')
    return state, state['tasks'][task]


def update_task(repo, task, **fields):
    state = load_state(repo)
    entry = state['tasks'].setdefault(task, {})
    entry.update(fields)
    entry['updated'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    save_state(repo, state)
    return entry


def match_any(rel, patterns):
    rel = rel.replace('\\', '/')
    name = rel.rsplit('/', 1)[-1]
    for pattern in patterns:
        p = pattern.replace('\\', '/')
        if fnmatch.fnmatch(rel.lower(), p.lower()) or fnmatch.fnmatch(name.lower(), p.lower()):
            return True
        if p.endswith('/**') and rel.lower().startswith(p[:-3].lower() + '/'):
            return True
    return False


def write_text(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


def read_text(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def render_template(name, repo=None, **values):
    """Load a template (project override in .rgs/templates first) and fill {{key}} placeholders."""
    candidates = []
    if repo:
        candidates.append(os.path.join(rgs_dir(repo), 'templates', name))
    candidates.append(os.path.join(TEMPLATES, name))
    for path in candidates:
        if os.path.exists(path):
            text = read_text(path)
            break
    else:
        raise RgsError(f'template {name} not found')
    for key, value in values.items():
        text = text.replace('{{' + key + '}}', str(value))
    return text


def parse_allowed_files(spec_text):
    """Collect the backticked paths listed under the spec's 'files you may change' heading."""
    heading = re.compile(r'^#{2,4}\s*(可修改的檔案|允許修改的檔案|Files you may (change|modify)|Allowed files)', re.I)
    allowed, inside = [], False
    for line in spec_text.splitlines():
        if line.lstrip().startswith('#'):
            inside = bool(heading.match(line.strip()))
            continue
        if inside:
            m = re.match(r'\s*[-*]\s+`([^`]+)`', line)
            if m:
                allowed.append(m.group(1).strip().replace('\\', '/'))
    return allowed


# ---------------------------------------------------------------- guard installation

def guard_hook_command():
    exe = sys.executable
    return (f'"{exe}"' if ' ' in exe else exe) + ' -I rgs-guard.py'


def exclude_in_git(worktree, patterns):
    common = git(['rev-parse', '--path-format=absolute', '--git-common-dir'], cwd=worktree)
    path = os.path.join(common, 'info', 'exclude')
    existing = read_text(path) if os.path.exists(path) else ''
    lines = [p for p in patterns if p not in existing.splitlines()]
    if lines:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'a', encoding='utf-8', newline='\n') as f:
            if existing and not existing.endswith('\n'):
                f.write('\n')
            f.write('\n'.join(['# rgs guard files', *lines]) + '\n')


def install_guard(workspace, policy):
    """Put rgs-guard.py, its policy and a PreToolUse hook into <workspace>/.agents.

    If the project already tracks .agents/hooks.json, our hook is merged into it and
    remove_guard() restores the tracked file afterwards.
    """
    agents = os.path.join(workspace, '.agents')
    os.makedirs(agents, exist_ok=True)
    shutil.copyfile(GUARD_SRC, os.path.join(agents, 'rgs-guard.py'))
    write_text(os.path.join(agents, 'rgs-guard.json'), json.dumps(policy, ensure_ascii=False, indent=2))
    log = os.path.join(agents, 'rgs-guard.log')
    if not os.path.exists(log):
        write_text(log, '')
    hooks_path = os.path.join(agents, 'hooks.json')
    tracked = False
    hooks = {}
    if os.path.exists(hooks_path):
        tracked = bool(git(['ls-files', '.agents/hooks.json'], cwd=workspace, check=False))
        try:
            hooks = json.loads(read_text(hooks_path))
        except ValueError:
            hooks = {}
    hooks['rgs-guard'] = {'PreToolUse': [{'matcher': '*', 'hooks': [
        {'type': 'command', 'command': guard_hook_command(), 'timeout': 20}]}]}
    write_text(hooks_path, json.dumps(hooks, ensure_ascii=False, indent=2))
    patterns = ['/.agents/rgs-guard.py', '/.agents/rgs-guard.json', '/.agents/rgs-guard.log']
    if not tracked:
        patterns.append('/.agents/hooks.json')
    if os.path.isdir(workspace) and os.path.exists(os.path.join(workspace, '.git')):
        exclude_in_git(workspace, patterns)
    return {'hooks_tracked': tracked}


def remove_guard(workspace, hooks_tracked):
    agents = os.path.join(workspace, '.agents')
    for name in ('rgs-guard.py', 'rgs-guard.json', 'rgs-guard.log'):
        try:
            os.remove(os.path.join(agents, name))
        except FileNotFoundError:
            pass
    if hooks_tracked:
        git(['checkout', '--', '.agents/hooks.json'], cwd=workspace, check=False)
    else:
        try:
            os.remove(os.path.join(agents, 'hooks.json'))
        except FileNotFoundError:
            pass
        try:
            os.rmdir(agents)
        except OSError:
            pass


def isolated_workspace(prefix, files=None, deny=(), read_commands=False):
    """An empty temp folder (plus the given files) guarded read-only, for agy calls that need no repo."""
    import tempfile
    path = tempfile.mkdtemp(prefix=prefix)
    for name, text in (files or {}).items():
        write_text(os.path.join(path, name), text)
    install_guard(path, {'role': 'reviewer', 'roots': [path], 'write_allow': [], 'deny_read': list(deny),
                         'read_commands': read_commands, 'allow_commands': []})
    return path


GUARD_FILES = ('.agents/rgs-guard.py', '.agents/rgs-guard.json', '.agents/rgs-guard.log', '.agents/hooks.json')
TASK_INPUTS = '.rgs-task'  # implementer inputs inside the task worktree, excluded from git and never committed


def guard_log_since(workspace, offset):
    """Guard decisions written after byte offset; returns (entries, new_offset)."""
    path = os.path.join(workspace, '.agents', 'rgs-guard.log')
    if not os.path.exists(path):
        return [], offset
    with open(path, 'rb') as f:
        f.seek(offset)
        data = f.read()
    entries = []
    for line in data.decode('utf-8', 'replace').splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            pass
    return entries, offset + len(data)


def guard_log_size(workspace):
    path = os.path.join(workspace, '.agents', 'rgs-guard.log')
    return os.path.getsize(path) if os.path.exists(path) else 0


# ---------------------------------------------------------------- agy

FORBIDDEN_ALWAYS = ('--dangerously-skip-permissions', '--yolo', '-i', '--prompt-interactive',
                    '--remote-control', '--sandbox')
FORBIDDEN_FOR_REVIEWER = ('--mode', '--add-dir', '--conversation', '-c', '--continue')
IMPLEMENTER_MODES = ('accept-edits',)
VALUE_FLAGS = ('-p', '--model', '--output-format', '--print-timeout', '--mode', '--json-schema',
               '--conversation', '--add-dir', '--log-file')


def check_agy_args(args, role, model):
    """Raise RgsError(code=2) when these agy arguments are not allowed for the role (design D-14).

    args is the argument list after the agy executable. The value after a flag in VALUE_FLAGS is
    not a flag: the prompt may well contain text such as "--yolo".
    """
    if role not in ('implementer', 'reviewer'):
        raise RgsError(f"unknown role: {role!r}", code=2)
    if not isinstance(model, str) or not model.startswith('gemini-'):
        raise RgsError(
            f"invalid model {model!r}: rgs 只用 Gemini 模型；agy 的預設模型可能是 Claude，所以必須明確指定 gemini-…",
            code=2,
        )

    i = 0
    n = len(args)
    while i < n:
        item = args[i]
        if '=' in item:
            flag, _, val = item.partition('=')
            has_eq = True
        else:
            flag = item
            val = args[i + 1] if i + 1 < n else None
            has_eq = False

        if flag in FORBIDDEN_ALWAYS:
            raise RgsError(f"flag '{flag}' is forbidden for role '{role}'", code=2)

        if role == 'reviewer' and flag in FORBIDDEN_FOR_REVIEWER:
            raise RgsError(f"flag '{flag}' is forbidden for role '{role}'", code=2)

        if role == 'implementer' and flag == '--mode':
            if val not in IMPLEMENTER_MODES:
                raise RgsError(f"mode '{val}' is not allowed for role '{role}' (--mode)", code=2)

        if flag in VALUE_FLAGS:
            if has_eq:
                i += 1
            else:
                i += 2
        else:
            i += 1


def popen_kwargs():
    """Start a process in its own group so kill_tree() can stop everything it starts."""
    if os.name == 'nt':
        return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    return {'start_new_session': True}


def kill_tree(proc):
    """Stop proc and every process it started (design D-15)."""
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                       capture_output=True, stdin=subprocess.DEVNULL)
    else:
        import signal
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=10)
        except (subprocess.TimeoutExpired, OSError):
            pass
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def reported_model_from_log(path):
    """Return the last model label recorded by agy in path, or None."""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            content = f.read()
    except OSError:
        return None
    matches = re.findall(r'label="([^"]*)"', content)
    return matches[-1] if matches else None


def find_agy():
    """argv prefix for agy. RGS_AGY overrides it (a .py file runs with this Python; used by tests)."""
    override = os.environ.get('RGS_AGY')
    if override:
        return [sys.executable, override] if override.endswith('.py') else [override]
    local = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'agy', 'bin', 'agy.exe')
    if os.path.exists(local):
        return [local]
    found = shutil.which('agy')
    if found:
        return [found]
    raise RgsError('agy (Antigravity CLI) not found; install it or set RGS_AGY')


class AgyResult:
    def __init__(self, kind, model, data=None, stderr='', returncode=None, detail='',
                 reported_model=None):
        self.kind = kind            # ok | empty | error | quota | timeout
        self.model = model
        self.data = data or {}
        self.stderr = stderr
        self.returncode = returncode
        self.detail = detail
        self.reported_model = reported_model

    @property
    def ok(self):
        return self.kind == 'ok'

    @property
    def response(self):
        return self.data.get('response') or ''

    @property
    def structured(self):
        return self.data.get('structured_output')

    @property
    def conversation_id(self):
        return self.data.get('conversation_id')

    @property
    def usage(self):
        return self.data.get('usage') or {}

    def summary(self):
        return {'kind': self.kind, 'model': self.model, 'reported_model': self.reported_model,
                'conversation_id': self.conversation_id,
                'status': self.data.get('status'), 'duration_s': self.data.get('duration_seconds'),
                'usage': self.usage, 'detail': self.detail}


def classify(returncode, stdout, stderr, model, want_structured, reported_model=None):
    try:
        data = json.loads(stdout) if stdout.strip() else None
    except ValueError:
        data = None
    if data is None:
        # The JSON may be preceded by prose; take the last line that parses.
        for line in reversed(stdout.strip().splitlines()):
            try:
                data = json.loads(line)
                break
            except ValueError:
                continue
    error_text = stderr + ' ' + (json.dumps(data.get('error'), ensure_ascii=False) if data and data.get('error') else '')
    if returncode != 0 or data is None or data.get('status') != 'SUCCESS':
        kind = 'quota' if QUOTA_MARKERS.search(error_text) else 'error'
        return AgyResult(kind, model, data, stderr, returncode,
                         detail=(error_text.strip() or stdout.strip())[:600],
                         reported_model=reported_model)
    if 'print timeout' in stderr:
        return AgyResult('timeout', model, data, stderr, returncode, detail=stderr.strip()[:300],
                         reported_model=reported_model)
    if want_structured:
        if not data.get('structured_output'):
            return AgyResult('empty', model, data, stderr, returncode,
                             detail='no structured_output (the model may have stopped before answering)',
                             reported_model=reported_model)
    elif not (data.get('response') or '').strip():
        return AgyResult('empty', model, data, stderr, returncode, detail='empty response',
                         reported_model=reported_model)
    return AgyResult('ok', model, data, stderr, returncode, reported_model=reported_model)


def call_agy(prompt, cwd, model, mode=None, schema_path=None, conversation=None, add_dirs=(),
             timeout_s=900, save_as=None, role='reviewer', grace_s=180):
    """Run one agy print-mode turn. save_as: path prefix for .json/.err/.prompt.md/.log copies.
    Log is written to a system temp file and copied to save_as + '.log' after agy exits, so agy's
    arguments never include paths under the main checkout.
    """
    prefix = find_agy()
    cmd = [*prefix, '-p', prompt, '--model', model, '--output-format', 'json',
           '--disable-slash-commands', '--print-timeout', f'{int(timeout_s)}s']
    if mode:
        cmd += ['--mode', mode]
    if schema_path:
        cmd += ['--json-schema', schema_path]
    if conversation:
        cmd += ['--conversation', conversation]
    for d in add_dirs:
        cmd += ['--add-dir', d]

    fd, log_path = tempfile.mkstemp(prefix='rgs_agy_', suffix='.log')
    os.close(fd)

    try:
        cmd += ['--log-file', log_path]
        check_agy_args(cmd[len(prefix):], role, model)

        if save_as:
            write_text(save_as + '.prompt.md', prompt)
        env = dict(os.environ, MSYS_NO_PATHCONV='1')
        started = time.time()
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL, env=env, **popen_kwargs())
        try:
            out, err = proc.communicate(timeout=timeout_s + grace_s)
        except subprocess.TimeoutExpired:
            kill_tree(proc)
            try:
                out, err = proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                # A grandchild may still hold the pipes open; give up on the output.
                proc.kill()
                out, err = b'', b''
            stdout = (out or b'').decode('utf-8', 'replace')
            stderr = (err or b'').decode('utf-8', 'replace')
            reported = reported_model_from_log(log_path)
            result = AgyResult('timeout', model, None, stderr, None,
                               detail=f'killed after {int(time.time() - started)}s',
                               reported_model=reported)
        else:
            stdout = out.decode('utf-8', 'replace')
            stderr = err.decode('utf-8', 'replace')
            reported = reported_model_from_log(log_path)
            result = classify(proc.returncode, stdout, stderr, model, bool(schema_path),
                              reported_model=reported)

        if save_as:
            write_text(save_as + '.json', stdout)
            write_text(save_as + '.err', stderr)
            if os.path.exists(log_path):
                shutil.copyfile(log_path, save_as + '.log')
        return result
    finally:
        if log_path and os.path.exists(log_path):
            try:
                os.remove(log_path)
            except OSError:
                pass


def call_with_fallback(models, **kwargs):
    """Try each model in turn while the previous one is out of quota."""
    if isinstance(models, str):
        models = [models]
    tried = []
    result = None
    for model in models:
        result = call_agy(model=model, **kwargs)
        tried.append(result.kind)
        if result.kind != 'quota':
            break
    result.tried = list(zip(models, tried))
    return result


def exit_code_for(result):
    if result.ok:
        return EXIT_OK
    return EXIT_QUOTA if result.kind == 'quota' else EXIT_NO_RESULT


def shell_cmd(command, profile):
    shell = profile.get('shell') or 'bash'
    if shell == 'bash' and shutil.which('bash'):
        return ['bash', '-lc', command]
    if shell in ('powershell', 'bash'):
        return ['powershell', '-NoProfile', '-Command', command]
    return ['cmd', '/c', command]


def run_commands(commands, cwd, profile, log_prefix, timeout_s=3600):
    """Run profile commands in order; stop at the first failure. Returns a list of result dicts."""
    env = dict(os.environ, **{k: str(v) for k, v in (profile.get('env') or {}).items()})
    env.setdefault('MSYS_NO_PATHCONV', '1')
    results = []
    for i, command in enumerate(commands, 1):
        started = time.time()
        try:
            proc = subprocess.run(shell_cmd(command, profile), cwd=cwd, capture_output=True, env=env,
                                  stdin=subprocess.DEVNULL, timeout=timeout_s)
            code = proc.returncode
            output = decode_output(proc.stdout) + decode_output(proc.stderr)
        except subprocess.TimeoutExpired:
            code, output = -1, f'timed out after {timeout_s}s'
        log = f'{log_prefix}-{i}.log'
        write_text(log, f'$ {command}\n{output}')
        results.append({'command': command, 'exit': code, 'seconds': round(time.time() - started, 1),
                        'log': log, 'tail': output.strip().splitlines()[-15:]})
        if code != 0:
            break
    return results
