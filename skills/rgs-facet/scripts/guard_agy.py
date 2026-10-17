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


def _is_agy_word(word):
    """Return True if word's final path component is agy or agy.exe."""
    if not isinstance(word, str):
        return False
    clean = word.rstrip(');}')
    clean = clean.strip('\'"')
    clean = clean.replace('\\', '/')
    token = clean.split('/')[-1].lower()
    return token in ('agy', 'agy.exe')


def _quoted_word(inner):
    """Return the executable candidate inside a quoted string.

    The first word decides, except when it looks like the start of a path: then the quoted text
    may be a path with spaces ("C:\\Program Files\\agy\\agy.exe -p x"), so prefixes of 2, 3, ...
    words are tried as well. A quoted command whose first word is a path to another program and
    whose later argument ends in /agy would be blocked; that is accepted for this second-line guard.
    """
    words = inner.split()
    if not words:
        return ''
    first = words[0]
    if _is_agy_word(first) or not any(c in first for c in ('/', '\\', ':')):
        return first
    for n in range(2, len(words) + 1):
        candidate = ' '.join(words[:n])
        if _is_agy_word(candidate):
            return candidate
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

        if _is_agy_word(word):
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
