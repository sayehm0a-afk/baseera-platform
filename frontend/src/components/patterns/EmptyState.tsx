interface EmptyStateProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
}

/** The one shared empty-state pattern every screen reuses (UI Spec
 * Global Invariants §0) -- a screen rendering its own empty state is
 * defective by definition. */
export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-bsr-3 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised px-bsr-6 py-bsr-12 text-center">
      <p className="text-base font-medium text-bsr-text-primary">{title}</p>
      {description ? (
        <p className="max-w-sm text-sm text-bsr-text-secondary">
          {description}
        </p>
      ) : null}
      {action}
    </div>
  );
}
