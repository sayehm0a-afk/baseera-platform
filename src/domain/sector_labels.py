"""English -> Arabic sector-name translation for Tadawul's published
GICS-style sector classification (the sector names SAHMK's company
directory returns). A sector not present in this map falls back to
"غير محدد" (unspecified) rather than the raw English string or an
English "Unclassified" label -- Basirah's Arabic-only UX requirement.
"""

import re

SECTOR_LABELS_AR = {
    "Energy": "الطاقة",
    "Materials": "المواد الأساسية",
    "Capital Goods": "السلع الرأسمالية",
    "Commercial & Professional Services": "الخدمات التجارية والمهنية",
    "Transportation": "النقل",
    "Consumer Durables & Apparel": "السلع المعمرة والملابس",
    "Consumer Services": "الخدمات الاستهلاكية",
    "Media and Entertainment": "الإعلام والترفيه",
    "Retailing": "تجزئة السلع الكمالية",
    "Food & Staples Retailing": "تجزئة المواد الغذائية والأساسية",
    "Food & Beverages": "الأغذية والمشروبات",
    "Health Care Equipment & Svc": "معدات وخدمات الرعاية الصحية",
    "Pharma, Biotech & Life Science": "الأدوية والتقنية الحيوية",
    "Banks": "البنوك",
    "Diversified Financials": "الخدمات المالية المتنوعة",
    "Insurance": "التأمين",
    "Real Estate Mgmt & Dev't": "إدارة وتطوير العقارات",
    "REITs": "الصناديق العقارية المتداولة",
    "Software & Services": "البرمجيات والخدمات التقنية",
    "Telecommunication Services": "خدمات الاتصالات",
    "Utilities": "المرافق العامة",
}


# Real production evidence (M7 audit, symbols 6004/9591) showed SAHMK
# does not consistently spell out the same abbreviations this map's own
# keys use -- e.g. symbol 6004 came back "Commercial & Professional Svc"
# (this map's key spells "Services" in full) while symbol 9591 came back
# "Real Estate Mgmt & Development" (this map's key abbreviates "Dev't").
# Matching only the exact key string silently dropped a real, mappable
# sector to "غير محدد". Normalizing both sides through the same
# abbreviation expansion makes the match order-independent without
# hardcoding every specific variant.
_ABBREVIATION_EXPANSIONS = (
    (re.compile(r"\bSvc\.?\b", re.IGNORECASE), "Services"),
    (re.compile(r"\bMgmt\.?\b", re.IGNORECASE), "Management"),
    (re.compile(r"\bDev't\.?\b", re.IGNORECASE), "Development"),
)


def _normalize_sector(sector: str) -> str:
    text = sector.strip()
    for pattern, replacement in _ABBREVIATION_EXPANSIONS:
        text = pattern.sub(replacement, text)
    return re.sub(r"\s+", " ", text).strip().lower()


_NORMALIZED_LABELS_AR = {_normalize_sector(k): v for k, v in SECTOR_LABELS_AR.items()}


def sector_label_ar(sector: "str | None") -> "str | None":
    if not sector:
        return None
    direct = SECTOR_LABELS_AR.get(sector)
    if direct is not None:
        return direct
    return _NORMALIZED_LABELS_AR.get(_normalize_sector(sector), "غير محدد")
