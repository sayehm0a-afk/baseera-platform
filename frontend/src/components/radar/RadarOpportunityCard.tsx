"use client";

import { useState } from "react";
import { AiStar } from "@/components/ai/AiStar";
import { ConfidenceBar } from "@/components/ai/ConfidenceBar";
import { DecisionBadge } from "@/components/badges/DecisionBadge";
import { SymbolText } from "@/components/shared/SymbolText";
import { ApiError } from "@/lib/api/client";
import type { RadarOpportunitySummary } from "@/lib/api/radar-types";
import { followSignal } from "@/lib/api/signals";
import {
  decisionFreshnessLabelAr,
  FRESHNESS_LABELS_AR,
  formatArabicDateTime,
  formatRelativeAgeAr,
  isEntryMissed,
} from "@/lib/format/freshness";

interface RadarOpportunityCardProps {
  opportunity: RadarOpportunitySummary;
}

export { FRESHNESS_LABELS_AR };

function priceLabel(value: number | null): string {
  return value == null ? "--" : value.toFixed(2);
}

const RELIABILITY_COLOR: Record<string, string> = {
  HIGH: "bg-bsr-market-up/15 text-bsr-market-up",
  MODERATE: "bg-bsr-gold-500/15 text-bsr-gold-500",
  LOW: "bg-bsr-market-down/15 text-bsr-market-down",
  INSUFFICIENT_DATA: "bg-bsr-surface-raised text-bsr-text-secondary",
};

/** One Smart Radar opportunity card -- every field is read straight
 * from GET /api/v1/radar/summary or /opportunities, never recomputed
 * here (see src.market_intelligence.radar_v2). Mirrors
 * PersonalOpportunityCard's layout so both product surfaces read
 * consistently, but sourced from RadarOpportunity/Decision V2 data
 * instead of the personal-scan simplification. */
const ACTIONABLE_CLASSIFICATIONS = new Set(["STRONG_BUY_CANDIDATE", "BUY_CANDIDATE"]);

type FollowState = "idle" | "following" | "followed" | "error";

export function RadarOpportunityCard({ opportunity: o }: RadarOpportunityCardProps) {
  const entryMissed = isEntryMissed(o.entry_status);
  const [followState, setFollowState] = useState<FollowState>("idle");
  const canFollow = ACTIONABLE_CLASSIFICATIONS.has(o.classification);

  async function handleFollow() {
    setFollowState("following");
    try {
      await followSignal(o.decision_v2_snapshot_id);
      setFollowState("followed");
    } catch (err) {
      // Already following this exact signal from an earlier visit --
      // show the same success state rather than an error, since the
      // real underlying fact (the user follows this signal) is true.
      if (err instanceof ApiError && err.code === "signal_already_followed") {
        setFollowState("followed");
      } else {
        setFollowState("error");
      }
    }
  }

  return (
    <div
      className={`flex flex-col gap-bsr-3 rounded-bsr-lg border p-bsr-4 ${
        entryMissed
          ? "border-bsr-gold-500/40 bg-bsr-surface-raised"
          : "border-bsr-border-subtle bg-bsr-surface-overlay"
      }`}
    >
      <div className="flex items-start justify-between">
        <div className="flex flex-col">
          {o.stage1_rank != null ? (
            <span className="bsr-numeric text-xs text-bsr-text-secondary">#{o.stage1_rank}</span>
          ) : null}
          <span className="text-base font-semibold text-bsr-text-primary">
            {o.company_name_ar ?? o.company_name_en}
          </span>
          <span className="bsr-numeric text-sm text-bsr-text-secondary"><SymbolText>{o.symbol}</SymbolText></span>
        </div>
        <DecisionBadge value={o.classification} labelAr={o.classification_label_ar} />
      </div>

      {/* Real-world evidence (owner, 2026-09-15): this exact symbol can
       * be re-quoted as a "fresh" BUY_CANDIDATE with a recalculated,
       * lower entry/stop right after its OWN earlier signal already
       * failed -- this disclosure links the two together instead of
       * letting the new card read as unrelated. See
       * src.market_intelligence.recent_symbol_outcome. Shown before the
       * sector-level badge below: a symbol's own very recent failure is
       * more specific and more urgent than its sector's aggregate rate. */}
      {o.recent_negative_outcome_status != null ? (
        <div className="rounded-bsr-md bg-bsr-market-down/15 px-bsr-3 py-bsr-2 text-xs font-semibold text-bsr-market-down">
          ⚠️ {o.recent_negative_outcome_label_ar}
          {o.recent_negative_outcome_at != null
            ? ` (بتاريخ ${formatArabicDateTime(o.recent_negative_outcome_at)})`
            : ""}
        </div>
      ) : null}

      {/* Real, independent per-sector win-rate disclosure -- shown
       * prominently because confidence_score alone has not been shown
       * to track real accuracy reliably; Smart Radar is the app's
       * de facto home screen, so this must appear here too, not only
       * on "/today". See src.market_intelligence.sector_reliability. */}
      <div
        className={`rounded-bsr-md px-bsr-3 py-bsr-2 text-xs font-semibold ${
          RELIABILITY_COLOR[o.historical_reliability_level]
        }`}
      >
        {o.historical_reliability_label_ar}
        {o.historical_reliability_win_rate_pct != null
          ? ` (${Math.round(o.historical_reliability_win_rate_pct)}% نسبة ربح فعلية على ${o.historical_reliability_sample_size} توصية سابقة)`
          : ""}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-bsr-2 text-xs text-bsr-text-secondary">
        <span>
          صدرت الإشارة: <span className="bsr-numeric">{formatArabicDateTime(o.emitted_at)}</span> ({formatRelativeAgeAr(o.emitted_at)})
        </span>
      </div>

      {/* Production truthfulness fix (2026-08-23): LIVE PRICE != LIVE
          DECISION -- this line reflects the same is_decision_fresh /
          decision_freshness_status RadarStockSection.tsx already shows on
          the stock-detail page, so a stale decision (e.g. a 3-day-old
          BUY_CANDIDATE) is never left unlabeled next to a "بيانات حيّة"
          price badge that could otherwise read as endorsing it. Never
          reuse FRESHNESS_LABELS_AR (price) for this -- see
          src/lib/format/freshness.ts's own warning. */}
      {!o.is_decision_fresh ? (
        <p className="text-xs font-semibold text-bsr-action-sell">{decisionFreshnessLabelAr(o.decision_freshness_status)}</p>
      ) : null}

      {entryMissed ? (
        <div className="rounded-bsr-md border border-bsr-gold-500/50 bg-bsr-gold-500/10 px-bsr-3 py-bsr-2 text-xs font-semibold text-bsr-gold-500">
          {o.entry_status_label_ar ?? "فاتت نقطة الدخول"} — لم تعد فرصة دخول حالية، معروضة هنا للاطلاع فقط.
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-bsr-2 text-sm md:grid-cols-4">
        <div>
          <p className="text-xs text-bsr-text-secondary">درجة بصيرة</p>
          <div className="flex items-center gap-bsr-2">
            <AiStar size="sm" />
            <span className="bsr-numeric font-semibold text-bsr-gold-500">
              {o.basirah_score != null ? `${Math.round(o.basirah_score)}/100` : "--"}
            </span>
          </div>
        </div>
        <div>
          <p className="text-xs text-bsr-text-secondary">درجة الثقة</p>
          <div className="flex items-center gap-bsr-2">
            <span className="bsr-numeric font-semibold text-bsr-teal-500">
              {Math.round(o.confidence_score)}%
            </span>
          </div>
          <ConfidenceBar confidence={o.confidence_score} className="mt-1" />
        </div>
        <div>
          <p className="text-xs text-bsr-text-secondary">المخاطرة</p>
          <p className="font-semibold text-bsr-text-primary">{o.risk_level_label_ar ?? "غير محدد"}</p>
        </div>
        <div>
          <p className="text-xs text-bsr-text-secondary">السعر عند الإشارة</p>
          <p className="bsr-numeric font-semibold text-bsr-text-primary">{priceLabel(o.price_at_signal)}</p>
        </div>
        <div>
          <p className="text-xs text-bsr-text-secondary">حداثة البيانات</p>
          <p className="font-semibold text-bsr-text-primary">
            {FRESHNESS_LABELS_AR[o.data_freshness_status]}
          </p>
        </div>
      </div>

      {/* Product decision (2026-09-18, explicit owner direction): entry/
       * target/stop-loss are the single most important numbers on this
       * card -- "واجهات ... بخط كبير واحترافي" -- so they get their own
       * high-contrast block with much larger numerals, instead of
       * competing visually with secondary metadata (Basirah score,
       * confidence, risk level) above. */}
      <div className="grid grid-cols-2 gap-bsr-3 rounded-bsr-lg bg-bsr-surface-base p-bsr-3 sm:grid-cols-4">
        <div>
          <p className="text-xs font-semibold text-bsr-text-secondary">الدخول</p>
          <p className="bsr-numeric text-xl font-bold leading-tight text-bsr-text-primary">
            {priceLabel(o.entry_zone_low)}–{priceLabel(o.entry_zone_high)}
          </p>
        </div>
        <div>
          <p className="text-xs font-semibold text-bsr-text-secondary">وقف الخسارة</p>
          <p className="bsr-numeric text-xl font-bold leading-tight text-bsr-market-down">{priceLabel(o.stop_loss)}</p>
        </div>
        <div>
          <p className="text-xs font-semibold text-bsr-text-secondary">الهدف الأول</p>
          <p className="bsr-numeric text-xl font-bold leading-tight text-bsr-market-up">{priceLabel(o.target_1)}</p>
        </div>
        {o.target_2 != null ? (
          <div>
            <p className="text-xs font-semibold text-bsr-text-secondary">الهدف الثاني</p>
            <p className="bsr-numeric text-xl font-bold leading-tight text-bsr-market-up">{priceLabel(o.target_2)}</p>
          </div>
        ) : null}
        {o.target_3 != null ? (
          <div>
            <p className="text-xs font-semibold text-bsr-text-secondary">الهدف الثالث</p>
            <p className="bsr-numeric text-xl font-bold leading-tight text-bsr-market-up">{priceLabel(o.target_3)}</p>
          </div>
        ) : null}
      </div>

      {/* "متابعة هذه الإشارة" (product decision 2026-09-18): a one-tap
       * commitment to this exact recommendation, so its real outcome
       * (already tracked by DecisionV2Outcome, never recomputed here)
       * can later be counted as one of the user's own calls on
       * /performance instead of only ever seeing the algorithm's
       * aggregate track record. */}
      {canFollow ? (
        <button
          type="button"
          onClick={handleFollow}
          disabled={followState === "following" || followState === "followed"}
          className={`rounded-bsr-md px-bsr-3 py-bsr-2 text-sm font-semibold transition-colors ${
            followState === "followed"
              ? "bg-bsr-market-up/15 text-bsr-market-up"
              : "bg-bsr-gold-500 text-bsr-navy-950 hover:bg-bsr-gold-400 disabled:opacity-50"
          }`}
        >
          {followState === "followed"
            ? "✓ تتم متابعة هذه الإشارة"
            : followState === "following"
              ? "جارٍ المتابعة..."
              : "متابعة هذه الإشارة"}
        </button>
      ) : null}
      {followState === "error" ? (
        <p role="alert" className="text-xs text-bsr-market-down">
          تعذّرت متابعة هذه الإشارة. حاول مرة أخرى.
        </p>
      ) : null}

      <div className="flex items-center justify-between text-sm">
        <span className="text-bsr-text-secondary">
          العائد/المخاطرة:{" "}
          <span className="bsr-numeric font-semibold text-bsr-text-primary">
            {o.risk_reward_target_1 != null ? `1 : ${o.risk_reward_target_1.toFixed(1)}` : "--"}
          </span>
        </span>
      </div>

      {o.ranking_reason_ar ? (
        <div>
          <p className="text-xs text-bsr-text-secondary">لماذا الآن؟</p>
          <p className="text-sm text-bsr-text-primary">{o.ranking_reason_ar}</p>
        </div>
      ) : null}

      <p className="text-xs text-bsr-text-muted">{o.confidence_disclaimer_ar}</p>

      <a
        href={`/stocks/${o.symbol}`}
        className="mt-bsr-1 rounded-bsr-md border border-bsr-border-subtle px-bsr-3 py-bsr-2 text-center text-sm font-semibold text-bsr-text-primary transition-colors hover:border-bsr-gold-500/40"
      >
        التفاصيل
      </a>
    </div>
  );
}
