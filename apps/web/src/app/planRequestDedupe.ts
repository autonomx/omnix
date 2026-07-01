export interface PendingPlanRequest {
  id: string;
  objective: string;
}

export function normalizePlanObjective(value: string): string {
  return value.trim().replace(/\s+/g, ' ').toLowerCase();
}

export function hasPendingPlanRequest(pending: PendingPlanRequest[], objective: string): boolean {
  const normalized = normalizePlanObjective(objective);
  return pending.some((item) => normalizePlanObjective(item.objective) === normalized);
}
