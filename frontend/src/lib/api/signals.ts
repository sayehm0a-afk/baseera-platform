import { apiFetch } from "./client";
import type { FollowedSignal, FollowedSignalList, PersonalPerformanceComparison } from "./signals-types";

/** Every function here is a direct, unmodified call to an existing
 * /api/v1/signals/* route (src/api/routes/signals.py) -- "متابعة هذه
 * الإشارة" (product decision 2026-09-18). */

export function followSignal(decisionV2SnapshotId: number): Promise<FollowedSignal> {
  return apiFetch<FollowedSignal>("/api/v1/signals/follow", {
    method: "POST",
    body: JSON.stringify({ decision_v2_snapshot_id: decisionV2SnapshotId }),
  });
}

export function unfollowSignal(decisionV2SnapshotId: number): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/api/v1/signals/${decisionV2SnapshotId}`, {
    method: "DELETE",
  });
}

export function getFollowedSignals(): Promise<FollowedSignalList> {
  return apiFetch<FollowedSignalList>("/api/v1/signals/followed");
}

export function getPersonalPerformance(): Promise<PersonalPerformanceComparison> {
  return apiFetch<PersonalPerformanceComparison>("/api/v1/signals/performance");
}
