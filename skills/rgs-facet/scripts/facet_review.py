"""Run one facet review turn: validate inputs, invoke agy in an isolated sealed workspace, and record results.

Usage:
    python -I facet_review.py --plan-file <計畫檔> --lens logic|gaps|verifiability --round <N> --models <M1,M2,...>
                              [--timeout 900] [--session <ID>] [--run-dir <資料夾>] [--repo <專案資料夾>] [--prior-stdin]

--models is the reviewer fallback chain in order of preference (--model is an alias; one model is a chain of one).
A model is tried only after the one before it failed with timeout, agy_error, empty_output, parse_error or
schema_error (design D-22). workspace_modified and the errors found before agy runs stop at once. A model that
ran out of quota, or timed out with a --timeout no larger than this one, is skipped by later calls of the same
session for SKIP_TTL_S (record: <run-dir>/model-skips.json); when that would skip every model, none is skipped.

Status and Exit Codes (of the last model tried):
    | status             | exit | condition                                                              |
    | ok                 |    0 | Valid verdict obtained                                                 |
    | timeout            |    2 | agy execution timed out                                                |
    | agy_error          |    3 | agy returned error/quota, or agy executable not found                  |
    | empty_output       |    4 | agy returned no structured_output                                       |
    | parse_error        |    5 | structured_output is a string and JSON parsing failed                  |
    | schema_error       |    5 | verdict schema validation failed                                       |
    | workspace_modified |    6 | repo or workspace modified during call (preempts all other post-call)   |
    | secret_suspected   |    7 | Secret suspected in plan; agy not invoked                              |
    | forbidden_flag     |    8 | Forbidden agy arguments or a model the reviewer may not use; agy not invoked |
    | plan_too_long      |    9 | Prompt constructed from plan exceeds char limit; agy not invoked       |
    | usage_error        |   10 | Command line/file/prior syntax errors; agy not invoked                  |

一次送審（一個角度、一輪）；換模型在這裡做，多輪迴圈由 SKILL.md 負責。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CORE_SCRIPTS = os.path.normpath(os.path.join(HERE, '..', '..', 'rgs-core', 'scripts'))
for _p in (HERE, CORE_SCRIPTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import prompt
import rgs_common as rc
import verdict


FALLBACK_STATUSES = ('timeout', 'agy_error', 'empty_output', 'parse_error', 'schema_error')
SKIPS_FILE = 'model-skips.json'
SKIP_TTL_S = 2 * 3600


class UsageError(Exception):
    pass


def parse_models(text):
    """The comma-separated fallback chain, blanks and repeats removed, order kept."""
    models = []
    for part in (text or '').split(','):
        model = part.strip()
        if model and model not in models:
            models.append(model)
    return models


def load_skips(run_dir):
    try:
        with open(os.path.join(run_dir, SKIPS_FILE), encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def skip_reason(record, timeout, now):
    """Why a model that failed earlier in this session is skipped now, or None."""
    if not isinstance(record, dict):
        return None
    try:
        if now - float(record.get('at', 0)) > SKIP_TTL_S:
            return None
        if record.get('reason') == 'quota':
            return 'quota'
        if record.get('reason') == 'timeout' and timeout <= int(record.get('timeout_s', 0)):
            return 'timeout'
    except (TypeError, ValueError):
        return None
    return None


def plan_attempts(models, skips, timeout, now):
    """Return (models to try, [{model, reason}] skipped, skips_ignored)."""
    order, skipped = [], []
    for model in models:
        reason = skip_reason(skips.get(model), timeout, now)
        if reason:
            skipped.append({'model': model, 'reason': reason})
        else:
            order.append(model)
    if not order:
        # Every model failed earlier; trying the chain again beats stopping without a single call.
        return list(models), [], True
    return order, skipped, False


def evaluate(result, round_no, plan_text):
    """Map one agy result to (status, exit_code, detail, review fields)."""
    review = {'verdict': None, 'findings': [], 'resolved': [], 'coverage': None, 'limitations': None}
    if result.kind == 'timeout':
        return 'timeout', 2, result.detail, review
    if result.kind in ('error', 'quota'):
        return 'agy_error', 3, result.detail, review
    if result.kind == 'empty':
        return 'empty_output', 4, result.detail, review
    data = result.structured
    try:
        if isinstance(data, str):
            data = verdict.parse_response(data)
        verdict.validate(data, round_no=round_no)
    except verdict.VerdictError as e:
        return e.kind, 5, str(e), review  # 'parse_error' or 'schema_error'
    findings = []
    for f in data.get('findings') or []:
        f_copy = dict(f)
        f_copy['evidence_found'] = verdict.evidence_found(f.get('evidence', ''), plan_text)
        findings.append(f_copy)
    review = {
        'verdict': data.get('verdict'),
        'findings': findings,
        'resolved': (data.get('resolved') or []) if round_no >= 2 else [],
        'coverage': data.get('coverage'),
        'limitations': data.get('limitations'),
    }
    return 'ok', 0, '', review


class FacetArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def get_agy_version():
    try:
        prefix = rc.find_agy()
        proc = subprocess.run(
            [*prefix, '--version'],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=30,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
        return None
    except Exception:
        return None


def finish_and_exit(
    status,
    exit_code,
    detail,
    verdict_val,
    findings,
    resolved,
    coverage,
    limitations,
    lens,
    round_no,
    requested_model,
    reported_model,
    call_dir,
    secret_hits,
    repo_changes,
    workspace_new_files,
    guard_denials,
    repo,
    repo_before,
    plan_file,
    plan_chars,
    prompt_chars,
    agy_exec,
    agy_ver,
    result,
    started_iso,
    start_time,
    chain,
):
    finished_time = time.time()
    finished_iso = time.strftime('%Y-%m-%dT%H:%M:%S')
    duration_s = round(finished_time - start_time, 2)
    test_double = bool(os.environ.get('RGS_AGY'))
    models = chain['models']
    fallback_used = bool(models) and requested_model != models[0]
    cross_model = not (isinstance(requested_model, str) and requested_model.startswith('claude-'))

    if call_dir and os.path.isdir(call_dir):
        meta = {
            'status': status,
            'exit_code': exit_code,
            'lens': lens,
            'round': round_no,
            'plan_file': plan_file,
            'plan_chars': plan_chars,
            'prompt_chars': prompt_chars,
            'requested_model': requested_model,
            'reported_model': reported_model,
            'reported_model_note': 'agy 用戶端解析，伺服器端未確認',
            'models': models,
            'attempts': chain['attempts'],
            'skipped': chain['skipped'],
            'skips_ignored': chain['skips_ignored'],
            'fallback_used': fallback_used,
            'cross_model': cross_model,
            'agy_executable': agy_exec,
            'agy_version': agy_ver,
            'agy': result.summary() if result else None,
            'repo': repo,
            'repo_snapshot_kind': repo_before.get('kind') if repo_before else None,
            'repo_changes': repo_changes,
            'workspace_new_files': workspace_new_files,
            'guard_denials': guard_denials,
            'test_double': test_double,
            'started': started_iso,
            'finished': finished_iso,
            'duration_s': duration_s,
        }
        rc.write_text(os.path.join(call_dir, 'meta.json'), json.dumps(meta, ensure_ascii=False, indent=2))

    res = {
        'status': status,
        'verdict': verdict_val,
        'findings': findings,
        'resolved': resolved,
        'coverage': coverage,
        'limitations': limitations,
        'lens': lens,
        'round': round_no,
        'requested_model': requested_model,
        'reported_model': reported_model,
        'models': models,
        'attempts': chain['attempts'],
        'skipped': chain['skipped'],
        'fallback_used': fallback_used,
        'cross_model': cross_model,
        'raw_dir': os.path.abspath(call_dir) if call_dir else None,
        'test_double': test_double,
        'detail': detail,
    }
    if status == 'secret_suspected':
        res['secret_hits'] = secret_hits
    if status == 'workspace_modified':
        res['repo_changes'] = repo_changes
        res['workspace_new_files'] = workspace_new_files

    print(json.dumps(res, ensure_ascii=False))
    sys.exit(exit_code)


def main():
    rc.setup_stdio()
    start_time = time.time()
    started_iso = time.strftime('%Y-%m-%dT%H:%M:%S')

    status = 'usage_error'
    exit_code = 10
    detail = ''
    verdict_val = None
    findings = []
    resolved = []
    coverage = None
    limitations = None
    lens = None
    round_no = None
    requested_model = None
    reported_model = None
    plan_file = None
    plan_text = None
    plan_chars = None
    prompt_text = None
    prompt_chars = None
    call_dir = None
    repo = None
    repo_before = None
    repo_changes = []
    workspace_new_files = []
    guard_denials = []
    result = None
    secret_hits = []
    ws = None
    agy_exec = None
    agy_ver = None
    chain = {'models': [], 'attempts': [], 'skipped': [], 'skips_ignored': False}

    parser = FacetArgumentParser(description='Run one facet review turn.')
    parser.add_argument('--plan-file', required=True)
    parser.add_argument('--lens', required=True)
    parser.add_argument('--round', required=True, type=int)
    parser.add_argument('--models', '--model', dest='models', required=True)
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--session', default=None)
    parser.add_argument('--run-dir', default=None)
    parser.add_argument('--repo', default=None)
    parser.add_argument('--prior-stdin', action='store_true')

    try:
        args = parser.parse_args()
    except UsageError as e:
        detail = str(e)
        finish_and_exit(
            status, exit_code, detail, verdict_val, findings, resolved,
            coverage, limitations, lens, round_no, requested_model,
            reported_model, call_dir, secret_hits, repo_changes,
            workspace_new_files, guard_denials, repo, repo_before,
            plan_file, plan_chars, prompt_chars, agy_exec, agy_ver,
            result, started_iso, start_time, chain,
        )

    lens = args.lens
    round_no = args.round
    chain['models'] = parse_models(args.models)
    requested_model = chain['models'][0] if chain['models'] else args.models
    timeout = args.timeout

    try:
        if not chain['models']:
            raise UsageError(f'no model given: {args.models!r}')
        if lens not in prompt.LENSES:
            raise UsageError(f'unknown lens {lens!r}, expected one of {prompt.LENSES}')
        if round_no < 1:
            raise UsageError(f'invalid round: {round_no}, must be >= 1')
        if timeout < 1:
            raise UsageError(f'invalid timeout: {timeout}, must be >= 1')

        session = args.session
        if session is None:
            session = os.environ.get('CLAUDE_SESSION_ID') or 'manual'
        if not session or session in ('.', '..') or not re.fullmatch(r'[A-Za-z0-9_.-]+', session):
            raise UsageError(f'invalid session: {session!r}')

        repo = os.path.abspath(args.repo) if args.repo else os.getcwd()
        if not os.path.isdir(repo):
            raise UsageError(f'repo directory not found: {repo}')

        plan_file = os.path.abspath(args.plan_file)
        if not os.path.isfile(plan_file):
            raise UsageError(f'plan file not found: {plan_file}')

        if args.run_dir:
            run_dir = os.path.abspath(args.run_dir)
        else:
            run_dir = os.path.join(tempfile.gettempdir(), 'rgs-facet', session)

        call_dir = os.path.abspath(os.path.join(run_dir, f'r{round_no}-{lens}'))
        os.makedirs(call_dir, exist_ok=True)
    except UsageError as e:
        detail = str(e)
        finish_and_exit(
            status, exit_code, detail, verdict_val, findings, resolved,
            coverage, limitations, lens, round_no, requested_model,
            reported_model, call_dir, secret_hits, repo_changes,
            workspace_new_files, guard_denials, repo, repo_before,
            plan_file, plan_chars, prompt_chars, agy_exec, agy_ver,
            result, started_iso, start_time, chain,
        )

    # 3. Load plan
    try:
        plan_text = prompt.load_plan(plan_file)
        plan_chars = len(plan_text)
    except Exception as e:
        status = 'usage_error'
        exit_code = 10
        detail = f'failed to load plan: {e}'
        finish_and_exit(
            status, exit_code, detail, verdict_val, findings, resolved,
            coverage, limitations, lens, round_no, requested_model,
            reported_model, call_dir, secret_hits, repo_changes,
            workspace_new_files, guard_denials, repo, repo_before,
            plan_file, plan_chars, prompt_chars, agy_exec, agy_ver,
            result, started_iso, start_time, chain,
        )

    # 4. Scan secrets
    hits = prompt.scan_secrets(plan_text)
    if hits:
        status = 'secret_suspected'
        exit_code = 7
        detail = f'found {len(hits)} suspected secret(s) in plan'
        secret_hits = hits
        finish_and_exit(
            status, exit_code, detail, verdict_val, findings, resolved,
            coverage, limitations, lens, round_no, requested_model,
            reported_model, call_dir, secret_hits, repo_changes,
            workspace_new_files, guard_denials, repo, repo_before,
            plan_file, plan_chars, prompt_chars, agy_exec, agy_ver,
            result, started_iso, start_time, chain,
        )

    # 5. Prior stdin
    prior = None
    if args.prior_stdin:
        try:
            raw_stdin = sys.stdin.buffer.read().decode('utf-8')
            prior = json.loads(raw_stdin)
        except Exception as e:
            status = 'usage_error'
            exit_code = 10
            detail = f'failed to read/parse prior from stdin: {e}'
            finish_and_exit(
                status, exit_code, detail, verdict_val, findings, resolved,
                coverage, limitations, lens, round_no, requested_model,
                reported_model, call_dir, secret_hits, repo_changes,
                workspace_new_files, guard_denials, repo, repo_before,
                plan_file, plan_chars, prompt_chars, agy_exec, agy_ver,
                result, started_iso, start_time, chain,
            )
        rc.write_text(os.path.join(call_dir, 'prior.json'), json.dumps(prior, ensure_ascii=False, indent=2))

    # 6. Build prompt
    try:
        prompt_text = prompt.build_prompt(plan_text, lens, round_no, prior)
        prompt_chars = len(prompt_text)
    except prompt.PromptError as e:
        if e.kind == 'plan_too_long':
            status = 'plan_too_long'
            exit_code = 9
        elif e.kind == 'invalid_prior':
            status = 'usage_error'
            exit_code = 10
        else:
            status = 'usage_error'
            exit_code = 10
        detail = str(e)
        finish_and_exit(
            status, exit_code, detail, verdict_val, findings, resolved,
            coverage, limitations, lens, round_no, requested_model,
            reported_model, call_dir, secret_hits, repo_changes,
            workspace_new_files, guard_denials, repo, repo_before,
            plan_file, plan_chars, prompt_chars, agy_exec, agy_ver,
            result, started_iso, start_time, chain,
        )
    except ValueError as e:
        status = 'usage_error'
        exit_code = 10
        detail = str(e)
        finish_and_exit(
            status, exit_code, detail, verdict_val, findings, resolved,
            coverage, limitations, lens, round_no, requested_model,
            reported_model, call_dir, secret_hits, repo_changes,
            workspace_new_files, guard_denials, repo, repo_before,
            plan_file, plan_chars, prompt_chars, agy_exec, agy_ver,
            result, started_iso, start_time, chain,
        )

    rc.write_text(os.path.join(call_dir, 'prompt.md'), prompt_text)

    # 7. Schema
    if round_no == 1:
        schema_path = verdict.SCHEMA_PATH
    else:
        schema = verdict.load_schema()
        req = schema.setdefault('required', [])
        if 'resolved' not in req:
            req.append('resolved')
        schema_path = os.path.join(call_dir, 'schema.json')
        rc.write_text(schema_path, json.dumps(schema, ensure_ascii=False, indent=2))

    # 8. Models and agy
    for model in chain['models']:
        try:
            rc.check_model(model, 'reviewer')
        except rc.RgsError as e:
            status = 'forbidden_flag'
            exit_code = 8
            detail = str(e)
            finish_and_exit(
                status, exit_code, detail, verdict_val, findings, resolved,
                coverage, limitations, lens, round_no, requested_model,
                reported_model, call_dir, secret_hits, repo_changes,
                workspace_new_files, guard_denials, repo, repo_before,
                plan_file, plan_chars, prompt_chars, agy_exec, agy_ver,
                result, started_iso, start_time, chain,
            )

    try:
        prefix = rc.find_agy()
        agy_exec = prefix[-1]
    except rc.RgsError as e:
        status = 'agy_error'
        exit_code = 3
        detail = str(e)
        finish_and_exit(
            status, exit_code, detail, verdict_val, findings, resolved,
            coverage, limitations, lens, round_no, requested_model,
            reported_model, call_dir, secret_hits, repo_changes,
            workspace_new_files, guard_denials, repo, repo_before,
            plan_file, plan_chars, prompt_chars, agy_exec, agy_ver,
            result, started_iso, start_time, chain,
        )

    agy_ver = get_agy_version()

    # 9. Repo snapshot before; models skipped after failing earlier in this session
    repo_before = rc.snapshot(repo)
    skips = load_skips(run_dir)
    order, chain['skipped'], chain['skips_ignored'] = plan_attempts(chain['models'], skips, timeout, time.time())
    requested_model = order[0]

    # 10. Isolated workspace
    ws = rc.isolated_workspace('rgs_facet_', sealed=True)
    try:
        ws_before = rc.snapshot(ws, ignore=('.agents/**',))

        # 11. Call agy with each model in turn until one gives a valid verdict
        for i, model in enumerate(order):
            requested_model = model
            save_prefix = os.path.join(call_dir, 'agy' if i == 0 else f'agy-{i + 1}')
            attempt_started = time.time()
            try:
                result = rc.call_agy(
                    prompt=prompt_text,
                    cwd=ws,
                    model=model,
                    schema_path=schema_path,
                    timeout_s=timeout,
                    grace_s=15,
                    save_as=save_prefix,
                    role='reviewer',
                )
            except rc.RgsError as e:
                status = 'forbidden_flag'
                exit_code = 8
                detail = str(e)
                result = None
                break

            # 12. Status of this attempt
            reported_model = result.reported_model
            status, exit_code, detail, review = evaluate(result, round_no, plan_text)
            verdict_val = review['verdict']
            findings = review['findings']
            resolved = review['resolved']
            coverage = review['coverage']
            limitations = review['limitations']
            chain['attempts'].append({
                'model': model,
                'status': status,
                'detail': detail,
                'reported_model': reported_model,
                'duration_s': round(time.time() - attempt_started, 2),
                'raw': os.path.basename(save_prefix),
            })

            # 13. Snapshot changes comparison; a modified workspace is never retried
            repo_changes = rc.snapshot_changes(repo_before, rc.snapshot(repo))
            workspace_new_files = rc.snapshot_changes(ws_before, rc.snapshot(ws, ignore=('.agents/**',)))
            if repo_changes or workspace_new_files:
                status = 'workspace_modified'
                exit_code = 6
                detail = detail or 'workspace or repo modified during review'
                break

            if status == 'ok':
                skips.pop(model, None)
                break
            if result.kind == 'quota':
                skips[model] = {'reason': 'quota', 'at': time.time()}
            elif status == 'timeout':
                skips[model] = {'reason': 'timeout', 'timeout_s': timeout, 'at': time.time()}
            if status not in FALLBACK_STATUSES:
                break
        if status in FALLBACK_STATUSES and len(chain['attempts']) > 1:
            tried = ', '.join(f"{a['model']} {a['status']}" for a in chain['attempts'])
            detail = f'every model failed ({tried}); last: {detail}'
        try:
            rc.write_text(os.path.join(run_dir, SKIPS_FILE), json.dumps(skips, ensure_ascii=False, indent=2))
        except OSError:
            pass

    finally:
        # 14. Guard log and cleanup
        if ws and os.path.exists(ws):
            entries, _ = rc.guard_log_since(ws, 0)
            guard_denials = [e for e in entries if e.get('decision') == 'deny']
            guard_src = os.path.join(ws, '.agents', 'rgs-guard.log')
            if os.path.exists(guard_src):
                shutil.copyfile(guard_src, os.path.join(call_dir, 'guard.log'))
            shutil.rmtree(ws, ignore_errors=True)

    # 15. Write meta.json and exit
    finish_and_exit(
        status, exit_code, detail, verdict_val, findings, resolved,
        coverage, limitations, lens, round_no, requested_model,
        reported_model, call_dir, secret_hits, repo_changes,
        workspace_new_files, guard_denials, repo, repo_before,
        plan_file, plan_chars, prompt_chars, agy_exec, agy_ver,
        result, started_iso, start_time, chain,
    )


if __name__ == '__main__':
    main()
