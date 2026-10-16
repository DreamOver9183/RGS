"""Stand-in for the GitHub CLI in tests, backed by the local bare remote. Environment variables:

FAKE_GH_DIR    folder for calls/ (one JSON file per invocation) and prs/<n>.json (the fake PR records)
FAKE_GH_FAIL   a subcommand that fails with exit 1, e.g. "pr create"

Supported: auth status; pr create | view | diff | comment | edit --base. Each PR also gets
refs/pull/<n>/head in the bare remote, as on GitHub, kept in step with the head branch.
"""
import json
import os
import subprocess
import sys
import time
import uuid


def arg(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


def git(args, git_dir):
    proc = subprocess.run(['git', '--git-dir', git_dir, *args], capture_output=True, encoding='utf-8')
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        sys.exit(1)
    return proc.stdout


def remote_dir():
    proc = subprocess.run(['git', 'remote', 'get-url', 'origin'], capture_output=True, encoding='utf-8')
    return proc.stdout.strip()


def pr_path(state, number):
    return os.path.join(state, 'prs', f'{number}.json')


def load_pr(state, number):
    path = pr_path(state, number)
    if not os.path.exists(path):
        sys.stderr.write(f'no pull requests found for {number}\n')
        sys.exit(1)
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save_pr(state, pr):
    os.makedirs(os.path.join(state, 'prs'), exist_ok=True)
    with open(pr_path(state, pr['number']), 'w', encoding='utf-8') as f:
        json.dump(pr, f, ensure_ascii=False)


def sync_head(pr):
    """Point refs/pull/<n>/head at the head branch tip and return that commit."""
    remote = remote_dir()
    oid = git(['rev-parse', f'refs/heads/{pr["head"]}'], remote).strip()
    git(['update-ref', f'refs/pull/{pr["number"]}/head', oid], remote)
    return oid


def main():
    argv = sys.argv[1:]
    state = os.environ.get('FAKE_GH_DIR') or os.path.join(os.getcwd(), '.fake_gh')
    calls = os.path.join(state, 'calls')
    os.makedirs(calls, exist_ok=True)
    with open(os.path.join(calls, f'{time.time_ns()}-{uuid.uuid4().hex[:6]}.json'), 'w', encoding='utf-8') as f:
        json.dump({'argv': argv, 'cwd': os.getcwd()}, f, ensure_ascii=False)
    command = ' '.join(argv[:2])
    if command == os.environ.get('FAKE_GH_FAIL'):
        sys.stderr.write(f'fake gh: {command} failed\n')
        sys.exit(1)

    if command == 'auth status':
        print('github.com\n  Logged in to github.com account tester')
    elif command == 'pr create':
        number = len(os.listdir(os.path.join(state, 'prs'))) + 1 if os.path.isdir(os.path.join(state, 'prs')) else 1
        with open(arg(argv, '--body-file'), encoding='utf-8') as f:
            body = f.read()
        pr = {'number': number, 'base': arg(argv, '--base'), 'head': arg(argv, '--head'),
              'title': arg(argv, '--title'), 'body': body, 'draft': '--draft' in argv,
              'state': 'OPEN', 'comments': []}
        sync_head(pr)
        save_pr(state, pr)
        print('Creating pull request for {} into {}'.format(pr['head'], pr['base']), file=sys.stderr)
        print(f'https://github.com/owner/repo/pull/{number}')
    elif command == 'pr view':
        pr = load_pr(state, argv[2])
        values = {'number': pr['number'], 'title': pr['title'], 'state': pr['state'],
                  'baseRefName': pr['base'], 'headRefName': pr['head'], 'headRefOid': sync_head(pr),
                  'url': f'https://github.com/owner/repo/pull/{pr["number"]}'}
        fields = (arg(argv, '--json') or '').split(',')
        print(json.dumps({k: values[k] for k in fields if k in values}))
    elif command == 'pr diff':
        pr = load_pr(state, argv[2])
        head = sync_head(pr)
        sys.stdout.write(git(['diff', f'refs/heads/{pr["base"]}...{head}'], remote_dir()))
    elif command == 'pr comment':
        pr = load_pr(state, argv[2])
        with open(arg(argv, '--body-file'), encoding='utf-8') as f:
            pr['comments'].append(f.read())
        save_pr(state, pr)
        print(f'https://github.com/owner/repo/pull/{pr["number"]}#issuecomment-{len(pr["comments"])}')
    elif command == 'pr edit':
        pr = load_pr(state, argv[2])
        if arg(argv, '--base'):
            pr['base'] = arg(argv, '--base')
        save_pr(state, pr)
        print(f'https://github.com/owner/repo/pull/{pr["number"]}')
    else:
        sys.stderr.write(f'fake gh: unsupported command {argv}\n')
        sys.exit(2)


if __name__ == '__main__':
    main()
