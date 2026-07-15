# Desktop Mode and Companion Watch

Omnix provides two user-authorized screen-vision modes:

1. **Desktop Ask** attaches the current frame and bounded recent history to the next user message.
2. **Companion Watch** continuously samples a shared source, but only submits change-gated observations after the user explicitly presses **Start**.

Neither mode controls the computer or game.

## Requirements

- Chromium-family browser with `getDisplayMedia` support.
- Secure browser context: `localhost` or HTTPS.
- Omnix gateway and web app from the same deployment.
- OpenAI-compatible vision endpoint that accepts image input.
- Explicit browser permission for each shared source.

Recommended browsers:

| Browser | Minimum tested contract | Notes |
|---|---:|---|
| Google Chrome | 120+ | Primary browser path |
| Microsoft Edge | 120+ | Chromium behavior expected |
| Chromium | 120+ | Distribution codecs and capture UI may differ |
| Firefox | Not supported for rollout | Capture and media lifecycle require separate validation |
| Safari | Not supported for rollout | Capture and audio lifecycle require separate validation |

Capture-source support:

| Source | Support | Notes |
|---|---|---|
| Browser tab | Supported | Best visibility lifecycle behavior |
| Application window | Supported | Protected or minimized windows may return blank/stale frames |
| Monitor | Supported | Highest privacy exposure; remote-provider disclosure is important |
| Protected fullscreen/video | Best effort | DRM and operating-system protections may return black frames |

## Configure Vision

```powershell
$env:OMNIX_VISION_BASE_URL = "http://127.0.0.1:1234/v1"
$env:OMNIX_VISION_MODEL = "your-vision-model"
$env:OMNIX_VISION_API_KEY = "optional-api-key"
```

The endpoint must support OpenAI-compatible `/chat/completions` image messages. Omnix prefers separate temporal-history and current-frame images, then falls back to a combined contact sheet and current-only input.

## Desktop Ask

1. Open Chatbot → Chats.
2. Click **Desktop**.
3. Select a tab, window, or monitor.
4. Wait for `Buffering recent frames` or `Sharing`.
5. Ask a screen-specific question.
6. Click **Desktop** again to stop sharing.

Desktop Ask remains available even when Companion Watch is disabled or in operational backoff.

## Companion Watch

1. In Settings → Assistant & Chat, enable Desktop Companion and select a requested rollout stage.
2. For remote vision, explicitly enable **Allow remote vision provider**.
3. Start screen sharing with **Desktop**.
4. In the Chat workspace, press **Start** under Companion Watch.
5. Omnix performs a harmless one-pixel image-capability preflight.
6. Use **Pause**, **Resume**, **Muted/Sound on**, or **Stop** as needed.

Global settings only make Watch available. They do not start observation. Every Watch session requires an explicit in-session Start.

## Rollout Stages

- **Disabled:** no Watch observation.
- **Shadow:** observes and records content-free aggregate evidence; produces no comments.
- **Text:** requires an exact evidence partition to pass; shows one transient dismissible comment.
- **Speech:** requires a separate speech partition; otherwise degrades to text.

Evidence is isolated by commit SHA, observation schema, attention policy, provider class, model hash, and remote/local status.

A controlled speech evidence canary may be enabled by deployment operators:

```powershell
$env:OMNIX_DESKTOP_COMPANION_SPEECH_CANARY = "1"
```

It is off by default and does not bypass user Start, mute, preflight, remote consent, floor ownership, interruption, or stale-candidate checks.

## Privacy Model

- Raw screenshots remain in browser memory and are not written to the evaluation store.
- The gateway receives frames only for an authorized user request or an explicitly started Watch session.
- Screen text is untrusted observed data and is never treated as an instruction.
- Source labels are reduced to a browser-side fingerprint before Watch requests.
- Evaluation records contain aggregate counts, rates, latency, hashed model identity, build identity, and identifier-only scenarios.
- Evaluation records reject image-, frame-, prompt-, transcript-, message-, commentary-, and screen-text-bearing metric keys.
- Remote vision is blocked before the test image is sent unless the user explicitly allows it.
- **Stop** clears browser binding state and resets gateway scene memory for the capture generation.

## Performance and Resource Budgets

```text
capture sampling                         2 FPS
history buffer                            6 seconds / 12 frames
provider-wide background calls            6 per minute
minimum background interval               8 seconds
observation timeout                       10 seconds
observation stale TTL                     12 seconds
background pending queue                   64 global maximum
per-generation pending work                1 coalesced item
text/speech pending delivery               1 coalesced item
evaluation retention                       5,000 records
provider-failure backoff                   60 seconds after 3 failures
provider-failure stop                      after 6 consecutive failures
```

Foreground Desktop Ask requests always outrank background Watch work. A ten-thousand-request endurance guard verifies that unique-session background work remains bounded, and repeated updates for one capture generation coalesce to one pending request.

## Troubleshooting

### `Testing model` never completes

- Confirm the vision endpoint is reachable from the gateway process.
- Confirm the model accepts image input.
- Check `OMNIX_VISION_BASE_URL` and `OMNIX_VISION_MODEL`.
- For a remote endpoint, enable remote vision explicitly.

### `Remote blocked`

The selected endpoint is not loopback and remote vision consent is off. Enable remote vision only after reviewing what is shared.

### Watch enters backoff

Three consecutive provider errors pause Watch for 60 seconds. A successful observation resets the circuit. Six consecutive provider errors stop Watch and require a new explicit Start.

### Blank or stale observations

- Re-select the source.
- Avoid minimized/protected windows.
- Prefer a browser tab or window over a full monitor.
- Verify the source continues producing frames when the Omnix tab is visible.

### Text works but speech does not

- Confirm auto-speak is enabled and Companion Watch is unmuted.
- Speech may still be gated and safely degraded to text.
- Operators can inspect the internal speech release-gate evidence without exposing generated content.

## Deployment Kill Switch and Rollback

To immediately disable Companion Watch while preserving manual Desktop Ask:

```powershell
$env:OMNIX_DESKTOP_COMPANION_KILL_SWITCH = "1"
```

Restart the gateway. The kill switch blocks preflight and observation and forces effective rollout to `disabled`. Browser operational checks stop active Watch sessions.

Rollback procedure:

1. Set the kill switch.
2. Confirm `/api/desktop-companion/operational-status` reports `kill_switch: true`.
3. Revert or redeploy the prior known-good `main` commit.
4. Keep rollout settings disabled until new exact-build evidence is collected.
5. Remove the kill switch only after preflight, shadow observation, and required GitHub Actions gates pass.

## Data Deletion

- Press **Stop** to clear active capture binding and scene memory.
- Delete `resources/data/desktop_companion_evaluations.json` while Omnix is stopped to remove local aggregate evidence.
- No screenshot or video archive is created by Desktop Companion.
