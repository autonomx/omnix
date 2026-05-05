from __future__ import annotations

import html
import json
import zipfile
from pathlib import Path
from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def render_autoplay_html(transcript: List[Dict[str, Any]], summary: Dict[str, Any]) -> str:
    rows = []
    for row in transcript:
        context = _safe_dict(row.get("player_action_context"))
        suggested = context.get("suggested_actions") if isinstance(context.get("suggested_actions"), list) else []
        rows.append(
            f"""
            <section class="turn">
              <h2>Turn {html.escape(str(row.get("turn_index")))} </h2>
              <div><strong>Player action:</strong> {html.escape(_safe_str(row.get("player_action")))}</div>
              <div><strong>Reason:</strong> {html.escape(_safe_str(row.get("selected_action_reason")))}</div>
              <div><strong>Narration:</strong><p>{html.escape(_safe_str(row.get("narration")))}</p></div>
              <div><strong>Progress:</strong>
                <pre>{html.escape(json.dumps(row.get("progress_delta") or {}, ensure_ascii=False, indent=2, sort_keys=True, default=str))}</pre>
              </div>
              <div><strong>Progress quality:</strong>
                <pre>{html.escape(json.dumps(row.get("progress_quality") or {}, ensure_ascii=False, indent=2, sort_keys=True, default=str))}</pre>
              </div>
              <details>
                <summary>Story hook result</summary>
                <pre>{html.escape(json.dumps(row.get("story_hook_result") or {}, ensure_ascii=False, indent=2, sort_keys=True, default=str))}</pre>
              </details>
              <details>
                <summary>Base runtime response</summary>
                <pre>{html.escape(json.dumps(row.get("base_response_payload") or {}, ensure_ascii=False, indent=2, sort_keys=True, default=str))}</pre>
              </details>
              <details>
                <summary>Final authoritative state</summary>
                <pre>{html.escape(json.dumps(row.get("final_authoritative_state") or {}, ensure_ascii=False, indent=2, sort_keys=True, default=str))}</pre>
              </details>
              <details>
                <summary>Strategy guidance</summary>
                <pre>{html.escape(json.dumps(row.get("strategy_guidance") or {}, ensure_ascii=False, indent=2, sort_keys=True, default=str))}</pre>
              </details>
              <details>
                <summary>Action diversity before turn</summary>
                <pre>{html.escape(json.dumps(row.get("action_diversity_before_turn") or {}, ensure_ascii=False, indent=2, sort_keys=True, default=str))}</pre>
              </details>
              <details>
                <summary>State bounds</summary>
                <pre>{html.escape(json.dumps(row.get("state_bounds") or {}, ensure_ascii=False, indent=2, sort_keys=True, default=str))}</pre>
              </details>
              <details>
                <summary>Save/load checkpoint</summary>
                <pre>{html.escape(json.dumps(row.get("save_load_checkpoint") or {}, ensure_ascii=False, indent=2, sort_keys=True, default=str))}</pre>
              </details>
              <details>
                <summary>Suggested actions shown to player-agent ({len(suggested)})</summary>
                <pre>{html.escape(json.dumps(suggested, ensure_ascii=False, indent=2))}</pre>
              </details>
              <details>
                <summary>Raw turn</summary>
                <pre>{html.escape(json.dumps(row, ensure_ascii=False, indent=2, sort_keys=True, default=str))}</pre>
              </details>
            </section>
            """
        )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Autoplay Campaign Transcript</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; line-height: 1.45; background: #111; color: #eee; }}
    .summary, .turn {{ border: 1px solid #444; border-radius: 12px; padding: 16px; margin-bottom: 16px; background: #181818; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #080808; padding: 12px; border-radius: 8px; }}
    h1, h2 {{ margin-top: 0; }}
  </style>
</head>
<body>
  <h1>Autoplay Campaign Transcript</h1>
  <section class="summary">
    <h2>Summary</h2>
    <pre>{html.escape(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str))}</pre>
  </section>
  {''.join(rows)}
</body>
</html>"""


def write_autoplay_artifacts(
    *,
    output_dir: Path,
    transcript: List[Dict[str, Any]],
    summary: Dict[str, Any],
    metrics: Dict[str, Any],
    health: Dict[str, Any],
    artifact_detail: str = "summary",
) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "autoplay-summary.json"
    transcript_path = output_dir / "autoplay-transcript.json"
    metrics_path = output_dir / "autoplay-progress-metrics.json"
    performance_path = output_dir / "autoplay-performance.json"
    health_path = output_dir / "autoplay-health.json"
    html_path = output_dir / "autoplay-transcript.html"
    zip_path = output_dir / "autoplay-campaign-results.zip"

    write_json(summary_path, summary)
    write_json(metrics_path, metrics)
    write_json(performance_path, metrics.get("performance") or {})
    write_json(health_path, health)
    if artifact_detail == "full":
        write_json(transcript_path, transcript)
        html_path.write_text(render_autoplay_html(transcript, summary), encoding="utf-8")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(summary_path, summary_path.name)
        zf.write(metrics_path, metrics_path.name)
        zf.write(performance_path, performance_path.name)
        zf.write(health_path, health_path.name)
        if artifact_detail == "full":
            zf.write(transcript_path, transcript_path.name)
            zf.write(html_path, html_path.name)
            campaign_report_html = output_dir / "autoplay-campaign-report.html"
            campaign_report_json = output_dir / "autoplay-campaign-report.json"
            if campaign_report_html.exists():
                zf.write(campaign_report_html, campaign_report_html.name)
            if campaign_report_json.exists():
                zf.write(campaign_report_json, campaign_report_json.name)
            checkpoint_dir = output_dir / "checkpoints"
            if checkpoint_dir.exists():
                session_id = str(summary.get("session_id") or "")
                pattern = f"{session_id}_turn_*.json" if session_id else "*.json"
                for checkpoint_path in sorted(checkpoint_dir.glob(pattern)):
                    zf.write(checkpoint_path, f"checkpoints/{checkpoint_path.name}")

    return {
        "summary": str(summary_path),
        "metrics": str(metrics_path),
        "performance": str(performance_path),
        "health": str(health_path),
        "transcript": str(transcript_path) if artifact_detail == "full" else "",
        "html": str(html_path) if artifact_detail == "full" else "",
        "zip": str(zip_path),
    }