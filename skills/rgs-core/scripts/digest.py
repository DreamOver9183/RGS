"""Hand long documents or noisy logs to Gemini in chunks; every claim comes back with a checked citation.

Usage:
    python -I digest.py --question "Which errors happen before the crash?" FILE [FILE ...]
                        [--grep REGEX ...] [--context 3] [--chunk-lines 800] [--workers 4]
                        [--model M] [--timeout S] [--out DIR]

--grep keeps only matching lines (plus --context lines around them) before chunking, which is
both cheaper and more reliable: a single agy call over ~110K tokens has missed planted lines
while claiming it found everything. Each chunk goes to its own agy call in an empty guarded folder.
Each finding's quote is checked against the cited lines of the original file ("verified").
Protected files (profile secrets.deny_read) are refused.
Exit code 0 = all chunks answered, 3 = quota, 5 = some chunks failed (see report).
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rgs_common as rc  # noqa: E402

SCHEMA = {
    'type': 'object',
    'properties': {
        'findings': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {
                'claim': {'type': 'string'},
                'file': {'type': 'string'},
                'line_start': {'type': 'integer'},
                'line_end': {'type': 'integer'},
                'quote': {'type': 'string'},
            },
            'required': ['claim', 'file', 'line_start', 'quote'],
        }},
        'notes': {'type': 'string'},
    },
    'required': ['findings'],
}


def select_ranges(lines, patterns, context):
    """1-based inclusive line ranges to keep."""
    if not patterns:
        return [(1, len(lines))] if lines else []
    rx = [re.compile(p, re.I) for p in patterns]
    keep = []
    for i, text in enumerate(lines, 1):
        if any(r.search(text) for r in rx):
            start, end = max(1, i - context), min(len(lines), i + context)
            if keep and start <= keep[-1][1] + 1:
                keep[-1] = (keep[-1][0], max(keep[-1][1], end))
            else:
                keep.append((start, end))
    return keep


def build_chunks(files, patterns, context, chunk_lines):
    chunks, current, count = [], [], 0
    for path in files:
        with open(path, encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()
        for start, end in select_ranges(lines, patterns, context):
            n = start
            while n <= end:
                if count >= chunk_lines:
                    chunks.append('\n'.join(current) + '\n')
                    current, count = [], 0
                take = min(end, n + (chunk_lines - count) - 1)
                current.append(f'# 檔案：{path}（第 {n}–{take} 行）')
                current += [f'L{k}: {lines[k - 1]}' for k in range(n, take + 1)]
                count += take - n + 1
                n = take + 1
    if current:
        chunks.append('\n'.join(current) + '\n')
    return chunks


def squash(text):
    return re.sub(r'\s+', ' ', re.sub(r'^\s*L\d+:\s?', '', text, flags=re.M)).strip()


def verify(finding, files):
    """True when the quote appears in the cited lines (±2) of a file that was sent."""
    target = None
    name = str(finding.get('file', '')).replace('\\', '/')
    for path in files:
        p = path.replace('\\', '/')
        if p == name or p.endswith('/' + name) or name.endswith('/' + p.rsplit('/', 1)[-1]) or os.path.basename(p) == name:
            target = path
            break
    quote = squash(str(finding.get('quote', '')))
    if not target or not quote:
        return False
    with open(target, encoding='utf-8', errors='replace') as f:
        lines = f.read().splitlines()
    start = max(1, int(finding.get('line_start') or 1) - 2)
    end = min(len(lines), int(finding.get('line_end') or finding.get('line_start') or 1) + 2)
    return quote in squash('\n'.join(lines[start - 1:end]))


def main():
    rc.setup_stdio()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('files', nargs='+')
    ap.add_argument('--question', required=True)
    ap.add_argument('--grep', action='append', default=[])
    ap.add_argument('--context', type=int, default=3)
    ap.add_argument('--chunk-lines', type=int)
    ap.add_argument('--workers', type=int)
    ap.add_argument('--model')
    ap.add_argument('--timeout', type=int)
    ap.add_argument('--out')
    args = ap.parse_args()
    try:
        return run(args)
    except rc.RgsError as e:
        print(json.dumps({'error': str(e)}, ensure_ascii=False))
        return e.code


def run(args):
    try:
        repo = rc.main_checkout('.')
        profile, _ = rc.load_profile(repo)
    except rc.RgsError:
        repo, profile = None, rc.DEFAULT_PROFILE
    conf = profile['agy']['digest']
    deny = list(profile['secrets'].get('deny_read') or []) + list(profile.get('worktree_copy') or [])
    files = [os.path.abspath(f) for f in args.files]
    def protected(path):
        if rc.match_any(os.path.basename(path), deny):
            return True
        try:
            return bool(repo) and rc.match_any(os.path.relpath(path, repo).replace('\\', '/'), deny)
        except ValueError:  # different drive
            return False

    refused = [f for f in files if protected(f)]
    if refused:
        raise rc.RgsError('refusing to send protected files: ' + ', '.join(refused), code=rc.EXIT_SECRET)
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        raise rc.RgsError('not found: ' + ', '.join(missing))
    chunks = build_chunks(files, args.grep, args.context, args.chunk_lines or conf['chunk_lines'])
    if not chunks:
        raise rc.RgsError('nothing to send (no lines matched --grep)')
    out = os.path.abspath(args.out) if args.out else (
        rc.run_dir(repo, 'digest-' + time.strftime('%Y%m%d-%H%M%S')) if repo else
        os.path.abspath('rgs-digest-' + time.strftime('%Y%m%d-%H%M%S')))
    os.makedirs(out, exist_ok=True)
    schema_path = os.path.join(out, 'schema.json')
    rc.write_text(schema_path, json.dumps(SCHEMA, ensure_ascii=False))
    language = '繁體中文' if profile['language'].get('docs', 'zh-TW').lower().startswith('zh') else 'English'
    models = [args.model] if args.model else conf['models']

    def one(index, text):
        name = f'chunk-{index:03d}.txt'
        rc.write_text(os.path.join(out, name), text)
        work = rc.isolated_workspace('rgs_digest_', {name: text})
        try:
            prompt = rc.render_template('prompts/digest.md', chunk=name, question=args.question, language=language)
            return rc.call_with_fallback(models, prompt=prompt, cwd=work, schema_path=schema_path,
                                         timeout_s=args.timeout or conf['timeout_s'],
                                         save_as=os.path.join(out, f'chunk-{index:03d}'))
        finally:
            shutil.rmtree(work, ignore_errors=True)

    with ThreadPoolExecutor(max_workers=args.workers or conf['workers']) as pool:
        results = list(pool.map(lambda pair: one(*pair), enumerate(chunks, 1)))

    findings, failed = [], []
    for index, result in enumerate(results, 1):
        if not result.ok:
            failed.append({'chunk': index, 'kind': result.kind, 'detail': result.detail[:200]})
            continue
        for f in result.structured.get('findings') or []:
            f['chunk'] = index
            f['verified'] = verify(f, files)
            findings.append(f)
    lines = [f'# 摘要委派結果', '', f'問題：{args.question}', '',
             f'片段 {len(chunks)} 個，失敗 {len(failed)} 個；結論 {len(findings)} 條，'
             f'引用核對通過 {sum(f["verified"] for f in findings)} 條。', '']
    if findings:
        lines += ['| # | 結論 | 位置 | 引用核對 |', '| --: | :-- | :-- | :-: |']
        for i, f in enumerate(findings, 1):
            where = f'{os.path.basename(str(f.get("file")))}:{f.get("line_start")}'
            if f.get('line_end') and f.get('line_end') != f.get('line_start'):
                where += f'-{f["line_end"]}'
            claim = str(f.get('claim', '')).replace('|', '\\|').replace('\n', ' ')
            lines.append(f'| {i} | {claim} | `{where}` | {"✓" if f["verified"] else "✗ 需人工確認"} |')
    if failed:
        lines += ['', '## 失敗的片段', ''] + [f'- chunk {x["chunk"]}：{x["kind"]} {x["detail"]}' for x in failed]
    report_path = os.path.join(out, 'digest.md')
    rc.write_text(report_path, '\n'.join(lines) + '\n')
    rc.write_text(os.path.join(out, 'digest.json'), json.dumps({'question': args.question, 'findings': findings,
                                                                 'failed_chunks': failed}, ensure_ascii=False, indent=2))
    rc.emit({'chunks': len(chunks), 'failed_chunks': failed, 'findings': len(findings),
             'verified': sum(f['verified'] for f in findings), 'report': report_path,
             'note': 'act only on verified findings; open the cited lines for anything marked ✗'})
    if any(x['kind'] == 'quota' for x in failed):
        return rc.EXIT_QUOTA
    return rc.EXIT_NO_RESULT if failed else rc.EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
