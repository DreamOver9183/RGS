"""Stand-in for agy in tests. Behaviour comes from environment variables:

FAKE_AGY_SCENARIO  ok | timeout | error | quota | quota_model | no_struct | implement | review_findings
                   | batch_echo | digest_echo | sleep_child | structured | ws_write
FAKE_AGY_DIR       folder for calls/ (one JSON file per invocation: argv, cwd, the guard policy and the
                   absolute paths in the prompt that do not exist) and counters
FAKE_AGY_WRITE     implement: comma-separated paths (relative to cwd) to append a line to
FAKE_AGY_QUOTA_MODEL  quota_model: the model that reports quota exhaustion
FAKE_AGY_DROP      batch_echo: an id left out of the first reply
FAKE_AGY_LABEL     label string for the log file; empty string writes log without label line
FAKE_AGY_MODELS    semicolon-separated model IDs for the 'models' subcommand
FAKE_AGY_TOUCH     absolute path to append a line to before processing any scenario
FAKE_AGY_STRUCTURED  JSON string for structured and ws_write scenarios

Subcommands handled before reading environment:
--version          prints 'agy 1.4.0'
models             prints tab-separated model ID and display name
"""
import json
import os
import re
import subprocess
import sys
import time
import uuid


def arg(name):
    argv = sys.argv[1:]
    return argv[argv.index(name) + 1] if name in argv else None


def count_calls(state_dir):
    return len(os.listdir(os.path.join(state_dir, 'calls'))) if state_dir else 1


def emit(data, code=0, stderr=''):
    sys.stdout.write(json.dumps(data, ensure_ascii=False))
    if stderr:
        sys.stderr.write(stderr)
    sys.exit(code)


def main():
    if sys.argv[1:] == ['--version']:
        print('agy 1.4.0')
        sys.exit(0)
    if sys.argv[1:2] == ['models']:
        models_env = os.environ.get('FAKE_AGY_MODELS')
        if models_env:
            model_ids = [m.strip() for m in models_env.split(';') if m.strip()]
        else:
            model_ids = ['gemini-4-argon-high', 'gemini-3.8-flash-high', 'gemini-3.8-flash-low']
        for mid in model_ids:
            print(f'{mid}\tFake {mid}')
        sys.exit(0)

    scenario = os.environ.get('FAKE_AGY_SCENARIO', 'ok')
    state_dir = os.environ.get('FAKE_AGY_DIR')
    prompt = arg('-p') or ''
    model = arg('--model')
    schema = arg('--json-schema')
    log_file = arg('--log-file')
    if log_file:
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        label_env = os.environ.get('FAKE_AGY_LABEL')
        label = ('Fake ' + str(model)) if label_env is None else label_env
        with open(log_file, 'w', encoding='utf-8', newline='\n') as f:
            if label:
                f.write(f'I1017 00:00:00.000000 1 model.go:1] Propagating selected model override to backend: label="{label}"\n')
    if state_dir:
        # One file per call: parallel processes appending to one file can lose lines on Windows.
        calls_dir = os.path.join(state_dir, 'calls')
        os.makedirs(calls_dir, exist_ok=True)
        policy = os.path.join(os.getcwd(), '.agents', 'rgs-guard.json')
        guard = None
        if os.path.exists(policy):
            with open(policy, encoding='utf-8') as f:
                guard = json.load(f)
        # Absolute paths quoted in the prompt that do not exist while agy runs.
        missing = [p for p in re.findall(r'`((?:[A-Za-z]:)?[\\/][^`]*)`', prompt) if not os.path.exists(p)]
        with open(os.path.join(calls_dir, f'{time.time_ns()}-{uuid.uuid4().hex[:6]}.json'), 'w', encoding='utf-8') as f:
            json.dump({'argv': sys.argv[1:], 'cwd': os.getcwd(), 'scenario': scenario, 'guard': guard,
                       'missing_paths': missing}, f, ensure_ascii=False)
    base = {'conversation_id': arg('--conversation') or str(uuid.uuid4()), 'status': 'SUCCESS',
            'duration_seconds': 0.1, 'num_turns': 1,
            'usage': {'input_tokens': 1000, 'output_tokens': 10, 'total_tokens': 1010}}

    touch_path = os.environ.get('FAKE_AGY_TOUCH')
    if touch_path:
        os.makedirs(os.path.dirname(os.path.abspath(touch_path)), exist_ok=True)
        with open(touch_path, 'a', encoding='utf-8', newline='\n') as f:
            f.write(f'# touched by fake_agy {time.time_ns()}\n')

    if scenario == 'sleep_child':
        child = subprocess.Popen(
            [sys.executable, '-c', 'import time; time.sleep(120)'],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        pids_file = os.path.join(state_dir or '.', 'pids.json')
        with open(pids_file, 'w', encoding='utf-8') as f:
            json.dump({'parent': os.getpid(), 'child': child.pid}, f)
        time.sleep(120)
        emit({**base, 'response': 'woke up'})

    if scenario == 'timeout':
        emit({**base, 'response': ''}, stderr='[agy] print timeout after 5s with turn in progress; returning partial output\n')
    if scenario == 'error':
        emit({**base, 'status': 'ERROR', 'response': 'VERDICT: PASS', 'error': {'message': 'stream was interrupted'}})
    if scenario == 'quota' or (scenario == 'quota_model' and model == os.environ.get('FAKE_AGY_QUOTA_MODEL')):
        emit({**base, 'status': 'ERROR', 'response': '',
              'error': {'message': 'Individual quota reached. Resets in 1h19m', 'code': 'RESOURCE_EXHAUSTED'}})
    if scenario == 'no_struct':
        emit({**base, 'response': 'I am waiting for the subagent to report back.'})

    if scenario == 'implement':
        for rel in filter(None, (os.environ.get('FAKE_AGY_WRITE') or '').split(',')):
            path = os.path.join(os.getcwd(), rel)
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
            with open(path, 'a', encoding='utf-8', newline='\n') as f:
                f.write(f'# change {count_calls(state_dir)}\n')
        emit({**base, 'response': 'Changed: ' + (os.environ.get('FAKE_AGY_WRITE') or 'nothing')})

    if scenario == 'ws_write':
        with open(os.path.join(os.getcwd(), 'probe.txt'), 'w', encoding='utf-8', newline='\n') as f:
            f.write('probe\n')

    if scenario in ('structured', 'ws_write'):
        raw = os.environ.get('FAKE_AGY_STRUCTURED', '{}')
        try:
            structured = json.loads(raw)
        except (ValueError, TypeError):
            structured = raw
        out = {**base, 'response': 'done'}
        if schema:
            out['json_schema'] = schema
        out['structured_output'] = structured
        emit(out)

    structured = None
    if schema:
        with open(schema, encoding='utf-8') as f:
            props = json.load(f).get('properties', {})
        if 'verdict' in props:
            findings = []
            if scenario == 'review_findings':
                findings = [{'severity': 'major', 'category': 'correctness',
                             'file': os.path.join(os.getcwd(), 'calc.py'), 'line': 3,
                             'title': 'missing zero check', 'detail': 'div(1, 0) raises', 'suggestion': 'guard b == 0'},
                            {'severity': 'minor', 'category': 'architecture', 'file': 'calc.py', 'line': 1,
                             'title': 'naming', 'detail': 'nit', 'suggestion': ''}]
            structured = {'verdict': 'PASS', 'summary': 'reviewed', 'findings': findings}
        elif 'items' in props:
            ids = [json.loads(line)['id'] for line in prompt.splitlines()
                   if line.startswith('{') and '"id"' in line]
            drop = os.environ.get('FAKE_AGY_DROP')
            marker = os.path.join(state_dir or '.', 'dropped')
            items = []
            for i in ids:
                if i == drop and not os.path.exists(marker):
                    open(marker, 'w').close()
                    continue
                items.append({'id': i, 'output': f'out-{i}'})
            structured = {'items': items}
        elif 'findings' in props:
            m = re.search(r'chunk-\d+\.txt', prompt)
            findings = []
            if m:
                with open(os.path.join(os.getcwd(), m.group(0)), encoding='utf-8') as f:
                    current = None
                    for line in f:
                        if line.startswith('# 檔案：'):
                            current = line[len('# 檔案：'):].split('（')[0]
                        hit = re.match(r'L(\d+): (.*ERROR.*)', line.rstrip('\n'))
                        if hit:
                            findings.append({'claim': 'an error', 'file': current, 'line_start': int(hit.group(1)),
                                             'line_end': int(hit.group(1)), 'quote': hit.group(2)})
            findings.append({'claim': 'made up', 'file': current if m else 'x.log', 'line_start': 1,
                             'line_end': 1, 'quote': 'this text is not in the file'})
            structured = {'findings': findings}
    out = {**base, 'response': 'done'}
    if schema:
        out['json_schema'] = schema
        out['structured_output'] = structured
    emit(out)


if __name__ == '__main__':
    main()
