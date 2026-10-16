"""Independent merge-gate review by agy: a fresh conversation, read-only guard, separate detached worktree.

Usage (from inside the project):
    python -I review.py --pr <N> [--task <id>] [--ledger docs/rgs/reviews/PR-<N>.md] [--post]
    python -I review.py --task <id>                      # uncommitted work in the task worktree (/rgs-main --gate)
    python -I review.py --diff-base <REF> [--head <REF>]  # any local range
  common: [--spec PATH] [--note PATH] [--model M] [--timeout S]

agy reviews with one subagent per lens (profile agy.reviewer.lenses) and must answer with the JSON schema
below. The verdict is recomputed here from the findings: PASS only without blocker/major findings.
Outputs a Markdown report and appends a ledger section where Claude records adopt / reject / defer.
Exit code 0 = review produced (read "verdict"), 3 = quota, 5 = no usable result.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rgs_common as rc  # noqa: E402

LENS_TEXT = {
    'security': 'security：機密外洩（記錄、例外訊息、網址、檔案、測試輸出）、注入、不安全的路徑或反序列化、權限與網路安全。',
    'correctness': 'correctness：邏輯錯誤、邊界條件（null、空字串、超長字串、Unicode）、競態與執行緒、逾時與錯誤分支、資源釋放、回歸、編譯錯誤。',
    'architecture': 'architecture：是否違反知識庫的架構規範與慣例（分層、相依方向、字串與設定放置、既有元件的重用）。',
    'spec-tests-docs': 'spec-tests-docs：規格的每個要求是否完成、是否改了範圍外的東西、測試是否真的測到聲稱的行為、文件與程式是否一致（測試數、路徑、版本、指令）。',
}
SEVERITY = {'blocker': '阻擋', 'major': '重要', 'minor': '次要'}


def schema(lenses):
    return {
        'type': 'object',
        'properties': {
            'verdict': {'type': 'string', 'enum': ['PASS', 'CHANGES_REQUESTED']},
            'summary': {'type': 'string'},
            'findings': {'type': 'array', 'items': {
                'type': 'object',
                'properties': {
                    'severity': {'type': 'string', 'enum': ['blocker', 'major', 'minor']},
                    'category': {'type': 'string', 'enum': list(lenses) + ['other']},
                    'file': {'type': 'string'},
                    'line': {'type': 'integer'},
                    'title': {'type': 'string'},
                    'detail': {'type': 'string'},
                    'suggestion': {'type': 'string'},
                },
                'required': ['severity', 'category', 'file', 'title', 'detail'],
            }},
        },
        'required': ['verdict', 'summary', 'findings'],
    }


def cell(text):
    return str(text or '').replace('|', '\\|').replace('\r', ' ').replace('\n', ' ').strip()


def normalize(findings, worktree):
    root = os.path.normcase(os.path.abspath(worktree)).replace('\\', '/')
    for f in findings:
        path = str(f.get('file') or '').replace('\\', '/')
        if path.lower().startswith('file:///'):
            path = path[8:]
        if os.path.normcase(path).replace('\\', '/').startswith(root + '/'):
            path = path[len(root) + 1:]
        f['file'] = path
    order = {'blocker': 0, 'major': 1, 'minor': 2}
    return sorted(findings, key=lambda f: (order.get(f.get('severity'), 3), f.get('file', ''), f.get('line') or 0))


def report(title, model, data, verdict):
    lines = [f'## Antigravity 合併閘門審查（`{model}`）', '', f'**{title}** — 判定：**{verdict}**', '',
             cell(data.get('summary')), '']
    findings = data['findings']
    if not findings:
        lines.append('沒有發現需要修正的問題。')
    else:
        lines += ['| # | 嚴重度 | 面向 | 位置 | 問題 | 說明 | 建議 |', '| --: | :-- | :-- | :-- | :-- | :-- | :-- |']
        for i, f in enumerate(findings, 1):
            where = f['file'] + (f':{f["line"]}' if f.get('line') else '')
            lines.append(f'| {i} | {SEVERITY.get(f["severity"], f["severity"])} | {cell(f.get("category"))} '
                         f'| `{cell(where)}` | {cell(f.get("title"))} | {cell(f.get("detail"))} '
                         f'| {cell(f.get("suggestion"))} |')
    lines += ['', '_由 rgs `review.py` 產生；意見由 Claude 逐條裁決後才採用。_']
    return '\n'.join(lines) + '\n'


def ledger_section(round_no, model, data, verdict, report_path, comment_url=None):
    lines = [f'## 第 {round_no} 輪審查（{time.strftime("%Y-%m-%d %H:%M")}，`{model}`，判定 {verdict}）', '',
             f'報告：`{report_path}`' + (f'；PR 留言：{comment_url}' if comment_url else ''), '']
    if not data['findings']:
        return '\n'.join(lines + ['沒有意見。']) + '\n'
    lines += ['| # | 嚴重度 | 位置 | 問題 | 裁決 | 理由 |', '| --: | :-- | :-- | :-- | :-- | :-- |']
    for i, f in enumerate(data['findings'], 1):
        where = f['file'] + (f':{f["line"]}' if f.get('line') else '')
        lines.append(f'| {i} | {SEVERITY.get(f["severity"], f["severity"])} | `{cell(where)}` '
                     f'| {cell(f.get("title"))} | 待裁決 |  |')
    lines += ['', '裁決只能填：採納、不採納、延後到 M<n>；不採納與延後都要寫理由。']
    return '\n'.join(lines) + '\n'


def main():
    rc.setup_stdio()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--pr', type=int)
    ap.add_argument('--task')
    ap.add_argument('--diff-base')
    ap.add_argument('--head', default='HEAD')
    ap.add_argument('--spec')
    ap.add_argument('--note')
    ap.add_argument('--ledger')
    ap.add_argument('--model')
    ap.add_argument('--timeout', type=int)
    ap.add_argument('--post', action='store_true')
    args = ap.parse_args()
    if not (args.pr or args.task or args.diff_base):
        ap.error('give --pr, --task or --diff-base')
    try:
        return review(args)
    except rc.RgsError as e:
        print(json.dumps({'error': str(e)}, ensure_ascii=False))
        return e.code


def review(args):
    repo = rc.main_checkout('.')
    profile, _ = rc.load_profile(repo)
    conf = profile['agy']['reviewer']
    remote = profile['remote']
    task = rc.get_task(repo, args.task)[1] if args.task else None
    apply_diff = None

    if args.pr:
        info = json.loads(rc.gh(['pr', 'view', str(args.pr), '--json', 'title,headRefOid'], cwd=repo).stdout)
        diff = rc.gh(['pr', 'diff', str(args.pr)], cwd=repo).stdout
        rc.git(['fetch', '-q', remote, f'refs/pull/{args.pr}/head'], cwd=repo)
        head, title, label = info['headRefOid'], f'PR #{args.pr}「{info["title"]}」', f'pr-{args.pr}'
    elif task and not args.diff_base:
        import rgs  # the task's uncommitted work, including new files
        diff = rgs.worktree_diff(task)
        head = rc.git(['rev-parse', 'HEAD'], cwd=task['worktree'])
        title, label, apply_diff = f'任務 {args.task}（尚未 commit 的變更）', f'task-{args.task}', diff
    else:
        head = rc.git(['rev-parse', args.head], cwd=repo)
        diff = rc.run(['git', '-c', 'core.quotepath=off', 'diff', '--no-color', f'{args.diff_base}...{head}'],
                      cwd=repo).stdout
        title, label = f'{args.diff_base}...{args.head}', f'range-{head[:8]}'
    if not diff.strip():
        raise rc.RgsError('the diff is empty; nothing to review')

    base_dir = rc.run_dir(repo, args.task or label)
    round_no = 1 + sum(1 for n in os.listdir(base_dir) if n.startswith('review-') and os.path.isdir(os.path.join(base_dir, n)))
    rd = os.path.join(base_dir, f'review-{round_no}')
    os.makedirs(rd, exist_ok=True)
    diff_path = os.path.join(rd, 'pr.diff')
    rc.write_text(diff_path, diff)
    spec = args.spec or (task or {}).get('spec')
    spec_ref = '（沒有規格檔，依 diff 與知識庫判斷）'
    if spec and os.path.exists(spec):
        spec_ref = f'`{os.path.join(rd, "spec.md")}`'
        rc.write_text(os.path.join(rd, 'spec.md'), rc.read_text(spec))
    note_ref = '（無）'
    if args.note:
        note_ref = f'`{os.path.join(rd, "note.md")}`'
        rc.write_text(os.path.join(rd, 'note.md'), rc.read_text(args.note))
    lenses = [l for l in conf['lenses'] if l in LENS_TEXT] or list(LENS_TEXT)
    deny = list(profile['secrets'].get('deny_read') or []) + list(profile.get('worktree_copy') or [])
    kb_files = list(profile.get('knowledge_base') or [])
    kb = '、'.join(f'`{p}`' for p in kb_files) or '（無）'
    # Absolute paths in the review worktree: the run-dir paths in the prompt point at the main checkout,
    # and a reviewer that guesses the project root from them is denied by the guard.
    wt = os.path.join(rc.worktree_root(repo, profile), f'review-{label}')
    kb_in_wt = '、'.join(f'`{os.path.join(wt, p)}`' for p in kb_files) or '（無）'
    rules = os.path.join(rd, 'reviewer-rules.md')
    rc.write_text(rules, rc.render_template('reviewer-rules.md', repo, secrets='、'.join(f'`{p}`' for p in deny),
                                            knowledge_base=kb))
    schema_path = os.path.join(rd, 'schema.json')
    rc.write_text(schema_path, json.dumps(schema(lenses), ensure_ascii=False))
    language = '繁體中文' if profile['language'].get('docs', 'zh-TW').lower().startswith('zh') else 'English'
    prompt = rc.render_template('prompts/review.md', repo, title=title, rules=rules, diff=diff_path, spec=spec_ref,
                                note=note_ref, knowledge_base=kb_in_wt, worktree=wt, lens_count=len(lenses),
                                language=language,
                                lenses='\n'.join(f'   {i}. {LENS_TEXT[l]}' for i, l in enumerate(lenses, 1)))

    if os.path.isdir(wt):
        rc.git(['worktree', 'remove', '--force', wt], cwd=repo, check=False)
    os.makedirs(os.path.dirname(wt), exist_ok=True)
    rc.git(['worktree', 'add', '-q', '--detach', wt, head], cwd=repo)
    denials = []
    try:
        if apply_diff:
            # From the file: text-mode stdin on Windows would turn LF into CRLF and break the patch.
            rc.run(['git', 'apply', '--whitespace=nowarn', diff_path], cwd=wt)
        rc.install_guard(wt, {'role': 'reviewer', 'roots': [wt, rd], 'write_allow': [], 'deny_read': deny,
                              'read_commands': True, 'allow_commands': []})
        result = rc.call_with_fallback([args.model] if args.model else conf['models'], prompt=prompt, cwd=wt,
                                       schema_path=schema_path, add_dirs=[rd],
                                       timeout_s=args.timeout or conf['timeout_s'],
                                       save_as=os.path.join(rd, 'agy'))
        entries, _ = rc.guard_log_since(wt, 0)
        denials = [e for e in entries if e.get('decision') == 'deny']
    finally:
        rc.git(['worktree', 'remove', '--force', wt], cwd=repo, check=False)

    if not result.ok:
        rc.emit({'review': label, 'round': round_no, 'agy': result.summary(),
                 'models_tried': getattr(result, 'tried', None), 'guard_denials': denials,
                 'note': 'no usable review; do not treat this as PASS'})
        return rc.exit_code_for(result)

    data = dict(result.structured)
    data['findings'] = normalize(list(data.get('findings') or []), wt)
    blocking = [f for f in data['findings'] if f.get('severity') in ('blocker', 'major')]
    verdict = 'CHANGES_REQUESTED' if blocking else 'PASS'
    data['model_verdict'] = data.get('verdict')
    data['verdict'] = verdict
    rc.write_text(os.path.join(rd, 'review.json'), json.dumps(data, ensure_ascii=False, indent=2))
    report_path = os.path.join(rd, 'review.md')
    rc.write_text(report_path, report(title, result.model, data, verdict))
    counts = {s: sum(1 for f in data['findings'] if f.get('severity') == s) for s in ('blocker', 'major', 'minor')}
    out = {'review': label, 'round': round_no, 'verdict': verdict, 'model_verdict': data['model_verdict'],
           'counts': counts, 'summary': data.get('summary'), 'report': report_path, 'posted': False}
    comment_url = None
    if args.post and args.pr:
        # A failed post must not hide the verdict: report the error next to the result instead of raising.
        proc = rc.gh(['pr', 'comment', str(args.pr), '--body-file', report_path], cwd=repo, check=False)
        if proc.returncode == 0:
            out['posted'] = True
            comment_url = (proc.stdout.strip().splitlines() or [None])[-1]
            out['comment_url'] = comment_url
        else:
            out['post_error'] = (proc.stderr or proc.stdout).strip()[-800:]
    ledger = os.path.abspath(args.ledger) if args.ledger else os.path.join(base_dir, 'ledger.md')
    if not os.path.exists(ledger):
        rc.write_text(ledger, f'# 審查裁決紀錄：{title}\n')
    source = os.path.relpath(report_path, repo).replace('\\', '/')
    with open(ledger, 'a', encoding='utf-8', newline='\n') as f:
        f.write('\n' + ledger_section(round_no, result.model, data, verdict, source, comment_url))
    out.update(ledger=ledger, agy=result.summary(), guard_denials=denials)
    rc.emit(out)
    return rc.EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
