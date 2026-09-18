"use client";

import { FollowedSignalsPanel } from "@/components/watchlist/FollowedSignalsPanel";
import { MyWatchlistPanel } from "@/components/watchlist/MyWatchlistPanel";
import { PersonalPerformancePanel } from "@/components/watchlist/PersonalPerformancePanel";
import { WatchlistNewsAlertsSection } from "@/components/watchlist/WatchlistNewsAlertsSection";

// 2026-09-16 simplification: this screen used to also offer 9 market-
// wide "browse by strategy" tabs (momentum/investment/swing/high_risk/
// dividend/recovery/breakout/oversold/overbought), each an auto-bucket
// of every stock the last scan covered. With the real scan currently
// covering only ~15 of ~250+ eligible symbols (SAHMK's Starter-plan
// daily quota), 7-8 of those 9 tabs were empty on a typical day --
// confusing for exactly the beginner trader this product targets, and
// redundant with what /radar (the actual "today's opportunities" home,
// see its own "de facto home" framing in nav-items.ts) already shows
// more honestly, including its scan-coverage transparency banner. This
// page now does only what "المتابعة" (follow-up) should mean: the
// user's OWN tracked stocks, plus real-time alerts on them -- never a
// second, thinner copy of Radar's job.
export default function WatchlistPage() {
  return (
    <div className="flex flex-col gap-bsr-4">
      <h1 className="text-lg font-semibold text-bsr-text-primary">المتابعة</h1>

      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-2 md:p-bsr-4">
        <MyWatchlistPanel />
      </section>

      {/* "متابعة هذه الإشارة" (product decision 2026-09-18): the same
       * "متابعة" (follow-up) concept as the symbol watchlist above,
       * just for specific followed BUY recommendations instead of
       * whole symbols -- kept on this existing screen rather than a
       * fifth primary nav item, per the RADAR-C simplification mandate
       * (see nav-items.ts). */}
      <section className="flex flex-col gap-bsr-3 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-2 md:p-bsr-4">
        <h2 className="text-base font-semibold text-bsr-text-primary">أداؤك مقابل أداء الخوارزمية</h2>
        <PersonalPerformancePanel />
      </section>

      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-2 md:p-bsr-4">
        <h2 className="mb-bsr-2 px-bsr-2 text-base font-semibold text-bsr-text-primary">الإشارات التي تتابعها</h2>
        <FollowedSignalsPanel />
      </section>

      <WatchlistNewsAlertsSection />
    </div>
  );
}
