"""Check the environment for rgs and (with --init) draft the project's .rgs/profile.json.

Usage (from inside the project):
    python -I doctor.py [--quick] [--flow main|pr] [--init] [--json]

--quick skips the slower network checks (agy models list, quota table, gh auth).
--init writes .rgs/profile.json from what it detects (never overwrites) and .rgs/.gitignore,
and prints the Claude Code permission rules the user can add themselves.
Exit code 0 = no failures (warnings allowed), 1 = at least one failure.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rgs_common as rc  # noqa: E402

MIN_AGY = (1, 4, 0)


def version_tuple(text):
    m = re.search(r'(\d+)\.(\d+)\.(\d+)', text or '')
    return tuple(int(x) for x in m.groups()) if m else None


def quiet(cmd, cwd=None, timeout=60, env=None):
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, encoding='utf-8', errors='replace',
                              stdin=subprocess.DEVNULL, timeout=timeout, env=env)
        return proc.returncode, (proc.stdout or '') + (proc.stderr or '')
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, str(e)


def detect_profile(repo):
    """Best guess at commands, knowledge base and protected files; the user confirms the result."""
    profile = {'version': 1, 'language': {'docs': 'zh-TW', 'commits': 'zh-TW', 'prompts': 'zh-TW'}}
    kb = [n for n in ('CLAUDE.md', 'AGENTS.md', 'GEMINI.md') if os.path.exists(os.path.join(repo, n))]
    profile['knowledge_base'] = kb or ['CLAUDE.md']
    branch = rc.git(['symbolic-ref', '--quiet', '--short', 'refs/remotes/origin/HEAD'], cwd=repo, check=False)
    current = rc.git(['rev-parse', '--abbrev-ref', 'HEAD'], cwd=repo, check=False)
    if current in ('', 'HEAD'):  # detached, or no commit yet
        current = 'main'
    profile['base_branch'] = branch.split('/', 1)[1] if '/' in branch else current
    quick, verify, copy = [], [], []
    has = lambda *names: any(glob.glob(os.path.join(repo, n)) for n in names)  # noqa: E731
    if has('gradlew', 'gradlew.bat'):
        quick = ['./gradlew testDebugUnitTest'] if has('app') else ['./gradlew test']
        verify = ['./gradlew testDebugUnitTest lintDebug assembleDebug'] if has('app') else ['./gradlew build']
        if has('local.properties'):
            copy.append('local.properties')
    elif has('package.json'):
        try:
            scripts = json.load(open(os.path.join(repo, 'package.json'), encoding='utf-8')).get('scripts', {})
        except ValueError:
            scripts = {}
        quick = ['npm test'] if 'test' in scripts else []
        verify = quick + [f'npm run {s}' for s in ('lint', 'build') if s in scripts]
    elif has('*.sln', '*.csproj', 'Source/*.sln', 'src/*.sln'):
        quick = ['dotnet test']
        verify = ['dotnet build -warnaserror', 'dotnet format --verify-no-changes', 'dotnet test']
    elif has('Cargo.toml'):
        quick, verify = ['cargo test'], ['cargo clippy -- -D warnings', 'cargo test']
    elif has('go.mod'):
        quick, verify = ['go test ./...'], ['go vet ./...', 'go test ./...']
    elif has('pyproject.toml', 'setup.py', 'requirements*.txt', 'tests/test_*.py', 'test_*.py'):
        text = ''
        for name in ('pyproject.toml', 'requirements.txt', 'requirements-dev.txt'):
            if has(name):
                text += open(os.path.join(repo, name), encoding='utf-8', errors='replace').read()
        quick = ['python -m pytest -q'] if 'pytest' in text else ['python -m unittest discover -q']
        verify = list(quick)
    profile['commands'] = {'quick': quick, 'verify': verify}
    profile['worktree_copy'] = copy
    secrets = [os.path.basename(p) for pattern in ('*_KEY_*', '.env', '.env.*', '*.keystore', '*.jks',
                                                    'local.properties', 'google-services.json')
               for p in glob.glob(os.path.join(repo, pattern))]
    profile['secrets'] = {'deny_read': sorted(set(rc.DEFAULT_PROFILE['secrets']['deny_read'] + secrets)),
                          'patterns': []}
    return profile


def permission_rules():
    scripts = os.path.join(rc.CORE, 'scripts').replace('\\', '/')
    return [f'Bash(python -I {scripts}/{name}:*)' for name in
            ('rgs.py', 'review.py', 'doctor.py', 'batch.py', 'digest.py', 'scope_check.py', 'secret_scan.py')]


def main():
    rc.setup_stdio()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--flow', choices=['main', 'pr'], default='main')
    ap.add_argument('--init', action='store_true')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    checks = []

    def add(name, status, detail=''):
        checks.append({'check': name, 'status': status, 'detail': detail})

    add('python', 'ok' if sys.version_info >= (3, 10) else 'fail', sys.version.split()[0])
    try:
        agy = rc.find_agy()
        code, out = quiet([*agy, '--version'], timeout=30)
        ver = version_tuple(out)
        status = 'ok' if ver and ver >= MIN_AGY else 'warn'
        add('agy', status, f'{out.strip()[:40]} ({agy[-1]})' + ('' if status == 'ok' else '; rgs was verified on 1.4.0'))
    except rc.RgsError as e:
        agy = None
        add('agy', 'fail', str(e))

    repo = None
    try:
        repo = rc.main_checkout('.')
        add('git repo', 'ok', repo)
    except rc.RgsError as e:
        add('git repo', 'fail', str(e))
    profile, has_profile = (rc.load_profile(repo) if repo else (rc.DEFAULT_PROFILE, False))

    if repo and args.init and not has_profile:
        draft = detect_profile(repo)
        rc.ensure_rgs_gitignore(repo)
        rc.write_text(os.path.join(rc.rgs_dir(repo), 'profile.json'), json.dumps(draft, ensure_ascii=False, indent=2) + '\n')
        profile, has_profile = rc.load_profile(repo)
        add('profile', 'warn', '.rgs/profile.json drafted from detection: review commands, secrets and knowledge base')
    elif has_profile:
        missing = [k for k in ('quick', 'verify') if not profile['commands'].get(k)]
        add('profile', 'warn' if missing else 'ok',
            '.rgs/profile.json' + (f' (no {"/".join(missing)} commands)' if missing else ''))
    else:
        add('profile', 'warn', 'no .rgs/profile.json; run doctor.py --init')

    if repo:
        remote, base = profile['remote'], profile['base_branch']
        if rc.has_remote(repo, remote):
            url = rc.git(['remote', 'get-url', remote], cwd=repo, check=False)
            add('remote', 'ok', f'{remote} = {url}')
            rc.git(['fetch', '-q', remote, base], cwd=repo, check=False)
            counts = rc.git(['rev-list', '--left-right', '--count', f'{base}...{remote}/{base}'], cwd=repo, check=False)
            if counts:
                ahead, behind = counts.split()
                add('base branch', 'ok' if ahead == behind == '0' else 'warn',
                    f'{base}: {ahead} ahead / {behind} behind {remote}/{base}')
        else:
            add('remote', 'warn' if args.flow == 'main' else 'fail', f'no remote named {remote}')
        current = rc.git(['rev-parse', '--abbrev-ref', 'HEAD'], cwd=repo, check=False)
        add('current branch', 'ok' if current == base else 'warn', current)
        dirty = [p for _, p in rc.changed_files(repo) if not p.startswith('.rgs/')]
        add('working tree', 'ok' if not dirty else 'warn',
            'clean' if not dirty else f'{len(dirty)} changed file(s), e.g. {", ".join(dirty[:3])}')
        kb_missing = [k for k in profile.get('knowledge_base') or [] if not os.path.exists(os.path.join(repo, k))]
        add('knowledge base', 'ok' if not kb_missing else 'warn',
            'present' if not kb_missing else f'missing {", ".join(kb_missing)} (create it from knowledge-base-skeleton.md)')
        root = rc.worktree_root(repo, profile)
        in_temp = os.path.normcase(root).startswith(os.path.normcase(tempfile.gettempdir()))
        add('worktree root', 'warn' if in_temp else 'ok',
            root + (' (inside %TEMP%: Smart App Control can block test DLLs there)' if in_temp else ''))

    if not args.quick:
        if agy:
            code, out = quiet([*agy, 'models'], timeout=60)
            wanted = sorted({m for role in ('implementer', 'reviewer', 'batch', 'digest')
                             for m in profile['agy'][role]['models']})
            absent = [m for m in wanted if m not in out]
            add('agy models', 'ok' if code == 0 and not absent else 'warn',
                'all configured models available' if not absent else f'not listed: {", ".join(absent)}')
            code, out = quiet([*agy, '-p', '/usage'], timeout=90, env=dict(os.environ, MSYS_NO_PATHCONV='1'))
            add('agy quota', 'ok' if code == 0 else 'warn', ' | '.join(out.strip().splitlines()[:8])[:600])
        if args.flow == 'pr':
            if shutil.which('gh'):
                code, out = quiet(['gh', 'auth', 'status'], timeout=30)
                add('gh auth', 'ok' if code == 0 else 'fail', out.strip().splitlines()[0][:120] if out.strip() else '')
            else:
                add('gh', 'fail', 'GitHub CLI not found')

    failures = [c for c in checks if c['status'] == 'fail']
    result = {'ok': not failures, 'checks': checks}
    if args.init:
        result['permission_rules'] = permission_rules()
        result['permission_note'] = ('Claude cannot edit its own settings; the user can add these to '
                                     '.claude/settings.json permissions.allow to avoid repeated prompts.')
    if args.json:
        rc.emit(result)
    else:
        for c in checks:
            mark = {'ok': 'OK  ', 'warn': 'WARN', 'fail': 'FAIL'}[c['status']]
            print(f'[{mark}] {c["check"]}: {c["detail"]}')
        if args.init:
            print('\nPermission rules the user may add (permissions.allow):')
            for rule in result['permission_rules']:
                print('  ' + rule)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
