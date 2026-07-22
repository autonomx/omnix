import os
import subprocess
from pathlib import Path

branch = os.environ.get("GITHUB_HEAD_REF", "").strip()
if not branch:
    raise SystemExit("GITHUB_HEAD_REF is missing")
subprocess.run(
    [
        "git",
        "fetch",
        "origin",
        f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
    ],
    check=True,
)
subprocess.run(["git", "checkout", "-B", branch, f"origin/{branch}"], check=True)

controller_path = Path("apps/web/src/features/assistant-workspace/live-voice-controller.ts")
workflow_path = Path(".github/workflows/live-chat-hardening.yml")
script_path = Path(".github/live-followup-patch.py")

controller = controller_path.read_text(encoding="utf-8")

old_import = "import type { AcceptedVoiceFinal, LiveFinalRoutingResult } from './live-accepted-final';\n"
new_import = old_import + "import { acceptedFinalSuppressionReason } from './live-accepted-final-routing';\n"
if "acceptedFinalSuppressionReason" not in controller:
    if old_import not in controller:
        raise SystemExit("accepted-final import anchor missing")
    controller = controller.replace(old_import, new_import, 1)

old_identity = """  const receivedAt = performance.now();
  const overlapIntent = session.overlapIntent;
  const interruptionDispatched = session.interruptionDispatched;
  const continuation = session.finalizationBuffer.drain();
"""
new_identity = """  const receivedAt = performance.now();
  const partialOverlapIntent = session.overlapIntent;
  const finalOverlapAssessment = partialOverlapIntent === 'uncertain'
    ? classifyOverlap(final.text, currentAssistantSpeechText())
    : null;
  const overlapIntent = finalOverlapAssessment?.intent ?? partialOverlapIntent;
  const interruptionDispatched = session.interruptionDispatched;
  const suppressionReason = acceptedFinalSuppressionReason(final.text, overlapIntent);
  const continuation = session.finalizationBuffer.drain();
"""
if old_identity in controller:
    controller = controller.replace(old_identity, new_identity, 1)
elif new_identity not in controller:
    raise SystemExit("accepted-final identity anchor missing")

old_diagnostic = """    transcript_chars: final.text.trim().length,
    stt_finalize_ms: session.sttFinalRequestedAt === null ? undefined : Math.round(receivedAt - session.sttFinalRequestedAt),
  }, 'live_voice_controller');
  const suppressTurn = Boolean(
    overlapIntent === 'hard_stop'
    || overlapIntent === 'backchannel'
    || overlapIntent === 'noise'
    || (overlapIntent === 'uncertain' && !interruptionDispatched),
  );
  resetTurnState(session);
  try {
    if (suppressTurn || !final.text.trim()) {
"""
new_diagnostic = """    transcript_chars: final.text.trim().length,
    stt_finalize_ms: session.sttFinalRequestedAt === null ? undefined : Math.round(receivedAt - session.sttFinalRequestedAt),
    overlap_intent: overlapIntent,
    overlap_confidence: finalOverlapAssessment?.confidence,
    overlap_reason: finalOverlapAssessment?.reason,
    interruption_dispatched: interruptionDispatched,
  }, 'live_voice_controller');
  resetTurnState(session);
  try {
    if (suppressionReason) {
"""
if old_diagnostic in controller:
    controller = controller.replace(old_diagnostic, new_diagnostic, 1)
elif new_diagnostic not in controller:
    raise SystemExit("accepted-final suppression anchor missing")

old_reason = """        suppression_reason: suppressTurn ? overlapIntent ?? 'suppressed_overlap' : 'empty_transcript',
"""
new_reason = """        suppression_reason: suppressionReason,
        overlap_intent: overlapIntent,
        overlap_confidence: finalOverlapAssessment?.confidence,
        overlap_reason: finalOverlapAssessment?.reason,
"""
if old_reason in controller:
    controller = controller.replace(old_reason, new_reason, 1)
elif new_reason not in controller:
    raise SystemExit("suppression diagnostic anchor missing")

old_started = """      source_sequence: final.sourceSequence,
      capture_epoch: final.captureEpoch,
    }, 'live_voice_controller');
"""
new_started = """      source_sequence: final.sourceSequence,
      capture_epoch: final.captureEpoch,
      overlap_intent: overlapIntent,
      overlap_confidence: finalOverlapAssessment?.confidence,
      overlap_reason: finalOverlapAssessment?.reason,
      interruption_dispatched: interruptionDispatched,
    }, 'live_voice_controller');
"""
if old_started in controller:
    controller = controller.replace(old_started, new_started, 1)
elif new_started not in controller:
    raise SystemExit("coordination-start diagnostic anchor missing")

controller_path.write_text(controller, encoding="utf-8")

workflow = workflow_path.read_text(encoding="utf-8")
start = "      # BEGIN ONE-TIME LIVE FOLLOWUP\n"
end = "      # END ONE-TIME LIVE FOLLOWUP\n"
if start not in workflow or end not in workflow:
    raise SystemExit("one-time workflow markers missing")
head, remainder = workflow.split(start, 1)
_, tail = remainder.split(end, 1)
workflow = head + tail
workflow = workflow.replace("permissions:\n  contents: write\n", "permissions:\n  contents: read\n", 1)
workflow_path.write_text(workflow, encoding="utf-8")
script_path.unlink()
