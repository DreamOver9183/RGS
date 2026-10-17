"""PreToolUse guard for agy (Antigravity CLI) runs started by rgs.

agy runs every hook command with the working directory set to the folder that holds hooks.json
(`<workspace>/.agents`). This script reads the tool call as JSON on stdin and prints
{"decision": "allow"|"deny", "reason": ...}. Policy comes from rgs-guard.json next to it:

    {
      "role": "implementer" | "reviewer" | "sealed",
      "roots": ["<workspace root>", "<extra read-only root>", ...],
      "write_allow": ["src/app.py", "tests/*.py"],   # relative to roots[0]; implementer only
      "deny_read": ["local.properties", "*_KEY_*", ".env*"],
      "read_commands": true,                        # allow read-only listing/search commands
      "allow_commands": []                          # exact command lines the implementer may run
    }

The sealed role allows only finish (used to deliver --json-schema results) and wait;
the model cannot read, list, run commands or start subagents.

agy 1.4.0 has no separate list or search tool; the model lists and searches files with
run_command (PowerShell). With read_commands on, a command is allowed only when every pipeline
segment starts with a known read-only verb, it has no shell metacharacters that could chain or
redirect, and every absolute path in it stays inside the roots and outside deny_read.

Every decision is appended to rgs-guard.log so the caller can see what was denied (agy itself
still reports SUCCESS when a tool is denied). Anything unexpected is denied: a crash also blocks
the call, because agy treats a failing hook as a denial.
"""
import fnmatch
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
POLICY_FILE = os.path.join(HERE, 'rgs-guard.json')
LOG_FILE = os.path.join(HERE, 'rgs-guard.log')

# Tools that only read. Their path arguments must stay inside the roots and outside deny_read.
READ_TOOLS = {
    'view_file', 'view_file_outline', 'view_code_item', 'view_content_chunk',
    'list_dir', 'grep_search', 'find_by_name', 'codebase_search',
}
READ_PREFIXES = ('view_', 'list_', 'find_', 'grep_')
# Tools that write files. Only the implementer may use them, and only on write_allow paths.
WRITE_TOOLS = {'write_to_file', 'replace_file_content', 'multi_replace_file_content'}
# Tools that neither read the disk nor change it.
NEUTRAL_TOOLS = {'finish', 'wait', 'task_boundary', 'notify_user', 'invoke_subagent', 'send_message',
                 'manage_subagents'}
SEALED_TOOLS = {'finish', 'wait'}

PATH_KEY = re.compile(r'(path|file|dir|directory|folder|uri|cwd)s?$', re.IGNORECASE)

# Read-only command verbs (PowerShell names, their aliases, and read-only git/rg forms).
READ_VERBS = re.compile(
    r'^(get-childitem|gci|ls|dir|get-content|gc|cat|type|select-string|sls|get-item|test-path|'
    r'resolve-path|measure-object|select-object|where-object|sort-object|format-table|format-list|'
    r'out-string|rg|findstr|git\s+(grep|ls-files|log|show|diff|status|blame|rev-parse))\b',
    re.IGNORECASE)
# Chaining, redirection, subexpressions and script blocks could run anything.
UNSAFE_COMMAND = re.compile(r'[;&<>`{}]|\$\(|@\(|\.\.[\\/]|--output|--pre\b', re.IGNORECASE)
# Quoted paths may contain spaces ("D:\Claude Code\x"); unquoted ones end at whitespace.
ABS_PATH = re.compile(r'"([A-Za-z]:[\\/][^"]*)"|\'([A-Za-z]:[\\/][^\']*)\'|([A-Za-z]:[\\/][^\s"\'|,]*)')


def norm(path, base):
    path = str(path).strip().strip('"')
    if path.lower().startswith('file:///'):
        path = path[8:]
    path = path.replace('/', os.sep)
    if not os.path.isabs(path):
        path = os.path.join(base, path)
    return os.path.normcase(os.path.realpath(path))


def path_args(args):
    found = []
    for key, value in args.items():
        if not PATH_KEY.search(key):
            continue
        values = value if isinstance(value, list) else [value]
        found += [v for v in values if isinstance(v, str) and v.strip()]
    return found


def inside(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def matches(rel, patterns):
    rel = rel.replace(os.sep, '/')
    name = rel.rsplit('/', 1)[-1]
    for pattern in patterns:
        p = os.path.normcase(pattern.replace('\\', '/')).replace(os.sep, '/')
        if fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(name, p):
            return True
    return False


def decide(policy, call):
    name = call.get('name', '')
    args = call.get('args') or {}
    if policy.get('role') == 'sealed':
        if name in SEALED_TOOLS:
            return None
        return f'{name}: only finish and wait are allowed in a sealed run'
    roots = [norm(r, HERE) for r in policy['roots']]
    base = roots[0]
    deny_read = [os.path.normcase(p) for p in policy.get('deny_read', [])]

    def check_paths(require_paths):
        paths = [norm(p, base) for p in path_args(args)]
        if require_paths and not paths:
            return f'{name}: no path argument found'
        for p in paths:
            root = next((r for r in roots if inside(p, r)), None)
            if root is None:
                return f'{name}: {p} is outside the allowed folders'
            rel = os.path.relpath(p, root)
            if matches(rel, deny_read):
                return f'{name}: {rel} is a protected file'
            if rel.split(os.sep)[0] == '.agents':
                return f'{name}: the .agents folder is off limits'
        return None

    if name in NEUTRAL_TOOLS:
        return None
    if name in READ_TOOLS or name.startswith(READ_PREFIXES):
        return check_paths(require_paths=False)
    if name in WRITE_TOOLS:
        if policy.get('role') != 'implementer':
            return f'{name}: this run is read-only'
        problem = check_paths(require_paths=True)
        if problem:
            return problem
        allowed = [os.path.normcase(p) for p in policy.get('write_allow', [])]
        for p in (norm(p, base) for p in path_args(args)):
            if not inside(p, base):
                return f'{name}: writes must stay inside the workspace'
            rel = os.path.relpath(p, base)
            if not matches(rel, allowed):
                return f'{name}: {rel} is not in the list of files this task may change'
        return None
    if name == 'run_command':
        command = str(args.get('CommandLine', '')).strip()
        if policy.get('role') == 'implementer' and command in policy.get('allow_commands', []):
            return check_paths(require_paths=False)
        if policy.get('read_commands', True):
            problem = check_read_command(command, roots, deny_read)
            if problem is None:
                return check_paths(require_paths=False)
            return f'run_command: {problem}'
        return 'run_command: shell commands are not allowed in this run'
    return f'{name}: tool not allowed in this run'


def check_read_command(command, roots, deny_read):
    rejected = ('only read-only listing and search commands are allowed '
                '(Get-ChildItem, Get-Content, Select-String, rg, git grep/log/diff/show); '
                'builds and tests are run by the reviewer')
    if not command or UNSAFE_COMMAND.search(command):
        return rejected
    for segment in command.split('|'):
        if not READ_VERBS.match(segment.strip()):
            return rejected
    lowered = os.path.normcase(command.replace('/', os.sep))
    for pattern in deny_read:
        literal = pattern.replace('*', '').replace('?', '')
        if literal and literal in lowered:
            return f'the command mentions a protected file ({pattern})'
    for groups in ABS_PATH.findall(command):
        p = norm(next(g for g in groups if g), roots[0])
        if not any(inside(p, r) for r in roots):
            return f'{p} is outside the allowed folders'
    return None


def main():
    raw = sys.stdin.buffer.read().decode('utf-8', 'replace')
    name, target = '?', ''
    try:
        payload = json.loads(raw)
        call = payload.get('toolCall') or {}
        name = call.get('name', '?')
        args = call.get('args') or {}
        target = str(args.get('CommandLine') or ', '.join(path_args(args)))[:200]
        with open(POLICY_FILE, encoding='utf-8') as f:
            policy = json.load(f)
        reason = decide(policy, call)
    except Exception as e:  # deny on anything unexpected
        reason = f'rgs-guard error: {type(e).__name__}: {e}'
    decision = 'allow' if reason is None else 'deny'
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'time': time.strftime('%Y-%m-%dT%H:%M:%S'), 'tool': name, 'target': target,
                                'decision': decision, 'reason': reason}, ensure_ascii=False) + '\n')
    except OSError:
        pass
    out = {'decision': decision}
    if reason:
        out['reason'] = 'rgs-guard: ' + reason
    sys.stdout.write(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
