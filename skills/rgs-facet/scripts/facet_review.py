"""Run one facet review turn: validate inputs, invoke agy in an isolated sealed workspace, and record results.

Usage:
    python -I facet_review.py --plan-file <計畫檔> --lens logic|gaps|verifiability --round <N> --model <M>
                              [--timeout 300] [--session <ID>] [--run-dir <資料夾>] [--repo <專案資料夾>] [--prior-stdin]

Status and Exit Codes:
    | status             | exit | condition                                                              |
    | ok                 |    0 | Valid verdict obtained                                                 |
    | timeout            |    2 | agy execution timed out                                                |
    | agy_error          |    3 | agy returned error/quota, or agy executable not found                  |
    | empty_output       |    4 | agy returned no structured_output                                       |
    | parse_error        |    5 | structured_output is a string and JSON parsing failed                  |
    | schema_error       |    5 | verdict schema validation failed                                       |
    | workspace_modified |    6 | repo or workspace modified during call (preempts all other post-call)   |
    | secret_suspected   |    7 | Secret suspected in plan; agy not invoked                              |
    | forbidden_flag     |    8 | Forbidden agy arguments or non-gemini model; agy not invoked           |
    | plan_too_long      |    9 | Prompt constructed from plan exceeds char limit; agy not invoked       |
    | usage_error        |   10 | Command line/file/prior syntax errors; agy not invoked                  |

只做一次送審，重試與多輪迴圈由 SKILL.md 負責。
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


class UsageError(Exception):
    pass


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
):
    finished_time = time.time()
    finished_iso = time.strftime('%Y-%m-%dT%H:%M:%S')
    duration_s = round(finished_time - start_time, 2)
    test_double = bool(os.environ.get('RGS_AGY'))

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

    parser = FacetArgumentParser(description='Run one facet review turn.')
    parser.add_argument('--plan-file', required=True)
    parser.add_argument('--lens', required=True)
    parser.add_argument('--round', required=True, type=int)
    parser.add_argument('--model', required=True)
    parser.add_argument('--timeout', type=int, default=300)
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
            result, started_iso, start_time,
        )

    lens = args.lens
    round_no = args.round
    requested_model = args.model
    timeout = args.timeout

    try:
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
            result, started_iso, start_time,
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
            result, started_iso, start_time,
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
            result, started_iso, start_time,
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
                result, started_iso, start_time,
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
            result, started_iso, start_time,
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
            result, started_iso, start_time,
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

    # 8. Find agy
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
            result, started_iso, start_time,
        )

    agy_ver = get_agy_version()

    # 9. Repo snapshot before
    repo_before = rc.snapshot(repo)

    # 10. Isolated workspace
    ws = rc.isolated_workspace('rgs_facet_', sealed=True)
    try:
        ws_before = rc.snapshot(ws, ignore=('.agents/**',))

        # 11. Call agy
        save_prefix = os.path.join(call_dir, 'agy')
        try:
            result = rc.call_agy(
                prompt=prompt_text,
                cwd=ws,
                model=requested_model,
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

        if result is not None:
            reported_model = result.reported_model
            # 12. Determine status based on result.kind
            if result.kind == 'timeout':
                status = 'timeout'
                exit_code = 2
                detail = result.detail
            elif result.kind in ('error', 'quota'):
                status = 'agy_error'
                exit_code = 3
                detail = result.detail
            elif result.kind == 'empty':
                status = 'empty_output'
                exit_code = 4
                detail = result.detail
            elif result.kind == 'ok':
                data = result.structured
                if isinstance(data, str):
                    try:
                        data = verdict.parse_response(data)
                    except verdict.VerdictError as e:
                        status = e.kind  # 'parse_error'
                        exit_code = 5
                        detail = str(e)

                if status != 'parse_error':
                    try:
                        verdict.validate(data, round_no=round_no)
                    except verdict.VerdictError as e:
                        status = e.kind  # 'schema_error'
                        exit_code = 5
                        detail = str(e)

                if status not in ('parse_error', 'schema_error'):
                    status = 'ok'
                    exit_code = 0
                    detail = ''
                    verdict_val = data.get('verdict')
                    coverage = data.get('coverage')
                    limitations = data.get('limitations')
                    if round_no >= 2:
                        resolved = data.get('resolved') or []
                    else:
                        resolved = []
                    findings = []
                    for f in data.get('findings') or []:
                        f_copy = dict(f)
                        f_copy['evidence_found'] = verdict.evidence_found(f.get('evidence', ''), plan_text)
                        findings.append(f_copy)

        # 13. Snapshot changes comparison
        repo_changes = rc.snapshot_changes(repo_before, rc.snapshot(repo))
        workspace_new_files = rc.snapshot_changes(ws_before, rc.snapshot(ws, ignore=('.agents/**',)))
        if repo_changes or workspace_new_files:
            status = 'workspace_modified'
            exit_code = 6
            detail = detail or 'workspace or repo modified during review'

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
        result, started_iso, start_time,
    )


if __name__ == '__main__':
    main()
