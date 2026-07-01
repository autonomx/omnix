import { createReviewChecklistState } from './reviewChecklistState';
import type { OmnixModeId } from './omnixModeIds';

export function ReviewChecklist({ mode, userReviewed = false }: { mode: OmnixModeId; userReviewed?: boolean }) {
  const items = createReviewChecklistState(mode, userReviewed);

  return (
    <section aria-label="Review checklist">
      <h3>Review checklist</h3>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            {item.checked ? '✓' : '○'} {item.label}
          </li>
        ))}
      </ul>
    </section>
  );
}
