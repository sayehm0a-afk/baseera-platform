"""Phase 2D: Stock Ranking Engine curation layer.

Computes no new scores and applies no new filtering of its own --
`RankingEngine.rank()` already produces all 17 gate-checked ranking
categories (see ranking.py's own Phase 2D docstring note for exactly
which 5 categories gained `is_publishable()` filtering this phase).
This module only picks the 8 categories the frontend Opportunities
screen already renders (`frontend/src/app/(app)/opportunities/page.tsx`'s
`OPPORTUNITY_SECTIONS`) and attaches, for each one, an Arabic label and
a plain-language description of the real field it is sorted by --
"transparent scoring factors," not a second scoring system.
"""

from dataclasses import dataclass
from typing import Dict, List

from src.market_intelligence.types import RankingCategory, RankingList

# Order matches the frontend's OPPORTUNITY_SECTIONS exactly.
OPPORTUNITY_CATEGORIES: List[RankingCategory] = [
    RankingCategory.TOP_STRONG_BUY,
    RankingCategory.TOP_BUY,
    RankingCategory.NEW_OPPORTUNITIES,
    RankingCategory.HIGHEST_EXPECTED_RETURN,
    RankingCategory.TOP_DIVIDEND_STOCKS,
    RankingCategory.LOWEST_RISK,
    RankingCategory.MOST_BULLISH,
    RankingCategory.MOST_BEARISH,
]

OPPORTUNITY_LABELS_AR: Dict[RankingCategory, str] = {
    RankingCategory.TOP_STRONG_BUY: "شراء قوي",
    RankingCategory.TOP_BUY: "الأعلى شراءً",
    RankingCategory.NEW_OPPORTUNITIES: "فرص جديدة",
    RankingCategory.HIGHEST_EXPECTED_RETURN: "الأعلى عائدًا متوقعًا",
    RankingCategory.TOP_DIVIDEND_STOCKS: "أسهم توزيعات",
    RankingCategory.LOWEST_RISK: "الأقل مخاطرة",
    RankingCategory.MOST_BULLISH: "الأكثر إيجابية",
    RankingCategory.MOST_BEARISH: "الأكثر سلبية",
}

OPPORTUNITY_SCORING_FACTOR_AR: Dict[RankingCategory, str] = {
    RankingCategory.TOP_STRONG_BUY: "الترتيب حسب درجة الثقة، ضمن توصيات «شراء قوي» فقط.",
    RankingCategory.TOP_BUY: "الترتيب حسب الدرجة الإجمالية للتحليل الفني والأساسي مجتمعين.",
    RankingCategory.NEW_OPPORTUNITIES: "أسهم أصبحت توصية شراء اليوم لأول مرة، أو بعد ترقية من تصنيف أضعف.",
    RankingCategory.HIGHEST_EXPECTED_RETURN: "الترتيب حسب نسبة العائد المتوقع حتى الهدف السعري.",
    RankingCategory.TOP_DIVIDEND_STOCKS: "الترتيب حسب نسبة توزيعات الأرباح السنوية.",
    RankingCategory.LOWEST_RISK: "الترتيب حسب مستوى المخاطرة (الأقل أولًا)، ثم درجة الثقة كعامل ترجيح.",
    RankingCategory.MOST_BULLISH: "الترتيب حسب الدرجة الإجمالية للتحليل، من الأعلى إلى الأدنى.",
    RankingCategory.MOST_BEARISH: "الترتيب حسب الدرجة الإجمالية للتحليل، من الأدنى إلى الأعلى.",
}

GATE_EXCLUSION_NOTE_AR = (
    "تم استبعاد أي سهم لم يجتز بوابات النشر (بيانات حقيقية، حداثة البيانات، "
    "سعر صالح، عائد إلى مخاطرة منطقي، جودة دخول مقبولة) من هذه القائمة."
)


@dataclass(frozen=True)
class OpportunityCategory:
    category: RankingCategory
    label_ar: str
    scoring_factor_ar: str
    gate_exclusion_note_ar: str
    ranking_list: RankingList


def curate_opportunity_rankings(
    all_rankings: Dict[RankingCategory, RankingList],
) -> List[OpportunityCategory]:
    """`all_rankings` is the full dict `RankingEngine.rank()` returns --
    this just selects and annotates a fixed 8-category subset of it, in
    a fixed order, skipping any category the caller's rankings dict
    happens not to contain rather than raising (keeps this resilient to
    a caller passing a filtered subset, e.g. via the `category` query
    param `/market/rankings` already supports)."""
    return [
        OpportunityCategory(
            category=category,
            label_ar=OPPORTUNITY_LABELS_AR[category],
            scoring_factor_ar=OPPORTUNITY_SCORING_FACTOR_AR[category],
            gate_exclusion_note_ar=GATE_EXCLUSION_NOTE_AR,
            ranking_list=all_rankings[category],
        )
        for category in OPPORTUNITY_CATEGORIES
        if category in all_rankings
    ]
