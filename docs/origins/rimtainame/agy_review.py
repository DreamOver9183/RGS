"""Automated pull request review through the Antigravity CLI (agy).

Used when GitHub Copilot review is unavailable (see CLAUDE.md, SOP step 3).

Usage:
    python -I Tools/agy_review.py <PR number> [--model gemini-3.8-flash-high] [--timeout 900] [--post]

The PR head is checked out in a temporary git worktree and the diff is written to
.agy_review/pr.diff inside it, so agy reads the code from files instead of a long command line.
agy is asked to review with three parallel subagents (security, boundary conditions,
architecture compliance with CLAUDE.md). A Markdown report is printed; --post also adds it to the
PR as a comment. Exit code 0 = review done, 2 = agy returned no usable result.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGY = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'agy', 'bin', 'agy.exe')

SCHEMA = {
    'type': 'object',
    'properties': {
        'summary': {'type': 'string'},
        'findings': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'severity': {'type': 'string', 'enum': ['high', 'medium', 'low']},
                    'category': {'type': 'string', 'enum': ['security', 'boundary', 'architecture', 'other']},
                    'file': {'type': 'string'},
                    'line': {'type': 'integer'},
                    'title': {'type': 'string'},
                    'detail': {'type': 'string'},
                    'suggestion': {'type': 'string'},
                },
                'required': ['severity', 'category', 'file', 'title', 'detail'],
            },
        },
    },
    'required': ['summary', 'findings'],
}

PROMPT = """你是資深 C#／RimWorld Mod 程式審查者。請審查目前工作目錄中的 Pull Request #{number}「{title}」。

- 變更的 diff 在 .agy_review/pr.diff；目前目錄是 PR 分支的完整專案；專案規範在 CLAUDE.md（尤其是「架構規範」與「API Key 規則」）。
- 只審查 diff 中新增或修改的部分；需要上下文時可以讀其他檔案。不要修改任何檔案，不要執行建置、測試或網路請求。
- 請用 invoke_subagent 平行建立三個子代理，每個只負責一個面向。把 diff 與 CLAUDE.md 的路徑告訴它們，不要把 diff 內容抄進任務：
  1. security：API Key 外洩（記錄、例外訊息、網址、檔案、PR 內容）、HTTP 安全（端點、轉址、TLS）、輸入驗證、不安全的路徑或反序列化。
  2. boundary：null、空字串、超長字串、Unicode（NFC／NFKC、代理對）、執行緒與競態、逾時、錯誤分支、資源釋放、檔案損壞。
  3. architecture：是否違反 CLAUDE.md 的規範（純 C# 層不得引用遊戲型別或寫記錄、net472 相容 API、主執行緒規則、零存檔污染、語言檔雙語、Harmony 2.4.2 相容）。
- 彙整子代理的結果：刪除重複與沒有根據的推測，每個問題標明檔案與行號（diff 中新檔案的行號），並給具體的修正建議。沒有問題就回傳空的 findings。
- summary 與各欄位一律用繁體中文。
"""

SEVERITY = {'high': '高', 'medium': '中', 'low': '低'}


def run(cmd, cwd=ROOT, check=True):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, encoding='utf-8', errors='replace')
    if check and proc.returncode != 0:
        raise RuntimeError(f'{" ".join(cmd[:3])} failed ({proc.returncode}): {proc.stderr.strip()[:500]}')
    return proc.stdout


def cell(text):
    return (text or '').replace('|', '\\|').replace('\r', ' ').replace('\n', ' ').strip()


def report(number, model, data):
    findings = data.get('findings') or []
    lines = [f'## Antigravity CLI Code Review（`{model}`）', '', cell(data.get('summary')), '']
    if not findings:
        lines.append('沒有發現需要修正的問題。')
    else:
        lines += ['| 嚴重度 | 類別 | 位置 | 問題 | 說明 | 建議 |', '| :-- | :-- | :-- | :-- | :-- | :-- |']
        order = {'high': 0, 'medium': 1, 'low': 2}
        for f in sorted(findings, key=lambda f: order.get(f.get('severity'), 3)):
            where = f.get('file', '') + (f':{f["line"]}' if f.get('line') else '')
            lines.append(f'| {SEVERITY.get(f.get("severity"), f.get("severity", ""))} | {cell(f.get("category"))} '
                         f'| `{cell(where)}` | {cell(f.get("title"))} | {cell(f.get("detail"))} '
                         f'| {cell(f.get("suggestion"))} |')
    lines += ['', f'_PR #{number}；由 `Tools/agy_review.py` 產生，意見僅供參考。_']
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('number', type=int)
    ap.add_argument('--model', default='gemini-3.8-flash-high')
    ap.add_argument('--timeout', type=int, default=900, help='seconds')
    ap.add_argument('--post', action='store_true', help='add the report to the PR as a comment')
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')

    pr = json.loads(run(['gh', 'pr', 'view', str(args.number), '--json', 'title,headRefOid']))
    diff = run(['gh', 'pr', 'diff', str(args.number)])
    run(['git', 'fetch', '-q', 'origin', f'refs/pull/{args.number}/head'])

    work = tempfile.mkdtemp(prefix='agy_review_')
    tree = os.path.join(work, 'tree')
    run(['git', 'worktree', 'add', '-q', '--detach', tree, pr['headRefOid']])
    try:
        os.makedirs(os.path.join(tree, '.agy_review'))
        with open(os.path.join(tree, '.agy_review', 'pr.diff'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(diff)
        schema_path = os.path.join(work, 'schema.json')
        with open(schema_path, 'w', encoding='utf-8') as f:
            json.dump(SCHEMA, f, ensure_ascii=False)
        prompt = PROMPT.format(number=args.number, title=pr['title'])
        cmd = [AGY, '-p', prompt, '--model', args.model, '--json-schema', schema_path,
               '--output-format', 'json', '--disable-slash-commands', '--print-timeout', f'{args.timeout}s']
        proc = subprocess.run(cmd, cwd=tree, capture_output=True, timeout=args.timeout + 120)
        out = proc.stdout.decode('utf-8', 'replace')
        try:
            data = json.loads(out).get('structured_output')
        except json.JSONDecodeError:
            data = None
        if proc.returncode != 0 or not data:
            # agy reports a timeout as success with an empty response.
            err = proc.stderr.decode('utf-8', 'replace')
            print(f'agy returned no review (exit {proc.returncode}): {err[:500]} {out[:500]}')
            return 2
    finally:
        run(['git', 'worktree', 'remove', '--force', tree], check=False)
        shutil.rmtree(work, ignore_errors=True)

    text = report(args.number, args.model, data)
    print(text)
    if args.post:
        body = os.path.join(tempfile.gettempdir(), f'agy_review_{args.number}.md')
        with open(body, 'w', encoding='utf-8') as f:
            f.write(text)
        run(['gh', 'pr', 'comment', str(args.number), '--body-file', body])
        os.remove(body)
    return 0


if __name__ == '__main__':
    sys.exit(main())
