"""Arabic text normalization for search matching -- the standard
diacritics/letter-variant folding most Arabic-aware search engines
apply (the same rules as Elasticsearch/Lucene's built-in
`arabic_normalization` char filter, reimplemented here with no new
dependency): a user typing "ارامكو" (no hamza), "أرامكو" (hamza on
alef), or "أرامكو  السعودية" (extra internal spacing) must all match
the one real stored Arabic company name -- Phase 1's "normalized
Arabic forms, common spacing variations" search requirement.

Deliberately not a fuzzy/phonetic matcher (no edit-distance, no
transliteration) -- only the specific, well-known cases where Arabic
text legitimately varies in ways a human reader treats as identical:
alef-with-hamza forms collapsing to bare alef, alef maksura (ى)
collapsing to yaa (ي), taa marbuta (ة) collapsing to haa (ه), tatweel
(ـ) and combining diacritics (tashkeel) removed entirely, and
whitespace collapsed/stripped. A search that still returns no results
after this is an honest "no match," not a guess.
"""

import re
import unicodedata

_ALEF_VARIANTS = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ة": "ه",
        "ـ": "",  # tatweel/kashida
    }
)

# Arabic combining diacritics (tashkeel) -- fatha/damma/kasra/sukun/
# shadda/tanwin/quranic marks -- stripped entirely, never meaningful
# for a company-name search match.
_TASHKEEL_RE = re.compile(
    "[" + "".join(chr(c) for c in range(0x0617, 0x061B)) + "".join(chr(c) for c in range(0x064B, 0x0653)) + "ٰ"
    + "".join(chr(c) for c in range(0x06D6, 0x06ED + 1)) + "]"
)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_arabic(text: str) -> str:
    """Case-insensitivity has no meaning for Arabic script (no case),
    so this only folds the letter variants/diacritics/whitespace
    above -- safe to apply to both a stored name and a user's query
    and compare the results directly."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = _TASHKEEL_RE.sub("", normalized)
    normalized = normalized.translate(_ALEF_VARIANTS)
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized
