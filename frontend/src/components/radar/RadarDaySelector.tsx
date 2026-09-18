/** Product decision 2026-09-18: lets the user browse a real past day's
 * Smart Radar picks (see GET /api/v1/radar/history), not only today's.
 * Days are computed in Tadawul-local time (Asia/Riyadh, UTC+3, no DST
 * -- same offset, safe to compute via the IANA zone) so "اليوم" always
 * matches the same trading day the rest of the app already reasons
 * about (see src/market_intelligence/trading_calendar.py's own
 * TADAWUL_TIMEZONE on the backend). */

const TADAWUL_IANA_ZONE = "Asia/Riyadh";
const DAYS_SHOWN = 7;

export interface RadarDayOption {
  /** "YYYY-MM-DD", Tadawul-local. */
  date: string;
  /** Day-of-month, Tadawul-local (real Western digits, matches
   * bsr-numeric convention). */
  dayOfMonth: string;
  /** Short Arabic weekday label (الأحد/الإثنين/...). */
  weekdayLabelAr: string;
  isToday: boolean;
}

function tadawulDateString(d: Date): string {
  // en-CA gives YYYY-MM-DD directly -- no manual zero-padding/reformatting.
  return new Intl.DateTimeFormat("en-CA", { timeZone: TADAWUL_IANA_ZONE }).format(d);
}

export function buildRadarDayOptions(now: Date = new Date()): RadarDayOption[] {
  const today = tadawulDateString(now);
  const options: RadarDayOption[] = [];
  for (let i = DAYS_SHOWN - 1; i >= 0; i--) {
    const d = new Date(now.getTime() - i * 24 * 60 * 60 * 1000);
    const date = tadawulDateString(d);
    options.push({
      date,
      dayOfMonth: new Intl.DateTimeFormat("en-US", { day: "numeric", timeZone: TADAWUL_IANA_ZONE }).format(d),
      weekdayLabelAr: new Intl.DateTimeFormat("ar-SA", { weekday: "short", timeZone: TADAWUL_IANA_ZONE }).format(d),
      isToday: date === today,
    });
  }
  return options;
}

interface RadarDaySelectorProps {
  value: string;
  onChange: (date: string) => void;
  options?: RadarDayOption[];
}

export function RadarDaySelector({ value, onChange, options }: RadarDaySelectorProps) {
  const days = options ?? buildRadarDayOptions();
  return (
    <div className="flex gap-bsr-2 overflow-x-auto" role="tablist" aria-label="اختر يوم الرادار">
      {days.map((day) => (
        <button
          key={day.date}
          type="button"
          role="tab"
          aria-selected={value === day.date}
          onClick={() => onChange(day.date)}
          className={`flex shrink-0 flex-col items-center gap-0.5 rounded-bsr-lg px-bsr-3 py-bsr-2 text-sm transition-colors ${
            value === day.date
              ? "bg-bsr-gold-500 text-bsr-navy-950 font-semibold"
              : "bg-bsr-surface-overlay text-bsr-text-secondary hover:text-bsr-text-primary"
          }`}
        >
          <span className="text-xs">{day.isToday ? "اليوم" : day.weekdayLabelAr}</span>
          <span className="bsr-numeric">{day.dayOfMonth}</span>
        </button>
      ))}
    </div>
  );
}
