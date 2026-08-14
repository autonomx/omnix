import { createRiskListState, createStepListState } from './stepsRisksDisplayState';

export function StepsRisksReviewList({ steps, risks }: { steps?: unknown; risks?: unknown }) {
  const stepItems = createStepListState(steps);
  const riskItems = createRiskListState(risks);

  return (
    <section aria-label="Proposal steps and risks">
      <h3>Proposal review</h3>
      <h4>Steps</h4>
      <ul>
        {stepItems.map((item) => (
          <li key={item.id}>
            <strong>{item.title}</strong> — {item.detail} ({item.badge})
          </li>
        ))}
      </ul>
      <h4>Risks</h4>
      <ul>
        {riskItems.map((item) => (
          <li key={item.id}>
            <strong>{item.title}</strong> — {item.detail} ({item.badge})
          </li>
        ))}
      </ul>
      <p>Review required before any use.</p>
    </section>
  );
}
