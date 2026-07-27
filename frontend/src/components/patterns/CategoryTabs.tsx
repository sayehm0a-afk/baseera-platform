interface CategoryTabsProps {
  categories: string[];
  labels: Record<string, string>;
  active: string;
  onChange: (category: string) => void;
}

/** The one shared horizontal category-pill tab bar (Scan/Watchlist
 * reuse this rather than each drawing its own). */
export function CategoryTabs({
  categories,
  labels,
  active,
  onChange,
}: CategoryTabsProps) {
  return (
    <div className="flex gap-bsr-2 overflow-x-auto pb-bsr-1">
      {categories.map((category) => {
        const isActive = category === active;
        return (
          <button
            key={category}
            type="button"
            onClick={() => onChange(category)}
            className={`shrink-0 rounded-bsr-full px-bsr-4 py-bsr-2 text-sm whitespace-nowrap transition-colors ${
              isActive
                ? "bg-bsr-gold-500 text-bsr-navy-950 font-semibold"
                : "bg-bsr-surface-overlay text-bsr-text-secondary hover:text-bsr-text-primary"
            }`}
          >
            {labels[category] ?? category}
          </button>
        );
      })}
    </div>
  );
}
