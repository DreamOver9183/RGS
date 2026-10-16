"""rgs task runner: an isolated worktree per task, Gemini (agy) implements, Claude reviews and lands.

Run from anywhere inside the project (the main checkout or a task worktree):

    python -I rgs.py prepare   --task <id> --spec <spec.md> [--flow main|pr] [--branch B] [--base REF] [--stack-on TASK]
    python -I rgs.py implement --task <id> [--model M] [--timeout S]
    python -I rgs.py diff      --task <id>
    python -I rgs.py fix       --task <id> --notes <fix.md> [--allow PATH ...] [--fresh] [--force]
    python -I rgs.py check     --task <id> [--level quick|verify|all]
    python -I rgs.py land      --task <id> --message-file <msg.txt> [--skip-tests]          # /rgs-main: push to main
    python -I rgs.py ship      --task <id> --message-file <msg.txt> [--title T --body-file B]   # /rgs-pr: open a PR
    python -I rgs.py retarget  --task <id> [--force]   # /rgs-pr: the parent PR was merged; move onto the base branch
    python -I rgs.py cleanup   --task <id> [--delete-branch]
    python -I rgs.py status    [--task <id>]

Every command prints a JSON summary. Exit codes: see rgs_common (0 ok, 3 quota, 4 scope,
5 no usable agy result, 6 escalate, 7 secret, 8 conflict, 9 tests failed, 10 push failed).
"""
import argparse
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rgs_common as rc  # noqa: E402
import scope_check  # noqa: E402
import secret_scan  # noqa: E402

EXIT_PUSH = 10
SLUG = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,60}$')


def context(task_id=None):
    repo = rc.main_checkout('.')
    profile, has_profile = rc.load_profile(repo)
    task = None
    if task_id:
        _, task = rc.get_task(repo, task_id)
    return repo, profile, has_profile, task


def kb_list(profile):
    return '、'.join(f'`{p}`' for p in profile.get('knowledge_base') or []) or '（無）'


def secrets_list(profile):
    items = list(profile['secrets'].get('deny_read') or []) + list(profile.get('worktree_copy') or [])
    return '、'.join(f'`{p}`' for p in items) or '（無）'


def policy_for(task, profile):
    return {
        'role': 'implementer',
        'roots': [task['worktree'], task['run_dir']],
        'write_allow': task['allowed'],
        'deny_read': list(profile['secrets'].get('deny_read') or []) + list(profile.get('worktree_copy') or []),
        'read_commands': True,
        'allow_commands': list(profile['agy']['implementer'].get('allow_commands') or []),
    }


def write_policy(task, profile):
    path = os.path.join(task['worktree'], '.agents', 'rgs-guard.json')
    rc.write_text(path, json.dumps(policy_for(task, profile), ensure_ascii=False, indent=2))


def main_status(repo):
    return rc.run(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=repo).stdout


def worktree_diff(task):
    """Diff of everything the task changed (including new files) against its base."""
    wt = task['worktree']
    rc.git(['add', '-A', '--intent-to-add'], cwd=wt, check=False)
    base = rc.git(['merge-base', task['base'], 'HEAD'], cwd=wt, check=False) or task['base']
    return rc.run(['git', '-c', 'core.quotepath=off', 'diff', '--no-color', base], cwd=wt).stdout


# ---------------------------------------------------------------- commands

def cmd_prepare(args):
    if not SLUG.match(args.task):
        raise rc.RgsError('task id may only use letters, digits, ".", "_" and "-"')
    repo, profile, has_profile, _ = context()
    state = rc.load_state(repo)
    existing = state['tasks'].get(args.task)
    spec_src = os.path.abspath(args.spec)
    spec_text = rc.read_text(spec_src)
    allowed = rc.parse_allowed_files(spec_text)
    if not allowed:
        raise rc.RgsError('the spec lists no files under a "可修改的檔案" / "Files you may change" heading')
    rd = rc.run_dir(repo, args.task)
    spec_copy = os.path.join(rd, 'spec.md')
    if os.path.normcase(spec_src) != os.path.normcase(spec_copy):
        shutil.copyfile(spec_src, spec_copy)

    remote, base_branch = profile['remote'], profile['base_branch']
    remote_ok = rc.has_remote(repo, remote)
    if remote_ok:
        rc.git(['fetch', '-q', remote, base_branch], cwd=repo, check=False)
    if args.stack_on:
        _, parent = rc.get_task(repo, args.stack_on)
        base = parent['branch']
    else:
        base = args.base or (f'{remote}/{base_branch}' if remote_ok else base_branch)
    branch = args.branch or (existing or {}).get('branch') or f'rgs/{args.task}'
    wt = os.path.join(rc.worktree_root(repo, profile), args.task)

    if os.path.isdir(wt):
        resumed = True
    else:
        resumed = False
        os.makedirs(os.path.dirname(wt), exist_ok=True)
        branch_exists = bool(rc.git(['branch', '--list', branch], cwd=repo, check=False))
        if branch_exists:
            rc.git(['worktree', 'add', wt, branch], cwd=repo)
        else:
            rc.git(['worktree', 'add', '-b', branch, wt, base], cwd=repo)
    copied = []
    for rel in profile.get('worktree_copy') or []:
        src, dst = os.path.join(repo, rel), os.path.join(wt, rel)
        if os.path.isfile(src) and not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            copied.append(rel)

    rules = os.path.join(rd, 'implementer-rules.md')
    rc.write_text(rules, rc.render_template('implementer-rules.md', repo, worktree=wt, run_dir=rd,
                                            secrets=secrets_list(profile), knowledge_base=kb_list(profile)))
    task = {
        'flow': args.flow, 'branch': branch, 'base': base, 'worktree': wt, 'run_dir': rd,
        'spec': spec_copy, 'spec_source': spec_src, 'allowed': allowed, 'rules': rules,
        'round': (existing or {}).get('round', 0), 'conversation_id': (existing or {}).get('conversation_id'),
        'stack_on': args.stack_on, 'step': 'prepared',
    }
    task.update(rc.install_guard(wt, policy_for(task, profile)))
    rc.update_task(repo, args.task, **task)
    rc.emit({'task': args.task, 'resumed': resumed, 'worktree': wt, 'branch': branch, 'base': base,
             'allowed': allowed, 'copied_into_worktree': copied, 'run_dir': rd,
             'profile': 'found' if has_profile else 'missing (defaults used; run doctor.py --init)'})
    return rc.EXIT_OK


def after_agy_run(repo, task_id, task, profile, result, label, offset, status_before, extra=None):
    entries, _ = rc.guard_log_since(task['worktree'], offset)
    denials = [e for e in entries if e.get('decision') == 'deny']
    response_file = os.path.join(task['run_dir'], f'{label}.response.md')
    rc.write_text(response_file, result.response)
    scope = scope_check.check(task['worktree'], task['allowed'])
    main_changed = main_status(repo) != status_before
    fields = {'step': label, 'last_result': result.summary()}
    if result.conversation_id:
        fields['conversation_id'] = result.conversation_id
    rc.update_task(repo, task_id, **fields)
    out = {
        'task': task_id, 'agy': result.summary(), 'models_tried': getattr(result, 'tried', None),
        'response_file': response_file, 'guard_denials': denials, 'scope': scope,
        'main_checkout_changed_during_run': main_changed,
        **(extra or {}),
    }
    if not result.ok:
        out['note'] = 'agy did not return a usable result; files may still have been changed, check the scope above'
        code = rc.exit_code_for(result)
    elif not scope['changed']:
        out['note'] = 'agy reported success but no file changed'
        code = rc.EXIT_NO_RESULT
    elif not scope['ok']:
        code = rc.EXIT_SCOPE
    else:
        code = rc.EXIT_OK
    if main_changed:
        out['warning'] = 'the main checkout changed while agy ran; inspect it before continuing'
    rc.emit(out)
    return code


def cmd_implement(args):
    repo, profile, _, task = context(args.task)
    conf = profile['agy']['implementer']
    prompt = rc.render_template('prompts/implement.md', repo, worktree=task['worktree'], branch=task['branch'],
                                rules=task['rules'], spec=task['spec'], knowledge_base=kb_list(profile))
    offset = rc.guard_log_size(task['worktree'])
    before = main_status(repo)
    result = rc.call_with_fallback([args.model] if args.model else conf['models'], prompt=prompt,
                                   cwd=task['worktree'], mode='accept-edits', add_dirs=[task['run_dir']],
                                   timeout_s=args.timeout or conf['timeout_s'],
                                   save_as=os.path.join(task['run_dir'], 'implement'))
    return after_agy_run(repo, args.task, task, profile, result, 'implement', offset, before)


def cmd_fix(args):
    repo, profile, _, task = context(args.task)
    conf = profile['agy']
    round_no = task.get('round', 0) + 1
    if round_no > conf['max_fix_rounds'] and not args.force:
        rc.emit({'task': args.task, 'round': round_no, 'max_fix_rounds': conf['max_fix_rounds'],
                 'note': 'too many fix rounds: stop and ask the user how to proceed (or pass --force)'})
        return rc.EXIT_ESCALATE
    fix_path = os.path.join(task['run_dir'], f'fix-{round_no}.md')
    shutil.copyfile(os.path.abspath(args.notes), fix_path)
    extra = ''
    if args.allow:
        task['allowed'] = sorted(set(task['allowed']) | {a.replace('\\', '/') for a in args.allow})
        rc.update_task(repo, args.task, allowed=task['allowed'])
        write_policy(task, profile)
        extra = ' 這一輪另外允許修改：' + '、'.join(f'`{a}`' for a in args.allow) + '。'
    used = ((task.get('last_result') or {}).get('usage') or {}).get('input_tokens') or 0
    fresh = args.fresh or not task.get('conversation_id') or used > conf['fresh_after_input_tokens']
    if fresh:
        diff_path = os.path.join(task['run_dir'], f'before-fix-{round_no}.diff')
        rc.write_text(diff_path, worktree_diff(task))
        prompt = rc.render_template('prompts/fix-fresh.md', repo, worktree=task['worktree'], branch=task['branch'],
                                    rules=task['rules'], spec=task['spec'], diff=diff_path, fix=fix_path,
                                    knowledge_base=kb_list(profile), extra_allowed=extra)
        conversation = None
    else:
        prompt = rc.render_template('prompts/fix.md', repo, fix=fix_path, rules=task['rules'], extra_allowed=extra)
        conversation = task['conversation_id']
    rc.update_task(repo, args.task, round=round_no)
    offset = rc.guard_log_size(task['worktree'])
    before = main_status(repo)
    result = rc.call_with_fallback([args.model] if args.model else conf['implementer']['models'], prompt=prompt,
                                   cwd=task['worktree'], mode='accept-edits', add_dirs=[task['run_dir']],
                                   conversation=conversation,
                                   timeout_s=args.timeout or conf['implementer']['timeout_s'],
                                   save_as=os.path.join(task['run_dir'], f'fix-{round_no}'))
    return after_agy_run(repo, args.task, task, profile, result, f'fix-{round_no}', offset, before,
                         extra={'round': round_no, 'fresh_conversation': fresh})


def cmd_diff(args):
    repo, _, _, task = context(args.task)
    path = os.path.join(task['run_dir'], f'review-r{task.get("round", 0)}.diff')
    diff = worktree_diff(task)
    rc.write_text(path, diff)
    stat = rc.run(['git', 'diff', '--stat', rc.git(['merge-base', task['base'], 'HEAD'], cwd=task['worktree'])],
                  cwd=task['worktree']).stdout
    rc.emit({'task': args.task, 'diff_file': path, 'lines': diff.count('\n'), 'stat': stat.strip().splitlines()})
    return rc.EXIT_OK


def cmd_check(args):
    repo, profile, _, task = context(args.task)
    scope = scope_check.check(task['worktree'], task['allowed'], args.ignore)
    levels = ['quick', 'verify'] if args.level == 'all' else [args.level]
    runs = {}
    code = rc.EXIT_OK if scope['ok'] else rc.EXIT_SCOPE
    for level in levels:
        commands = profile['commands'].get(level) or []
        if not commands:
            runs[level] = 'no commands configured in profile'
            continue
        prefix = os.path.join(task['run_dir'], f'check-{level}-r{task.get("round", 0)}')
        results = rc.run_commands(commands, task['worktree'], profile, prefix)
        runs[level] = results
        if any(r['exit'] != 0 for r in results):
            code = rc.EXIT_TESTS
            break
    rc.update_task(repo, args.task, step=f'checked-{args.level}', last_check_ok=code == rc.EXIT_OK)
    rc.emit({'task': args.task, 'scope': scope, 'commands': runs, 'ok': code == rc.EXIT_OK})
    return code


def stage_and_commit(task, profile, message_file, extra_allowed=()):
    wt = task['worktree']
    scope = scope_check.check(wt, task['allowed'] + list(extra_allowed))
    if not scope['ok']:
        return rc.EXIT_SCOPE, {'scope': scope}
    if task.get('hooks_tracked'):
        rc.git(['checkout', '--', '.agents/hooks.json'], cwd=wt, check=False)
    rc.git(['add', '-A'], cwd=wt)
    if rc.run(['git', 'diff', '--cached', '--quiet'], cwd=wt, check=False).returncode == 0:
        return rc.EXIT_NO_RESULT, {'note': 'nothing to commit: the worktree has no changes'}
    scan = secret_scan.scan(cwd=wt, profile=profile)
    if not scan['ok']:
        rc.git(['reset', '-q'], cwd=wt, check=False)
        return rc.EXIT_SECRET, {'secret_scan': scan}
    msg = os.path.join(task['run_dir'], 'commit-message.txt')
    if os.path.normcase(os.path.abspath(message_file)) != os.path.normcase(msg):
        shutil.copyfile(message_file, msg)
    rc.git(['commit', '-q', '-F', msg], cwd=wt)
    return rc.EXIT_OK, {'commit': rc.git(['rev-parse', 'HEAD'], cwd=wt)}


def remove_worktree(repo, task, delete_branch):
    wt = task['worktree']
    if os.path.isdir(wt):
        rc.remove_guard(wt, task.get('hooks_tracked'))
        rc.git(['worktree', 'remove', '--force', wt], cwd=repo, check=False)
    if delete_branch:
        rc.git(['branch', '-D', task['branch']], cwd=repo, check=False)
    return not os.path.isdir(wt)


def cmd_land(args):
    repo, profile, _, task = context(args.task)
    wt, remote, base_branch = task['worktree'], profile['remote'], profile['base_branch']
    code, info = stage_and_commit(task, profile, args.message_file)
    if code:
        rc.emit({'task': args.task, 'landed': False, **info})
        return code
    remote_ok = rc.has_remote(repo, remote)
    rebased = False
    if remote_ok:
        rc.git(['fetch', '-q', remote, base_branch], cwd=wt)
        target = f'{remote}/{base_branch}'
        if rc.run(['git', 'merge-base', '--is-ancestor', target, 'HEAD'], cwd=wt, check=False).returncode != 0:
            proc = rc.run(['git', 'rebase', '-q', target], cwd=wt, check=False)
            if proc.returncode != 0:
                rc.git(['rebase', '--abort'], cwd=wt, check=False)
                rc.emit({'task': args.task, 'landed': False, 'commit': info['commit'],
                         'note': f'rebase onto {target} hit conflicts; the commit is kept on {task["branch"]}',
                         'stderr': (proc.stderr or proc.stdout)[-800:]})
                return rc.EXIT_CONFLICT
            rebased = True
            if not args.skip_tests and profile['commands'].get('quick'):
                results = rc.run_commands(profile['commands']['quick'], wt, profile,
                                          os.path.join(task['run_dir'], 'land-quick'))
                if any(r['exit'] != 0 for r in results):
                    rc.emit({'task': args.task, 'landed': False, 'rebased': True, 'tests': results,
                             'note': 'quick checks failed after rebasing; nothing was pushed'})
                    return rc.EXIT_TESTS
        push = rc.run(['git', 'push', remote, f'HEAD:refs/heads/{base_branch}'], cwd=wt, check=False)
        if push.returncode != 0:
            rc.emit({'task': args.task, 'landed': False, 'rebased': rebased,
                     'note': 'push to the base branch was rejected (moved again, protected, or no permission); '
                             'nothing was forced. Retry land, or switch to the PR flow.',
                     'stderr': (push.stderr or push.stdout)[-800:]})
            return EXIT_PUSH
    head = rc.git(['rev-parse', 'HEAD'], cwd=wt)
    current = rc.git(['rev-parse', '--abbrev-ref', 'HEAD'], cwd=repo, check=False)
    synced = False
    if current == base_branch:
        ref = f'{remote}/{base_branch}' if remote_ok else head
        if remote_ok:
            rc.git(['fetch', '-q', remote, base_branch], cwd=repo, check=False)
        synced = rc.run(['git', 'merge', '--ff-only', '-q', ref], cwd=repo, check=False).returncode == 0
    elif not remote_ok:
        rc.emit({'task': args.task, 'landed': False, 'commit': head,
                 'note': f'no remote and the main checkout is not on {base_branch}; merge {task["branch"]} yourself'})
        return EXIT_PUSH
    removed = remove_worktree(repo, task, delete_branch=True)
    rc.update_task(repo, args.task, step='landed', commit=head)
    rc.emit({'task': args.task, 'landed': True, 'commit': head, 'rebased': rebased,
             'pushed_to': f'{remote}/{base_branch}' if remote_ok else None,
             'main_checkout_synced': synced, 'worktree_removed': removed})
    return rc.EXIT_OK


def cmd_ship(args):
    repo, profile, _, task = context(args.task)
    if not (args.no_pr or task.get('pr') or (args.title and args.body_file)):
        raise rc.RgsError('opening a PR needs --title and --body-file (or pass --no-pr)', code=2)
    wt, remote = task['worktree'], profile['remote']
    docs_globs = list(profile.get('knowledge_base') or []) + ['README*', profile['docs_dir'].rstrip('/') + '/**']
    code, info = stage_and_commit(task, profile, args.message_file, docs_globs + args.allow)
    if code:
        rc.emit({'task': args.task, 'shipped': False, **info})
        return code
    out = {'task': args.task, 'commit': info['commit'], 'branch': task['branch']}
    if not rc.has_remote(repo, remote):
        rc.update_task(repo, args.task, step='committed', commit=info['commit'])
        rc.emit({**out, 'shipped': False, 'note': 'no remote: committed only'})
        return rc.EXIT_OK
    push = rc.run(['git', 'push', '-u', remote, f'HEAD:refs/heads/{task["branch"]}'], cwd=wt, check=False)
    if push.returncode != 0:
        rc.emit({**out, 'shipped': False, 'stderr': (push.stderr or push.stdout)[-800:]})
        return EXIT_PUSH
    if args.no_pr or task.get('pr'):
        rc.update_task(repo, args.task, step='pushed', commit=info['commit'])
        rc.emit({**out, 'shipped': True, 'pr': task.get('pr'), 'note': 'pushed to the existing PR' if task.get('pr') else 'pushed (no PR requested)'})
        return rc.EXIT_OK
    base = profile['base_branch']
    if task.get('stack_on'):
        _, parent = rc.get_task(repo, task['stack_on'])
        base = parent['branch']
    cmd = ['pr', 'create', '--base', base, '--head', task['branch'], '--title', args.title,
           '--body-file', os.path.abspath(args.body_file)]
    if args.draft:
        cmd.append('--draft')
    proc = rc.gh(cmd, cwd=wt, check=False)
    if proc.returncode != 0:
        rc.emit({**out, 'shipped': False, 'note': 'pushed, but gh pr create failed', 'stderr': proc.stderr[-800:]})
        return EXIT_PUSH
    url = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ''
    m = re.search(r'/pull/(\d+)', url)
    pr = int(m.group(1)) if m else None
    rc.update_task(repo, args.task, step='pr-open', commit=info['commit'], pr=pr, pr_url=url)
    rc.emit({**out, 'shipped': True, 'pr': pr, 'url': url, 'base': base})
    return rc.EXIT_OK


def cmd_retarget(args):
    """After the parent PR is merged: move a stacked task, and its PR, onto the base branch."""
    repo, profile, _, task = context(args.task)
    if not task.get('stack_on'):
        raise rc.RgsError(f'task {args.task} is not stacked on another task')
    _, parent = rc.get_task(repo, task['stack_on'])
    wt, remote, base_branch = task['worktree'], profile['remote'], profile['base_branch']
    if not os.path.isdir(wt):
        raise rc.RgsError(f'the worktree of {args.task} is gone; run prepare again first')
    dirty = [p for _, p in rc.changed_files(wt) if p not in rc.GUARD_FILES]
    if dirty:
        raise rc.RgsError('the worktree has uncommitted changes (' + ', '.join(dirty[:5]) + '); ship them first')
    if parent.get('pr') and not args.force:
        state = json.loads(rc.gh(['pr', 'view', str(parent['pr']), '--json', 'state'], cwd=wt).stdout)['state']
        if state != 'MERGED':
            raise rc.RgsError(f'PR #{parent["pr"]} of {task["stack_on"]} is {state}, not merged; '
                              'retarget after the user merges it (or pass --force)')
    target = f'{remote}/{base_branch}'
    out = {'task': args.task, 'from': task['base'], 'base': target, 'rebased': False}
    if task.get('pr'):
        view = json.loads(rc.gh(['pr', 'view', str(task['pr']), '--json', 'state,baseRefName'], cwd=wt).stdout)
        out['pr'] = task['pr']
        if view['state'] != 'OPEN':
            rc.emit({**out, 'pr_state': view['state'],
                     'note': f'PR #{task["pr"]} is {view["state"]}; nothing was changed. Reopen it on GitHub, '
                             'or clear it from the task state and ship again to open a new PR'})
            return EXIT_PUSH
    rc.git(['fetch', '-q', remote, base_branch], cwd=wt)
    old = rc.git(['rev-parse', 'HEAD'], cwd=wt)
    fork = rc.git(['merge-base', 'HEAD', parent.get('commit') or parent['branch']], cwd=wt)
    if rc.run(['git', 'merge-base', '--is-ancestor', fork, target], cwd=wt, check=False).returncode != 0:
        # The parent was squash- or rebase-merged, so its commits are not in the base branch:
        # replay only this task's own commits. --autostash covers a tracked .agents/hooks.json.
        proc = rc.run(['git', 'rebase', '-q', '--autostash', '--onto', target, fork], cwd=wt, check=False)
        if proc.returncode != 0:
            rc.git(['rebase', '--abort'], cwd=wt, check=False)
            rc.emit({**out, 'note': f'rebase onto {target} hit conflicts; nothing was changed',
                     'stderr': (proc.stderr or proc.stdout)[-800:]})
            return rc.EXIT_CONFLICT
        out['rebased'] = True
    if task.get('pr'):
        if view['baseRefName'] != base_branch:
            rc.gh(['pr', 'edit', str(task['pr']), '--base', base_branch], cwd=wt)
        out['pr_base'] = base_branch
    if out['rebased'] and task.get('commit'):
        # The branch was pushed before; only overwrite it if it is still where this worktree left it.
        push = rc.run(['git', 'push', f'--force-with-lease=refs/heads/{task["branch"]}:{old}', remote,
                       f'HEAD:refs/heads/{task["branch"]}'], cwd=wt, check=False)
        if push.returncode != 0:
            rc.emit({**out, 'note': 'the rebased branch was not pushed (the remote branch moved?)',
                     'stderr': (push.stderr or push.stdout)[-800:]})
            return EXIT_PUSH
        out['pushed'] = True
    head = rc.git(['rev-parse', 'HEAD'], cwd=wt)
    rc.update_task(repo, args.task, base=target, stack_on=None, retargeted_from=task['stack_on'], step='retargeted',
                   **({'commit': head} if task.get('commit') else {}))
    rc.emit({**out, 'commit': head})
    return rc.EXIT_OK


def cmd_cleanup(args):
    repo, _, _, task = context(args.task)
    removed = remove_worktree(repo, task, args.delete_branch)
    rc.update_task(repo, args.task, step='cleaned')
    rc.emit({'task': args.task, 'worktree_removed': removed, 'branch_deleted': args.delete_branch})
    return rc.EXIT_OK


def cmd_status(args):
    repo = rc.main_checkout('.')
    state = rc.load_state(repo)
    keys = ('flow', 'step', 'branch', 'base', 'round', 'conversation_id', 'pr', 'commit', 'updated')
    tasks = {}
    for tid, t in state['tasks'].items():
        if args.task and tid != args.task:
            continue
        tasks[tid] = {k: t.get(k) for k in keys if t.get(k) is not None}
        tasks[tid]['worktree_exists'] = os.path.isdir(t.get('worktree', ''))
        tasks[tid]['run_dir'] = t.get('run_dir')
    rc.emit({'repo': repo, 'tasks': tasks})
    return rc.EXIT_OK


def main():
    rc.setup_stdio()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--task', required=True)
    p.add_argument('--spec', required=True)
    p.add_argument('--flow', choices=['main', 'pr'], default='main')
    p.add_argument('--branch')
    p.add_argument('--base')
    p.add_argument('--stack-on')
    p = sub.add_parser('implement')
    p.add_argument('--task', required=True)
    p.add_argument('--model')
    p.add_argument('--timeout', type=int)
    p = sub.add_parser('fix')
    p.add_argument('--task', required=True)
    p.add_argument('--notes', required=True)
    p.add_argument('--allow', action='append', default=[])
    p.add_argument('--fresh', action='store_true')
    p.add_argument('--force', action='store_true')
    p.add_argument('--model')
    p.add_argument('--timeout', type=int)
    p = sub.add_parser('diff')
    p.add_argument('--task', required=True)
    p = sub.add_parser('check')
    p.add_argument('--task', required=True)
    p.add_argument('--level', choices=['quick', 'verify', 'all'], default='quick')
    p.add_argument('--ignore', action='append', default=[])
    p = sub.add_parser('land')
    p.add_argument('--task', required=True)
    p.add_argument('--message-file', required=True)
    p.add_argument('--skip-tests', action='store_true')
    p = sub.add_parser('ship')
    p.add_argument('--task', required=True)
    p.add_argument('--message-file', required=True)
    p.add_argument('--title', default='')
    p.add_argument('--body-file')
    p.add_argument('--allow', action='append', default=[])
    p.add_argument('--draft', action='store_true')
    p.add_argument('--no-pr', action='store_true')
    p = sub.add_parser('retarget')
    p.add_argument('--task', required=True)
    p.add_argument('--force', action='store_true')
    p = sub.add_parser('cleanup')
    p.add_argument('--task', required=True)
    p.add_argument('--delete-branch', action='store_true')
    p = sub.add_parser('status')
    p.add_argument('--task')
    args = ap.parse_args()
    handler = globals()['cmd_' + args.cmd]
    try:
        return handler(args)
    except rc.RgsError as e:
        print(json.dumps({'error': str(e)}, ensure_ascii=False))
        return e.code


if __name__ == '__main__':
    sys.exit(main())
