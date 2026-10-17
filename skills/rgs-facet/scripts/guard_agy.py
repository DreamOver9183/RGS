"""Claude Code PreToolUse hook to prevent direct agy execution."""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

SPLIT_PATTERN = re.compile(r'&&|\|\||[;\n`|]|\$\(|(?<!&)&(?!&)')
ENV_VAR_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|\'[^\']*\'|\S+)(?:\s+|$)')
CALL_EXEC_ENV_PATTERN = re.compile(
    r'^(?:call|exec|env|command|eval|time|nohup|sudo)(?:\s+|$)', re.IGNORECASE
)


def _quoted_word(inner):
    """Return the executable candidate from inside a quoted string."""
    first = inner.split(None, 1)[0] if inner.split() else ''
    if any(c in first for c in ('/', '\\', ':')):
        return inner
    return first


def is_direct_agy(command):
    """True when a shell segment of command starts with the agy executable (design D-18)."""
    if not isinstance(command, str):
        return False

    segments = SPLIT_PATTERN.split(command)
    for raw_seg in segments:
        seg = raw_seg.strip()
        if not seg:
            continue

        while True:
            seg = seg.strip()
            if not seg:
                break
            # Strip leading environment variables: NAME=value
            m = ENV_VAR_PATTERN.match(seg)
            if m:
                seg = seg[m.end():]
                continue
            # Strip leading PowerShell call operator: &
            if seg.startswith('&'):
                seg = seg[1:]
                continue
            # Strip leading subshell or group braces: ( or {
            if seg.startswith('(') or seg.startswith('{'):
                seg = seg[1:]
                continue
            # Strip leading call, exec, env, command, eval, time, nohup, sudo
            m = CALL_EXEC_ENV_PATTERN.match(seg)
            if m:
                seg = seg[m.end():]
                continue
            break

        seg = seg.strip()
        if not seg:
            continue

        # Extract first word
        if seg.startswith('"'):
            m = re.match(r'^"([^"]*)"', seg)
            word = _quoted_word(m.group(1) if m else seg[1:])
        elif seg.startswith("'"):
            m = re.match(r"^'([^']*)'", seg)
            word = _quoted_word(m.group(1) if m else seg[1:])
        else:
            word = seg.split(None, 1)[0]

        word = word.rstrip(');}')
        word = word.strip('\'"')

        word = word.replace('\\', '/')
        token = word.split('/')[-1].lower()
        if token in ('agy', 'agy.exe'):
            return True

    return False


def main():
    """Read the hook payload on stdin; print a deny decision for direct agy calls, nothing otherwise."""
    try:
        raw = sys.stdin.buffer.read().decode('utf-8', errors='replace')
        if not raw.strip():
            sys.exit(0)
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            sys.exit(0)
        if payload.get('tool_name') != 'Bash':
            sys.exit(0)
        tool_input = payload.get('tool_input')
        if not isinstance(tool_input, dict):
            sys.exit(0)
        command = tool_input.get('command')
        if not isinstance(command, str):
            sys.exit(0)

        if is_direct_agy(command):
            decision = {
                'hookSpecificOutput': {
                    'hookEventName': 'PreToolUse',
                    'permissionDecision': 'deny',
                    'permissionDecisionReason': (
                        'rgs-facet: 不要直接執行 agy，請改用 scripts/facet_review.py'
                        '（它會裝好唯讀防護並檢查參數）'
                    ),
                }
            }
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8')
            print(json.dumps(decision, ensure_ascii=False))
            sys.exit(0)
    except Exception:
        sys.exit(0)


if __name__ == '__main__':
    main()
