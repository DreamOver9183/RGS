"""Check that a worktree only changed the files a spec allows, and catch common formatting slips.

Usage:
    python -I scope_check.py --task <id>                      # uses the task's worktree and allow list
    python -I scope_check.py --worktree <path> --allow a.py --allow "tests/*.py"

Exit code 0 = clean, 4 = files outside the allow list changed or a formatting problem was found.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rgs_common as rc  # noqa: E402

TEXT_EXT = {'.py', '.kt', '.kts', '.java', '.cs', '.ts', '.tsx', '.js', '.jsx', '.json', '.md', '.xml',
            '.yml', '.yaml', '.toml', '.gradle', '.txt', '.go', '.rs', '.c', '.h', '.cpp', '.hpp',
            '.swift', '.rb', '.php', '.html', '.css', '.scss', '.sh', '.ps1', '.sql', '.csv', '.ini'}


def format_problems(path):
    problems = []
    if os.path.splitext(path)[1].lower() not in TEXT_EXT or not os.path.isfile(path):
        return problems
    with open(path, 'rb') as f:
        data = f.read()
    if not data:
        return problems
    if b'\0' in data[:4096]:
        return problems
    if not data.endswith(b'\n'):
        problems.append('missing final newline')
    elif data.endswith(b'\n\n') or data.endswith(b'\r\n\r\n'):
        problems.append('extra blank line(s) at end of file')
    for marker in (b'<<<<<<< ', b'>>>>>>> '):
        if b'\n' + marker in b'\n' + data:
            problems.append('merge conflict marker')
            break
    return problems


def check(worktree, allowed, ignore=()):
    ignore = list(rc.GUARD_FILES) + [rc.TASK_INPUTS + '/**'] + list(ignore)
    changed = [(s, p) for s, p in rc.changed_files(worktree) if not rc.match_any(p, ignore)]
    outside = [p for _, p in changed if not rc.match_any(p, allowed)]
    formatting = {}
    for status, rel in changed:
        if 'D' in status:
            continue
        problems = format_problems(os.path.join(worktree, rel))
        if problems:
            formatting[rel] = problems
    return {
        'ok': not outside and not formatting,
        'changed': [p for _, p in changed],
        'deleted': [p for s, p in changed if 'D' in s],
        'outside_allowed': outside,
        'formatting': formatting,
    }


def main():
    rc.setup_stdio()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--task')
    ap.add_argument('--worktree')
    ap.add_argument('--allow', action='append', default=[])
    ap.add_argument('--ignore', action='append', default=[], help='extra paths/globs to skip (e.g. docs/rgs/**)')
    args = ap.parse_args()
    try:
        if args.task:
            repo = rc.main_checkout('.')
            _, task = rc.get_task(repo, args.task)
            worktree, allowed = task['worktree'], task['allowed'] + args.allow
        elif args.worktree:
            worktree, allowed = args.worktree, args.allow
        else:
            ap.error('give --task or --worktree')
        result = check(worktree, allowed, args.ignore)
    except rc.RgsError as e:
        print(f'error: {e}', file=sys.stderr)
        return e.code
    rc.emit(result)
    return rc.EXIT_OK if result['ok'] else rc.EXIT_SCOPE


if __name__ == '__main__':
    sys.exit(main())
