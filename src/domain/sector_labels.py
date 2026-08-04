"""English -> Arabic sector-name translation for Tadawul's published
GICS-style sector classification (the sector names SAHMK's company
directory returns). A sector not present in this map falls back to
"غير محدد" (unspecified) rather than the raw English string or an
English "Unclassified" label -- Basirah's Arabic-only UX requirement.
"""

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


def sector_label_ar(sector: "str | None") -> "str | None":
    if not sector:
        return None
    return SECTOR_LABELS_AR.get(sector, "غير محدد")
