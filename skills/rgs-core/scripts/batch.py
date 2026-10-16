"""Bulk data work through parallel agy processes, resumable from saved raw responses.

Usage:
    python -I batch.py --input items.jsonl --prompt instructions.md --out <dir>
                       [--schema schema.json] [--fields id,text,...] [--batch 40] [--workers 8]
                       [--model M] [--timeout 900] [--retries 3] [--validator check.py] [--limit N]

items.jsonl: one JSON object per line, each with a unique "id". Only --fields are sent (default: all).
schema.json: must return {"items": [{"id": ..., ...}]}; default asks for {"id", "output"}.
validator: optional Python file with validate(item: dict, result: dict) -> list[str] (warnings).

Every agy reply is kept in <out>/raw/; rerunning the same command sends only ids without a result.
Each round re-sends missing or empty ids (up to --retries rounds). Quota errors stop the whole run.
Outputs <out>/results.jsonl (input + result + warnings) and <out>/summary.json.
Exit code 0 = every id has a result, 3 = stopped on quota, 5 = some ids still missing.
"""
import argparse
import glob
import importlib.util
import json
import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rgs_common as rc  # noqa: E402

DEFAULT_SCHEMA = {
    'type': 'object',
    'properties': {'items': {'type': 'array', 'items': {
        'type': 'object',
        'properties': {'id': {'type': 'string'}, 'output': {'type': 'string'}},
        'required': ['id', 'output'],
    }}},
    'required': ['items'],
}
MAX_PROMPT = 30000  # Windows limits a command line to about 32K characters


def load_items(path, limit=None):
    items, seen = [], set()
    with open(path, encoding='utf-8') as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            item = json.loads(line)
            if 'id' not in item:
                raise rc.RgsError(f'{path}:{n} has no "id"')
            item['id'] = str(item['id'])
            if item['id'] in seen:
                raise rc.RgsError(f'{path}:{n} repeats id {item["id"]}')
            seen.add(item['id'])
            items.append(item)
            if limit and len(items) >= limit:
                break
    return items


def required_fields(schema):
    try:
        item_schema = schema['properties']['items']['items']
    except (KeyError, TypeError):
        raise rc.RgsError('the schema must describe {"items": [{"id": ...}]}')
    return [f for f in item_schema.get('required', []) if f != 'id']


def usable(entry, fields):
    return all(str(entry.get(f, '')).strip() for f in fields)


def load_done(raw_dir, fields):
    done = {}
    for path in sorted(glob.glob(os.path.join(raw_dir, '*.json'))):
        try:
            with open(path, encoding='utf-8') as f:
                saved = json.load(f)
        except ValueError:
            continue
        sent = set(saved.get('ids') or [])
        for entry in (saved.get('structured_output') or {}).get('items') or []:
            eid = str(entry.get('id'))
            if eid in sent and usable(entry, fields):
                done[eid] = entry
    return done


def load_validator(path):
    if not path:
        return None
    spec = importlib.util.spec_from_file_location('rgs_batch_validator', os.path.abspath(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate


def main():
    rc.setup_stdio()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--input', required=True)
    ap.add_argument('--prompt', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--schema')
    ap.add_argument('--fields')
    ap.add_argument('--batch', type=int)
    ap.add_argument('--workers', type=int)
    ap.add_argument('--model')
    ap.add_argument('--timeout', type=int)
    ap.add_argument('--retries', type=int, default=3)
    ap.add_argument('--validator')
    ap.add_argument('--limit', type=int)
    args = ap.parse_args()
    try:
        return run(args)
    except rc.RgsError as e:
        print(json.dumps({'error': str(e)}, ensure_ascii=False))
        return e.code


def run(args):
    try:
        profile, _ = rc.load_profile(rc.main_checkout('.'))
    except rc.RgsError:
        profile = rc.DEFAULT_PROFILE
    conf = profile['agy']['batch']
    models = [args.model] if args.model else conf['models']
    batch_size = args.batch or conf['batch_size']
    workers = args.workers or conf['workers']
    timeout = args.timeout or conf['timeout_s']
    schema = json.loads(rc.read_text(args.schema)) if args.schema else DEFAULT_SCHEMA
    fields = required_fields(schema)
    items = load_items(args.input, args.limit)
    by_id = {i['id']: i for i in items}
    send_fields = [f.strip() for f in args.fields.split(',')] if args.fields else None
    instructions = rc.read_text(args.prompt).strip()
    validate = load_validator(args.validator)

    out = os.path.abspath(args.out)
    raw_dir = os.path.join(out, 'raw')
    os.makedirs(raw_dir, exist_ok=True)
    schema_path = os.path.join(out, 'schema.json')
    rc.write_text(schema_path, json.dumps(schema, ensure_ascii=False))
    log_path = os.path.join(out, 'run.log')
    log_lock = threading.Lock()
    run_id = time.strftime('%Y%m%d-%H%M%S')
    stop = threading.Event()
    quota_hit = []

    def log(msg):
        with log_lock, open(log_path, 'a', encoding='utf-8') as f:
            f.write(f'{time.strftime("%H:%M:%S")} {msg}\n')

    def payload(item):
        sent = {k: v for k, v in item.items() if send_fields is None or k in send_fields or k == 'id'}
        return json.dumps(sent, ensure_ascii=False)

    def call(batch_no, attempt, ids):
        if stop.is_set():
            return
        prompt = rc.render_template('prompts/batch.md', instructions=instructions,
                                    items='\n'.join(payload(by_id[i]) for i in ids))
        if len(prompt) > MAX_PROMPT:
            log(f'b{batch_no} skipped: prompt is {len(prompt)} chars; use a smaller --batch')
            return
        work = rc.isolated_workspace('rgs_batch_')
        try:
            result = rc.call_with_fallback(models, prompt=prompt, cwd=work, schema_path=schema_path, timeout_s=timeout)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        saved = {'ids': ids, 'model': result.model, 'kind': result.kind, 'detail': result.detail,
                 'structured_output': result.structured, 'usage': result.usage}
        rc.write_text(os.path.join(raw_dir, f'{run_id}_a{attempt}_b{batch_no:04d}.json'),
                      json.dumps(saved, ensure_ascii=False))
        if result.kind == 'quota':
            stop.set()
            quota_hit.append(result.detail)
        log(f'a{attempt} b{batch_no} {len(ids)} ids -> {result.kind} ({result.model}) {result.detail[:120]}')

    for attempt in range(1, args.retries + 1):
        done = load_done(raw_dir, fields)
        pending = [i['id'] for i in items if i['id'] not in done]
        if not pending or stop.is_set():
            break
        batches = [pending[k:k + batch_size] for k in range(0, len(pending), batch_size)]
        log(f'attempt {attempt}: {len(pending)} ids in {len(batches)} batches, {workers} workers')
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(call, n, attempt, ids) for n, ids in enumerate(batches, 1)]
        for n, fut in enumerate(futures, 1):
            if fut.exception():
                log(f'a{attempt} b{n} crashed: {type(fut.exception()).__name__}: {fut.exception()}')

    done = load_done(raw_dir, fields)
    results_path = os.path.join(out, 'results.jsonl')
    missing, warned = [], 0
    with open(results_path, 'w', encoding='utf-8', newline='\n') as f:
        for item in items:
            entry = done.get(item['id'])
            if entry is None:
                missing.append(item['id'])
                continue
            warnings = list(validate(item, entry)) if validate else []
            warned += bool(warnings)
            f.write(json.dumps({'input': item, 'result': entry, 'warnings': warnings}, ensure_ascii=False) + '\n')
    summary = {'total': len(items), 'done': len(items) - len(missing), 'missing': len(missing),
               'missing_ids': missing[:50], 'with_warnings': warned, 'quota_stop': bool(quota_hit),
               'results': results_path, 'log': log_path,
               'next': 'rerun the same command to resume' if missing else 'spot-check results before using them'}
    rc.write_text(os.path.join(out, 'summary.json'), json.dumps(summary, ensure_ascii=False, indent=2))
    rc.emit(summary)
    if quota_hit:
        return rc.EXIT_QUOTA
    return rc.EXIT_NO_RESULT if missing else rc.EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
