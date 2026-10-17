"""facet 送審前的處理：截掉附錄、掃描密鑰、組出審查 prompt（docs/origins/facet/PLAN.md §4.3 步驟 1–2、§4.5、§4.8）。"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE_SCRIPTS = os.path.normpath(os.path.join(HERE, '..', '..', 'rgs-core', 'scripts'))
for _p in (HERE, CORE_SCRIPTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import secret_scan
import verdict

TEMPLATE_PATH = os.path.join(
    HERE,
    '..',
    'references',
    'review-prompt.md',
)
APPENDIX_MARKER = '<!-- facet:appendix -->'
LENSES = ('logic', 'gaps', 'verifiability')
MAX_PROMPT_CHARS = 30000

PRIOR_SCHEMA = {
    'type': 'object',
    'properties': {
        'changes_summary': {'type': 'string'},
        'prior_findings': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'id': {'type': 'string'},
                    'severity': {'type': 'string', 'enum': ['high', 'medium', 'low']},
                    'issue': {'type': 'string'},
                    'disposition': {'type': 'string', 'enum': ['accepted', 'rejected']},
                    'reason': {'type': 'string'},
                },
                'required': ['id', 'severity', 'issue', 'disposition', 'reason'],
            },
        },
    },
    'required': ['changes_summary', 'prior_findings'],
}

REQUIRED_SECTIONS = ('base', 'lens: logic', 'lens: gaps', 'lens: verifiability', 'round2')

_PLACEHOLDER = re.compile(r'\{(LENS|LENS_CHECKLIST|ROUND2_BLOCK|PLAN)\}')
_PRIOR_PLACEHOLDER = re.compile(r'\{PRIOR_JSON\}')


class PromptError(Exception):
    """不能送審。kind 是 'secret_suspected'、'plan_too_long' 或 'invalid_prior'（facet_review.py 會把前兩個當 status 回報）。"""

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def strip_appendix(text):
    """回傳第一個 APPENDIX_MARKER 之前的內容（去掉結尾空白）；沒有標記時回傳整份（去掉結尾空白）。"""
    idx = text.find(APPENDIX_MARKER)
    if idx == -1:
        return text.rstrip()
    return text[:idx].rstrip()


def load_plan(path):
    """以 'utf-8-sig' 讀取計畫檔，回傳 strip_appendix 的結果。"""
    with open(path, 'r', encoding='utf-8-sig') as f:
        content = f.read()
    return strip_appendix(content)


def scan_secrets(text):
    """回傳命中清單，每項是 {'kind': 名稱, 'line': 從 1 起算的行號, 'match': 遮蔽後的字串}。沒有命中回傳 []。

    樣式來自 rgs-core 的 secret_scan（內建樣式）。
    """
    hits = secret_scan.scan_text(text)
    return sorted(({'kind': h['kind'], 'line': h['line'], 'match': h['match']} for h in hits),
                  key=lambda h: (h['line'], h['kind']))


def load_template(path=TEMPLATE_PATH):
    """解析範本檔，回傳 {'base': str, 'lens': {'logic': str, 'gaps': str, 'verifiability': str}, 'round2': str}。"""
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()

    sections = {}
    current_sec = None
    for line in lines:
        if line.startswith('## '):
            title = line[3:].strip()
            if title in REQUIRED_SECTIONS:
                if title in sections:
                    raise ValueError(f"Duplicate section '{title}' in template")
                sections[title] = []
                current_sec = title
            else:
                current_sec = None
        else:
            if current_sec is not None:
                sections[current_sec].append(line)

    for sec in REQUIRED_SECTIONS:
        if sec not in sections:
            raise ValueError(f"Missing required section '{sec}' in template")

    result_blocks = {}
    for sec in REQUIRED_SECTIONS:
        sec_lines = sections[sec]
        start_idx = None
        for i, l in enumerate(sec_lines):
            if l.startswith('```text'):
                start_idx = i
                break
        if start_idx is None:
            raise ValueError(f"Section '{sec}' missing ```text block")

        end_idx = None
        for i in range(start_idx + 1, len(sec_lines)):
            if sec_lines[i].strip() == '```':
                end_idx = i
                break
        if end_idx is None:
            raise ValueError(f"Section '{sec}' has unclosed ```text block")

        result_blocks[sec] = '\n'.join(sec_lines[start_idx + 1 : end_idx])

    return {
        'base': result_blocks['base'],
        'lens': {
            'logic': result_blocks['lens: logic'],
            'gaps': result_blocks['lens: gaps'],
            'verifiability': result_blocks['lens: verifiability'],
        },
        'round2': result_blocks['round2'],
    }


def validate_prior(prior):
    """依 PRIOR_SCHEMA 驗證前輪資料；不合法時丟出 PromptError('invalid_prior', ...)。"""
    try:
        verdict.validate(prior, schema=PRIOR_SCHEMA, round_no=1)
    except verdict.VerdictError as e:
        raise PromptError('invalid_prior', str(e)) from e


def build_prompt(plan_text, lens, round_no=1, prior=None, template=None):
    """組出送給審查者的 prompt；template 為 None 時呼叫 load_template()。"""
    if lens not in LENSES:
        raise ValueError(f"Unknown lens: {lens!r}, expected one of {LENSES}")
    if not isinstance(round_no, int) or isinstance(round_no, bool) or round_no < 1:
        raise ValueError(f"Invalid round_no: {round_no!r}, must be an integer >= 1")
    if not isinstance(plan_text, str) or plan_text.strip() == '':
        raise ValueError("plan_text must be a non-empty string")
    if round_no == 1 and prior is not None:
        raise PromptError('invalid_prior', "Round 1 does not accept prior findings")
    if round_no >= 2 and prior is None:
        raise PromptError('invalid_prior', "Round 2 or later requires prior findings")
    if round_no >= 2:
        validate_prior(prior)
    if template is None:
        template = load_template()

    if round_no == 1:
        round2_block = ''
    else:
        prior_json_str = json.dumps(prior, ensure_ascii=False, indent=2)
        round2_block = _PRIOR_PLACEHOLDER.sub(lambda _: prior_json_str, template['round2'])

    values = {
        'LENS': lens,
        'LENS_CHECKLIST': template['lens'][lens],
        'ROUND2_BLOCK': round2_block,
        'PLAN': plan_text,
    }
    prompt = _PLACEHOLDER.sub(lambda m: values[m.group(1)], template['base'])

    if len(prompt) > MAX_PROMPT_CHARS:
        raise PromptError(
            'plan_too_long',
            f'prompt has {len(prompt)} characters, limit is {MAX_PROMPT_CHARS}',
        )

    return prompt
