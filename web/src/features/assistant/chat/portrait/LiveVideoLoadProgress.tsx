import { useEffect, useRef, useState } from 'react';
import { type LoadPlan, finishLoad, loadFraction, moveTo, secondsLeft, stepLabel } from './loadProgress';

const TICK_MS = 250;

/**
 * A load's plan for its bar. Kept in a ref as well, so a step is moved on (and its time recorded) once, outside a
 * render, and the load's async steps read the plan as it is now.
 */
export function useLoadPlan() {
  const planRef = useRef<LoadPlan | null>(null);
  const mounted = useRef(true);
  const [plan, setPlanState] = useState<LoadPlan | null>(null);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const setPlan = (next: LoadPlan | null) => {
    planRef.current = next;
    if (mounted.current) setPlanState(next);
  };
  const advance = (id: string) => {
    if (planRef.current) setPlan(moveTo(planRef.current, id, Date.now()));
  };
  const endPlan = () => {
    if (planRef.current) finishLoad(planRef.current, Date.now());
    setPlan(null);
  };
  return { plan, planRef, setPlan, advance, endPlan };
}

/**
 * The bar under "Load live video" while it loads: the step under way, how many there are, and about how long is
 * left. Without a plan (a load this button did not start, such as a call's) it slides, saying only that it loads.
 */
export function LiveVideoLoadProgress({ plan }: { plan: LoadPlan | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), TICK_MS);
    return () => window.clearInterval(timer);
  }, []);

  const step = plan?.steps[plan.index];
  if (!plan || !step) {
    return (
      <div className="assistant-live-video-progress is-indeterminate">
        <div className="assistant-live-video-progress-track" role="progressbar" aria-label="Loading live video">
          <span className="assistant-live-video-progress-fill" />
        </div>
      </div>
    );
  }
  const percent = Math.round(loadFraction(plan, Math.max(now, plan.since)) * 100);
  const left = secondsLeft(plan, Math.max(now, plan.since));
  const count = plan.steps.length > 1 ? `Step ${plan.index + 1} of ${plan.steps.length}` : '';
  const eta = left === null ? 'almost there' : `about ${left} s left`;
  return (
    <div className="assistant-live-video-progress">
      <div
        className="assistant-live-video-progress-track"
        role="progressbar"
        aria-label="Loading live video"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-valuetext={`${stepLabel(step)} ${percent}%`}
      >
        <span className="assistant-live-video-progress-fill" style={{ width: `${percent}%` }} />
      </div>
      <small className="assistant-live-video-progress-caption">
        <span>{stepLabel(step)}</span>
        <span>{count ? `${count} · ${eta}` : eta}</span>
      </small>
    </div>
  );
}
