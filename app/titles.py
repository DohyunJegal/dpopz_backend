"""곡명 정규화"""
import re
import unicodedata

# 특수 케이스 (완전 일치)
_ALIASES: dict[str, str] = {
    'ACTØ': 'ACT0',
    'CODE:Ø': 'CODE:0',
    'ÆTHER': 'ATHER',
    'BLO§OM': 'BLOSSOM',
    '火影': '焱影',
    "POLꓘAMAИIA": "POLꞰAMAИIA",
    "Τeλοs": "Τέλος",
    # 'Zenith'와 'ZEИITH' 충돌 방지
    "ZEИITH": "zenith2",
    "ZENITH": "zenith2",
    # 'with you…'와 'With You' 충돌 방지
    "with you...": "withyoudd",
    "with you…": "withyoudd",
}

# NFKD로 분해되지 않는 유사자 치환 테이블
_TRANS = str.maketrans({
    '¡': '!',
    'Ø': 'O', 'ø': 'o',
    'Ʞ': 'K',
    'æ': 'ae', 'Æ': 'AE',
    'Λ': 'A', '∧': 'A',
    'ə': 'e',
    'Χ': 'X', 'χ': 'x',
    'ƒ': 'f',
    '<': '', '>': '',
    'И': 'N',
})

_STRIP = re.compile(
    r"[\s\t\-_.'’\"“”()~〜～♡♥"
    r"♪♫♬"   # ♪♫♬
    r"《》"         # 《》
    r"・·"         # ・ ·
    r"♨"               # ♨
    r"​﻿"         # 제로 너비 공백
    r"!]"
)


def normalize_title(title: str) -> str:
    title = _ALIASES.get(title, title)
    title = title.translate(_TRANS)
    title = unicodedata.normalize('NFKD', title)
    title = ''.join(c for c in title if unicodedata.category(c) != 'Mn')
    return _STRIP.sub('', title.lower())
