"""Shared translation prompt rules and output checks for RimTaiName dictionary building."""
import csv
import os
import re
import unicodedata

# Rules 1-5 and the examples live in Prompts/NameRules_zhTW.txt, shared with the in-game C# PromptBuilder.
SHARED_RULES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 'Prompts', 'NameRules_zhTW.txt')
EXAMPLES_HEADING = '【範例】\n'


def load_shared_rules(path=SHARED_RULES_PATH):
    """Return (rules, examples) from the shared rules file; rules end with a newline."""
    with open(path, encoding='utf-8-sig') as f:  # -sig drops a BOM, as the C# reader does
        text = f.read()
    rules, sep, examples = text.partition('\n' + EXAMPLES_HEADING)
    if not sep:
        raise ValueError(f'{path}: missing {EXAMPLES_HEADING.strip()} section')
    return rules.rstrip('\n') + '\n', EXAMPLES_HEADING + examples


_SHARED_RULES, _SHARED_EXAMPLES = load_shared_rules()

TRANSLATION_RULES = ("""你是《RimWorld》（邊緣世界）的臺灣繁體中文在地化譯者。請把輸入的每個「角色姓名詞」翻成中文。不要使用任何工具，不要讀寫檔案，直接輸出結果。

【輸入欄位】
id、text（原文）、type（given_name 名／surname 姓／given_name_or_surname 名或姓／nickname 暱稱）、gender、origin（Japanese、Russian、British、invented/sci-fi 等來源提示，可能為空）、used_by（特殊族群說明，可能為空）、example（原版中含此詞的完整姓名，格式為「名 '暱稱' 姓」，可能為空）。

"""
                     + _SHARED_RULES
                     + '6. 每個 id 都必須回傳，且只回傳一個譯名。\n\n'
                     + _SHARED_EXAMPLES)

OUTPUT_SCHEMA = {
    'type': 'object',
    'properties': {
        'items': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'id': {'type': 'string'},
                    'zh': {'type': 'string'},
                },
                'required': ['id', 'zh'],
            },
        },
    },
    'required': ['items'],
}

CJK_ONLY = re.compile(r'^[㐀-䶿一-鿿]+$')
# Characters that only exist in Simplified Chinese (common in transliterations / CJK names).
SIMPLIFIED = set('们尔兰罗丽维华亚达莱纳顿伦赛劳乔汉马鲁费贝玛娅丝东韦苏迈鲍约汤奥万历门卢齐杨刘黄吴张陈赵孙郑冯许邓韩'
                 '泽树优纪绘叶凉铃爱乐岛荣实胜辉龙凤时广庆刚诚宫桥边织泪阳飞岚卫闻兴')
# Japanese shinjitai forms that Taiwan writes in traditional form.
SHINJITAI = set('桜沢恵竜広浜斉栄来気楽弥亜絵稲渉実剣団図国県蔵豊単伝徳将巌険')


ABBREVIATION = re.compile(r'^[A-Z]{2,4}$')
SINGLE_LETTER = re.compile(r'^[A-Z]$')


def special_form(text, namespace):
    """Deterministic translation for initials, or None. Mirrors the in-game SpecialFormRule."""
    text = unicodedata.normalize('NFKC', text.strip())
    if ABBREVIATION.match(text):
        return text  # MJ, DJ, ET: keep as written
    if SINGLE_LETTER.match(text):
        return text if namespace == 'name' else '阿' + text  # B / 阿B
    return None


def entry_key(namespace, text):
    """Key for matching dictionary rows with the fix lists: Trim, NFC and lower case, like the dictionary keys."""
    return (namespace or '').strip(), unicodedata.normalize('NFC', (text or '').strip()).lower()


def read_rows(path):
    """CSV rows with a namespace and a text; blank lines left by spreadsheet editors are skipped."""
    with open(path, encoding='utf-8-sig', newline='') as f:
        return [r for r in csv.DictReader(f) if (r.get('namespace') or '').strip() and (r.get('text') or '').strip()]


def is_cjk(c):
    """CJK Extension A and Unified Ideographs; the Yijing hexagram symbols in between are excluded."""
    return '㐀' <= c <= '䶿' or '一' <= c <= '鿿'


def latin_ok(text, zh):
    """Latin letters are allowed only as half-width capitals that also appear capitalised in the source."""
    source_caps = set(unicodedata.normalize('NFKC', text)) & set('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    return all(is_cjk(c) or c in source_caps for c in zh)


def check(text, zh, namespace):
    """Return a list of automatic warnings for one translation."""
    warns = []
    if not zh:
        return ['空白']
    if not CJK_ONLY.match(zh) and not latin_ok(text, zh):
        warns.append('含非中文字元')
    if len(zh) > (16 if namespace == 'nick' else 12):
        warns.append('超過長度上限')
    if namespace != 'nick' and len(zh) > 6:
        warns.append('名姓偏長')
    simp = sorted({c for c in zh if c in SIMPLIFIED})
    if simp:
        warns.append('簡體字:' + ''.join(simp))
    shin = sorted({c for c in zh if c in SHINJITAI})
    if shin:
        warns.append('日文新字體:' + ''.join(shin))
    return warns
