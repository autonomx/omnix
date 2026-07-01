export function StaleProposalWarning({ stale }: { stale: boolean }) {
  if (!stale) {
    return null;
  }
  return (
    <section aria-label="Stale proposal warning">
      <h3>Stale proposal</h3>
      <p>This proposal no longer matches the current input. Request a fresh review before use.</p>
    </section>
  );
}
