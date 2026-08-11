import type { PersonalOpportunity } from "@/lib/api/types";

interface PersonalOpportunityCardProps {
  opportunity: PersonalOpportunity;
}

const DECISION_COLOR: Record<string, string> = {
  شراء: "bg-bsr-market-up/15 text-bsr-market-up",
  انتظار: "bg-bsr-gold-500/15 text-bsr-gold-500",
  تجاهل: "bg-bsr-market-down/15 text-bsr-market-down",
};

function priceLabel(value: number | null): string {
  return value == null ? "--" : value.toFixed(2);
}

/** One "أفضل فرص المضاربة الآن" card -- every field is read straight
 * from GET /api/v1/market/personal/top-opportunities, never
 * recomputed here (see src.market_intelligence.personal_scan). */
export function PersonalOpportunityCard({ opportunity: o }: PersonalOpportunityCardProps) {
  return (
    <div className="flex flex-col gap-bsr-3 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-overlay p-bsr-4">
      <div className="flex items-start justify-between">
        <div className="flex flex-col">
          <span className="text-xs text-bsr-text-secondary">#{o.rank}</span>
          <span className="text-base font-semibold text-bsr-text-primary">
            {o.company_name_ar ?? o.company_name_en}
          </span>
          <span className="bsr-numeric text-sm text-bsr-text-secondary">
            {o.symbol}
            {o.sector_ar ? ` · ${o.sector_ar}` : ""}
          </span>
        </div>
        <span
          className={`rounded-bsr-md px-bsr-2 py-1 text-sm font-semibold ${
            DECISION_COLOR[o.simple_decision_ar] ?? "bg-bsr-surface-raised text-bsr-text-primary"
          }`}
        >
          قرار بصيرة: {o.simple_decision_ar}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-bsr-2 text-sm md:grid-cols-4">
        <div>
          <p className="text-xs text-bsr-text-secondary">الثقة</p>
          <p className="bsr-numeric font-semibold text-bsr-teal-500">{Math.round(o.confidence_score)}%</p>
        </div>
        <div>
          <p className="text-xs text-bsr-text-secondary">المخاطرة</p>
          <p className="font-semibold text-bsr-text-primary">{o.risk_level_label_ar ?? "غير محدد"}</p>
        </div>
        <div>
          <p className="text-xs text-bsr-text-secondary">السعر الحالي</p>
          <p className="bsr-numeric font-semibold text-bsr-text-primary">{priceLabel(o.current_price)}</p>
        </div>
        <div>
          <p className="text-xs text-bsr-text-secondary">حالة السوق</p>
          <p className="font-semibold text-bsr-text-primary">{o.market_status}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-bsr-2 text-sm">
        <div>
          <p className="text-xs text-bsr-text-secondary">الدخول</p>
          <p className="bsr-numeric font-semibold text-bsr-text-primary">
            {priceLabel(o.entry_zone_low)} – {priceLabel(o.entry_zone_high)}
          </p>
          {o.entry_status_label_ar ? (
            <p className={`text-xs ${o.is_entry_late ? "text-bsr-market-down" : "text-bsr-text-secondary"}`}>
              {o.entry_status_label_ar}
            </p>
          ) : null}
        </div>
        <div>
          <p className="text-xs text-bsr-text-secondary">وقف الخسارة</p>
          <p className="bsr-numeric font-semibold text-bsr-market-down">{priceLabel(o.stop_loss)}</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-bsr-2 text-sm">
        <div>
          <p className="text-xs text-bsr-text-secondary">الهدف الأول</p>
          <p className="bsr-numeric font-semibold text-bsr-market-up">{priceLabel(o.target_1)}</p>
        </div>
        <div>
          <p className="text-xs text-bsr-text-secondary">الهدف الثاني</p>
          <p className="bsr-numeric font-semibold text-bsr-market-up">{priceLabel(o.target_2)}</p>
        </div>
        <div>
          <p className="text-xs text-bsr-text-secondary">الهدف الثالث</p>
          <p className="bsr-numeric font-semibold text-bsr-market-up">{priceLabel(o.target_3)}</p>
        </div>
      </div>

      <div className="flex items-center justify-between text-sm">
        <span className="text-bsr-text-secondary">
          العائد/المخاطرة:{" "}
          <span className="bsr-numeric font-semibold text-bsr-text-primary">
            {o.risk_reward_target_1 != null ? `1 : ${o.risk_reward_target_1.toFixed(1)}` : "--"}
          </span>
        </span>
        <span className="text-bsr-text-secondary">
          المدة المتوقعة:{" "}
          <span className="font-semibold text-bsr-text-primary">
            {o.expected_holding_period_label_ar ?? "غير محدد"}
          </span>
        </span>
      </div>

      {o.trend_direction_ar || o.trend_strength_label_ar || o.liquidity_quality_ar ? (
        <div className="flex flex-wrap gap-bsr-2 text-xs text-bsr-text-secondary">
          {o.trend_direction_ar ? <span>الاتجاه: {o.trend_direction_ar}</span> : null}
          {o.trend_strength_label_ar ? <span>· الزخم: {o.trend_strength_label_ar}</span> : null}
          {o.liquidity_quality_ar ? <span>· السيولة: {o.liquidity_quality_ar}</span> : null}
        </div>
      ) : null}

      {o.decision_summary_ar ? (
        <div>
          <p className="text-xs text-bsr-text-secondary">سبب الترشيح</p>
          <p className="text-sm text-bsr-text-primary">{o.decision_summary_ar}</p>
        </div>
      ) : null}

      {o.entry_confirmation_conditions_ar.length > 0 ? (
        <div>
          <p className="text-xs text-bsr-text-secondary">أهم إشارات التأكيد</p>
          <ul className="list-inside list-disc text-sm text-bsr-text-primary">
            {o.entry_confirmation_conditions_ar.slice(0, 3).map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {o.invalidation_conditions.length > 0 ? (
        <div>
          <p className="text-xs text-bsr-text-secondary">أهم سبب قد يُبطل الصفقة</p>
          <p className="text-sm text-bsr-market-down">{o.invalidation_conditions[0]}</p>
        </div>
      ) : null}

      <a
        href={`/stocks/${o.symbol}`}
        className="mt-bsr-1 rounded-bsr-md border border-bsr-border-subtle px-bsr-3 py-bsr-2 text-center text-sm font-semibold text-bsr-text-primary transition-colors hover:border-bsr-gold-500/40"
      >
        التفاصيل
      </a>
    </div>
  );
}
