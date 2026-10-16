"""Translate name tokens with Gemini through the Antigravity CLI (agy) and write a review sheet.

Usage:
    python -I agy_translate.py [input.csv] [output.csv] [--model gemini-3.8-flash-low]
                               [--batch 40] [--workers 8] [--timeout 300]

input.csv needs: id, namespace, text, type, gender, origin, used_by, example (zh_tw_official optional,
never sent to the model). Every CLI response is kept under <output dir>/raw/; rerunning the same
command resumes from those files and only sends ids that have no translation yet.
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from name_rules import OUTPUT_SCHEMA, TRANSLATION_RULES, check  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IN = os.path.join(ROOT, 'NameTable', 'samples', 'sample_input.csv')
DEFAULT_OUT = os.path.join(ROOT, 'NameTable', 'samples', 'sample_results.csv')
AGY = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'agy', 'bin', 'agy.exe')
SENT_FIELDS = ['id', 'text', 'type', 'gender', 'origin', 'used_by', 'example']
QUOTA_MARKERS = ('quota', 'credits', 'resource_exhausted', 'rate limit')


class QuotaExceeded(RuntimeError):
    pass


def run_agy(prompt, model, schema_path, workdir, timeout_s):
    cmd = [AGY, '-p', prompt, '--model', model, '--json-schema', schema_path,
           '--output-format', 'json', '--disable-slash-commands', '--print-timeout', f'{timeout_s}s']
    proc = subprocess.run(cmd, cwd=workdir, capture_output=True, timeout=timeout_s + 60)
    out = proc.stdout.decode('utf-8', 'replace')
    err = proc.stderr.decode('utf-8', 'replace')
    if proc.returncode != 0:
        msg = f'agy exit {proc.returncode}: {err[:300]} {out[:300]}'
        if any(m in (err + out).lower() for m in QUOTA_MARKERS):
            raise QuotaExceeded(msg)
        raise RuntimeError(msg)
    return out, json.loads(out)


def load_done(raw_dir, wanted):
    """Collect translations already saved in raw/*.json for the wanted ids."""
    done = {}
    for fn in sorted(os.listdir(raw_dir)):
        if not fn.endswith('.json'):
            continue
        try:
            data = json.load(open(os.path.join(raw_dir, fn), encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            continue
        for it in (data.get('structured_output') or {}).get('items', []):
            if it.get('id') in wanted and (it.get('zh') or '').strip():
                done[it['id']] = it
    return done


class Runner:
    def __init__(self, model, schema_path, workdir, raw_dir, timeout_s, total):
        self.model, self.schema_path, self.workdir = model, schema_path, workdir
        self.raw_dir, self.timeout_s = raw_dir, timeout_s
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.total, self.finished, self.t0 = total, 0, time.time()

    def batch(self, label, chunk):
        if self.stop.is_set():
            return []
        items = [{k: r[k] for k in SENT_FIELDS if r.get(k)} for r in chunk]
        prompt = TRANSLATION_RULES + '\n【輸入】\n' + '\n'.join(json.dumps(i, ensure_ascii=False) for i in items)
        t0 = time.time()
        try:
            raw, data = run_agy(prompt, self.model, self.schema_path, self.workdir, self.timeout_s)
        except QuotaExceeded as e:
            self.stop.set()
            print(f'QUOTA STOP at {label}: {e}', flush=True)
            return []
        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            print(f'{label}: FAILED {str(e)[:300]}', flush=True)
            return []
        with open(os.path.join(self.raw_dir, f'{label}.json'), 'w', encoding='utf-8') as f:
            f.write(raw)
        wanted = {r['id'] for r in chunk}
        got = [i for i in (data.get('structured_output') or {}).get('items', [])
               if i.get('id') in wanted and (i.get('zh') or '').strip()]
        with self.lock:
            self.finished += len(got)
            rate = self.finished / max(time.time() - self.t0, 1)
            eta = (self.total - self.finished) / rate if rate else 0
            print(f'{label}: {len(got)}/{len(chunk)} ok in {time.time() - t0:.0f}s | '
                  f'progress {self.finished}/{self.total} | ETA {eta / 60:.0f} min', flush=True)
        return got


def translate(rows, model, batch, raw_dir, timeout_s, workers):
    workdir = tempfile.mkdtemp(prefix='agy_rimtainame_')
    schema_path = os.path.join(workdir, 'schema.json')
    with open(schema_path, 'w', encoding='utf-8') as f:
        json.dump(OUTPUT_SCHEMA, f, ensure_ascii=False)
    wanted = {r['id'] for r in rows}
    results = load_done(raw_dir, wanted)
    if results:
        print(f'resume: {len(results)} ids already translated', flush=True)
    pending = [r for r in rows if r['id'] not in results]
    runner = Runner(model, schema_path, workdir, raw_dir, timeout_s, len(pending))
    run_id = time.strftime('%m%d%H%M%S')
    for attempt in range(1, 4):
        if not pending or runner.stop.is_set():
            break
        chunks = [(f'{run_id}_a{attempt}_b{i // batch + 1:04d}', pending[i:i + batch])
                  for i in range(0, len(pending), batch)]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for got in pool.map(lambda c: runner.batch(*c), chunks):
                for it in got:
                    results[it['id']] = it
        pending = [r for r in pending if r['id'] not in results]
    return results, [r['id'] for r in pending], runner.stop.is_set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input', nargs='?', default=DEFAULT_IN)
    ap.add_argument('output', nargs='?', default=DEFAULT_OUT)
    ap.add_argument('--model', default='gemini-3.8-flash-low')
    ap.add_argument('--batch', type=int, default=40)
    ap.add_argument('--timeout', type=int, default=300)
    ap.add_argument('--workers', type=int, default=8, help='agy processes to run in parallel')
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')

    rows = list(csv.DictReader(open(args.input, encoding='utf-8-sig')))
    raw_dir = os.path.join(os.path.dirname(os.path.abspath(args.output)), 'raw')
    os.makedirs(raw_dir, exist_ok=True)
    t0 = time.time()
    results, missing, quota_stop = translate(rows, args.model, args.batch, raw_dir, args.timeout, args.workers)
    print(f'wall time: {time.time() - t0:.1f}s (workers={args.workers}, batch={args.batch}, model={args.model})')

    fields = list(rows[0].keys()) + ['model', 'gemini_zh', 'vs_official', 'auto_warnings',
                                     'review', 'suggested_zh', 'review_notes']
    with open(args.output, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            zh = (results.get(r['id'], {}).get('zh') or '').strip()
            official = r.get('zh_tw_official', '')
            vs = '' if not official or not zh else ('相同' if zh in official.split(' / ') else '不同')
            w.writerow({**r, 'model': args.model, 'gemini_zh': zh, 'vs_official': vs,
                        'auto_warnings': ';'.join(check(r['text'], zh, r['namespace'])) if zh else '未翻譯',
                        'review': '', 'suggested_zh': '', 'review_notes': ''})
    status = 'QUOTA STOP — rerun the same command later to resume' if quota_stop else 'done'
    print(f'{status}: {len(results)}/{len(rows)} translated, missing={len(missing)} -> {args.output}')


if __name__ == '__main__':
    main()
