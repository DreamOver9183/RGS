"""Refuse to commit secrets: scan the staged diff (or given files) for key-like strings and protected files.

Usage:
    python -I secret_scan.py [--cwd <worktree>]            # staged changes (git diff --cached)
    python -I secret_scan.py --files a.txt b.md            # whole files, e.g. release notes or docs

Patterns: built-in key formats plus profile secrets.patterns; protected file names: secrets.deny_read.
Matches are printed masked. Exit code 0 = clean, 7 = something was found.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rgs_common as rc  # noqa: E402

BUILTIN = {
    'google-api-key': r'AIza[0-9A-Za-z_\-]{35}',
    'openai-key': r'sk-(proj-)?[A-Za-z0-9_\-]{32,}',
    'anthropic-key': r'sk-ant-[A-Za-z0-9_\-]{32,}',
    'github-token': r'(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,}',
    'aws-access-key': r'AKIA[0-9A-Z]{16}',
    'slack-token': r'xox[baprs]-[A-Za-z0-9\-]{10,}',
    'private-key': r'-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----',
    'assigned-secret': r'(?i)(api[_-]?key|secret|token|passw(or)?d)\s*[:=]\s*["\'][A-Za-z0-9_\-+/=]{16,}["\']',
}


def mask(text):
    text = text.strip()
    return text[:4] + '…' + text[-2:] if len(text) > 8 else '…'


def scan_lines(lines, patterns):
    """lines: iterable of (file, line_no, text). Returns a list of hits."""
    compiled = [(name, re.compile(p)) for name, p in patterns.items()]
    hits = []
    for file, line_no, text in lines:
        for name, rx in compiled:
            m = rx.search(text)
            if m:
                hits.append({'file': file, 'line': line_no, 'kind': name, 'match': mask(m.group(0))})
    return hits


def staged_lines(cwd):
    diff = rc.run(['git', 'diff', '--cached', '-U0', '--no-color', '--no-ext-diff'], cwd=cwd).stdout
    file, line_no = None, 0
    for line in diff.splitlines():
        if line.startswith('+++ '):
            file = line[6:] if line.startswith('+++ b/') else line[4:]
        elif line.startswith('@@'):
            m = re.search(r'\+(\d+)', line)
            line_no = int(m.group(1)) if m else 0
        elif line.startswith('+') and file:
            yield file, line_no, line[1:]
            line_no += 1


def staged_files(cwd):
    out = rc.run(['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z'], cwd=cwd).stdout
    return [p for p in out.split('\0') if p]


def file_lines(paths):
    for path in paths:
        with open(path, encoding='utf-8', errors='replace') as f:
            for i, text in enumerate(f, 1):
                yield path, i, text


def scan(cwd=None, files=None, profile=None):
    profile = profile or rc.DEFAULT_PROFILE
    patterns = dict(BUILTIN)
    for i, p in enumerate(profile['secrets'].get('patterns') or []):
        patterns[f'profile-{i + 1}'] = p
    deny = list(profile['secrets'].get('deny_read') or []) + list(profile.get('worktree_copy') or [])
    if files:
        hits = scan_lines(file_lines(files), patterns)
        protected = [f for f in files if rc.match_any(f.replace('\\', '/'), deny)]
    else:
        hits = scan_lines(staged_lines(cwd), patterns)
        protected = [f for f in staged_files(cwd) if rc.match_any(f, deny)]
    return {'ok': not hits and not protected, 'hits': hits, 'protected_files': protected}


def main():
    rc.setup_stdio()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--cwd', default='.')
    ap.add_argument('--files', nargs='*')
    args = ap.parse_args()
    try:
        repo = rc.main_checkout(args.cwd)
        profile, _ = rc.load_profile(repo)
    except rc.RgsError:
        profile = rc.DEFAULT_PROFILE
    result = scan(args.cwd, args.files, profile)
    rc.emit(result)
    return rc.EXIT_OK if result['ok'] else rc.EXIT_SECRET


if __name__ == '__main__':
    sys.exit(main())
