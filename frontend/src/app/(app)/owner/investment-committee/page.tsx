"use client";

import { useEffect, useState } from "react";
import { RequireStaff } from "@/components/auth/RequireStaff";
import { OwnerNav } from "@/components/owner/OwnerNav";
import {
  AGENT_ROLE_LABELS_AR,
  AGENT_STANCE_LABELS_AR,
  FINAL_DECISION_LABELS_AR,
  stanceColorClass,
} from "@/components/committee/committee-labels";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { ApiError } from "@/lib/api/client";
import { getCommitteeSession, getCommitteeStats, listCommitteeSessions } from "@/lib/api/admin";
import type { CommitteeSessionDetail, CommitteeSessionSummary, CommitteeStats } from "@/lib/api/admin-types";

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
      <h2 className="mb-bsr-2 text-base font-semibold text-bsr-text-primary">{title}</h2>
      {children}
    </section>
  );
}

/** A minimal "decision graph": one horizontal bar per agent, signed by
 * its real weighted-vote contribution (see consensus.py's
 * `_signed_vote`) -- bullish bars extend right in green, bearish bars
 * extend left in red, a zero vote (NEUTRAL/UNAVAILABLE) renders as a
 * dot at center. No charting library: the bar width is a direct,
 * proportional read of the real number, nothing estimated. */
function DecisionGraph({ weightedVotes }: { weightedVotes: Record<string, number> }) {
  const entries = Object.entries(weightedVotes);
  if (entries.length === 0) return null;
  const maxAbs = Math.max(...entries.map(([, v]) => Math.abs(v)), 0.01);

  return (
    <div className="flex flex-col gap-bsr-1">
      {entries.map(([agentName, vote]) => {
        const widthPct = (Math.abs(vote) / maxAbs) * 50;
        return (
          <div key={agentName} className="flex items-center gap-bsr-2">
            <span className="w-32 shrink-0 truncate text-[11px] text-bsr-text-secondary">{agentName}</span>
            <div className="relative h-3 flex-1 rounded-bsr-sm bg-bsr-surface-base">
              <div className="absolute inset-y-0 start-1/2 w-px bg-bsr-border-subtle" />
              {vote > 0 ? (
                <div
                  className="absolute inset-y-0 start-1/2 rounded-bsr-sm bg-bsr-action-buy"
                  style={{ width: `${widthPct}%` }}
                />
              ) : vote < 0 ? (
                <div
                  className="absolute inset-y-0 end-1/2 rounded-bsr-sm bg-bsr-action-sell"
                  style={{ width: `${widthPct}%` }}
                />
              ) : null}
            </div>
            <span className="bsr-numeric w-12 shrink-0 text-end text-[11px] text-bsr-text-tertiary">
              {vote.toFixed(2)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function SessionDetailView({ detail }: { detail: CommitteeSessionDetail }) {
  return (
    <div className="flex flex-col gap-bsr-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-bsr-text-primary">
            {detail.symbol} — {detail.company_name_ar ?? ""}
          </p>
          <p className="text-xs text-bsr-text-secondary">{detail.decision_label_ar}</p>
        </div>
        <span className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
          {FINAL_DECISION_LABELS_AR[detail.final_decision] ?? detail.final_decision} (
          {Math.round(detail.final_confidence)}%)
        </span>
      </div>

      <div className="grid grid-cols-2 gap-bsr-2 sm:grid-cols-4">
        <div>
          <p className="text-[11px] text-bsr-text-secondary">التوافق</p>
          <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
            {Math.round(detail.agreement_pct)}%
          </p>
        </div>
        <div>
          <p className="text-[11px] text-bsr-text-secondary">الاختلاف</p>
          <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
            {Math.round(detail.disagreement_pct)}%
          </p>
        </div>
        <div>
          <p className="text-[11px] text-bsr-text-secondary">درجة الاختلاف</p>
          <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
            {detail.disagreement_score.toFixed(1)}
          </p>
        </div>
        <div>
          <p className="text-[11px] text-bsr-text-secondary">المشاركون / الاتجاهيون</p>
          <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
            {detail.participant_count} / {detail.directional_count}
          </p>
        </div>
      </div>

      {detail.consensus_reasoning_ar ? (
        <p className="rounded-bsr-md bg-bsr-surface-base p-bsr-2 text-xs text-bsr-text-secondary">
          {detail.consensus_reasoning_ar}
        </p>
      ) : null}

      <div>
        <p className="mb-bsr-1 text-xs font-semibold text-bsr-text-primary">مخطط القرار (الأصوات المرجحة)</p>
        <DecisionGraph weightedVotes={detail.weighted_votes} />
      </div>

      <div>
        <p className="mb-bsr-2 text-xs font-semibold text-bsr-text-primary">بطاقات الوكلاء</p>
        <div className="grid grid-cols-1 gap-bsr-2 sm:grid-cols-2">
          {detail.opinions.map((opinion) => (
            <div
              key={opinion.agent_name}
              className="rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base p-bsr-2"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-bsr-text-primary">{opinion.agent_name}</span>
                <span className={`text-xs font-semibold ${stanceColorClass(opinion.stance)}`}>
                  {AGENT_STANCE_LABELS_AR[opinion.stance]}
                </span>
              </div>
              <p className="text-[11px] text-bsr-text-tertiary">
                {AGENT_ROLE_LABELS_AR[opinion.role] ?? opinion.role} · ثقة {Math.round(opinion.confidence)}%
              </p>
              <p className="mt-1 text-[11px] text-bsr-text-secondary">{opinion.reasoning}</p>
              {opinion.evidence.length > 0 ? (
                <ul className="mt-1 flex flex-col gap-0.5 text-[11px] text-bsr-text-secondary">
                  {opinion.evidence.map((item, i) => (
                    <li key={i}>• {item}</li>
                  ))}
                </ul>
              ) : null}
              {opinion.rejection_reasons.length > 0 ? (
                <p className="mt-1 text-[11px] text-bsr-action-sell">{opinion.rejection_reasons.join("، ")}</p>
              ) : null}
            </div>
          ))}
        </div>
      </div>

      {detail.rejected_alternatives.length > 0 ? (
        <div>
          <p className="text-xs font-semibold text-bsr-text-primary">لماذا رُفضت الآراء البديلة؟</p>
          <ul className="mt-1 flex flex-col gap-1 text-[11px] text-bsr-text-secondary">
            {detail.rejected_alternatives.map((alt) => (
              <li key={alt.agent_name}>
                <span className="font-semibold text-bsr-text-primary">{alt.agent_name}</span>{" "}
                <span className={stanceColorClass(alt.stance)}>({AGENT_STANCE_LABELS_AR[alt.stance]})</span>:{" "}
                {alt.rejection_reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function InvestmentCommitteePageInner() {
  const [stats, setStats] = useState<CommitteeStats | null>(null);
  const [sessions, setSessions] = useState<CommitteeSessionSummary[] | null>(null);
  const [symbolFilter, setSymbolFilter] = useState("");
  const [selected, setSelected] = useState<CommitteeSessionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getCommitteeStats(72), listCommitteeSessions(undefined, 30)])
      .then(([statsData, sessionsData]) => {
        setStats(statsData);
        setSessions(sessionsData.sessions);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "تعذّر تحميل بيانات لجنة الاستثمار."))
      .finally(() => setLoading(false));
  }, []);

  function refreshSessions(symbol: string) {
    setLoading(true);
    listCommitteeSessions(symbol || undefined, 30)
      .then((data) => setSessions(data.sessions))
      .catch((err) => setError(err instanceof ApiError ? err.message : "تعذّر تحميل الجلسات."))
      .finally(() => setLoading(false));
  }

  function openSession(sessionId: number) {
    setSelected(null);
    getCommitteeSession(sessionId)
      .then((detail) => setSelected(detail))
      .catch((err) => setError(err instanceof ApiError ? err.message : "تعذّر تحميل تفاصيل الجلسة."));
  }

  if (loading && sessions === null) {
    return (
      <div className="flex flex-col gap-bsr-4">
        <OwnerNav />
        <LoadingScreen />
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex flex-col gap-bsr-4">
        <OwnerNav />
        <EmptyState title="تعذّر تحميل لجنة الاستثمار" description={error} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-bsr-4">
      <OwnerNav />
      <h1 className="text-lg font-semibold text-bsr-text-primary">لجنة الاستثمار متعددة الوكلاء</h1>
      <p className="text-sm text-bsr-text-secondary">
        كل قرار حي يمر عبر ثمانية وكلاء تحليل مستقلين ثم محرك توافق مرجح — هذه اللوحة تعرض السجل الحقيقي لتلك
        الجلسات.
      </p>

      {stats ? (
        <Card title={`إحصاءات آخر ${stats.window_hours} ساعة`}>
          <div className="grid grid-cols-2 gap-bsr-2 sm:grid-cols-4">
            <div>
              <p className="text-[11px] text-bsr-text-secondary">عدد الجلسات</p>
              <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">{stats.total_sessions}</p>
            </div>
            <div>
              <p className="text-[11px] text-bsr-text-secondary">متوسط التوافق</p>
              <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
                {stats.average_agreement_pct !== null ? `${stats.average_agreement_pct.toFixed(1)}%` : "—"}
              </p>
            </div>
            <div>
              <p className="text-[11px] text-bsr-text-secondary">متوسط درجة الاختلاف</p>
              <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
                {stats.average_disagreement_score !== null ? stats.average_disagreement_score.toFixed(1) : "—"}
              </p>
            </div>
            <div>
              <p className="text-[11px] text-bsr-text-secondary">توزيع القرار النهائي</p>
              <p className="text-xs text-bsr-text-primary">
                {Object.entries(stats.final_decision_distribution)
                  .map(([k, v]) => `${FINAL_DECISION_LABELS_AR[k] ?? k}: ${v}`)
                  .join("، ") || "—"}
              </p>
            </div>
          </div>
        </Card>
      ) : null}

      <Card title="الجدول الزمني للجلسات">
        <div className="mb-bsr-2 flex gap-bsr-2">
          <input
            type="text"
            value={symbolFilter}
            onChange={(e) => setSymbolFilter(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && refreshSessions(symbolFilter)}
            placeholder="تصفية حسب رمز السهم"
            className="rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-2 py-1 text-sm text-bsr-text-primary"
          />
          <button
            type="button"
            onClick={() => refreshSessions(symbolFilter)}
            className="rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-raised px-bsr-3 py-1 text-xs font-semibold text-bsr-text-secondary"
          >
            بحث
          </button>
        </div>

        {sessions === null || sessions.length === 0 ? (
          <p className="text-sm text-bsr-text-muted">لا توجد جلسات لجنة استثمار مسجّلة بعد.</p>
        ) : (
          <div className="flex flex-col gap-bsr-1">
            {sessions.map((session) => (
              <button
                key={session.session_id}
                type="button"
                onClick={() => openSession(session.session_id)}
                className={`flex items-center justify-between rounded-bsr-md border p-bsr-2 text-start ${
                  selected?.session_id === session.session_id
                    ? "border-bsr-gold-500 bg-bsr-surface-overlay"
                    : "border-bsr-border-subtle bg-bsr-surface-base"
                }`}
              >
                <div>
                  <span className="text-sm font-semibold text-bsr-text-primary">{session.symbol}</span>{" "}
                  <span className="text-xs text-bsr-text-secondary">{session.company_name_ar ?? ""}</span>
                  <p className="text-[11px] text-bsr-text-tertiary">
                    الأكثر تفاؤلاً: {session.most_optimistic_agent ?? "—"} · الأكثر تحفظاً:{" "}
                    {session.most_conservative_agent ?? "—"}
                  </p>
                </div>
                <div className="text-end">
                  <span className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
                    {FINAL_DECISION_LABELS_AR[session.final_decision] ?? session.final_decision}
                  </span>
                  <p className="text-[11px] text-bsr-text-tertiary">
                    توافق {Math.round(session.agreement_pct)}%
                  </p>
                </div>
              </button>
            ))}
          </div>
        )}
      </Card>

      {selected ? (
        <Card title="تفاصيل الجلسة">
          <SessionDetailView detail={selected} />
        </Card>
      ) : null}
    </div>
  );
}

export default function InvestmentCommitteePage() {
  return (
    <RequireStaff>
      <InvestmentCommitteePageInner />
    </RequireStaff>
  );
}
