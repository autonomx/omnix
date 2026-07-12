# Desktop Mode Game Companion

Desktop Mode lets the Chatbot workspace attach a user-approved desktop or game window frame to the next assistant message. When a vision model is configured, the gateway turns the screenshot history into a concise `desktop_vision` context item before queuing the normal chat response.

## Enable It

1. Start the Omnix gateway and web app normally.
2. Configure a vision-capable OpenAI-compatible endpoint for the gateway process:

```powershell
$env:OMNIX_VISION_BASE_URL = "http://127.0.0.1:1234/v1"
$env:OMNIX_VISION_MODEL = "your-vision-model"
$env:OMNIX_VISION_API_KEY = "optional-api-key"
```

3. Open the web app in a Chromium browser.
4. Go to Chatbot, then Chats.
5. In the composer controls, click `Desktop`.
6. Pick the game window, monitor, or browser tab from the browser permission dialog.
7. Wait until the Audio Services desktop status says `Buffering recent frames` or `Sharing`.
8. Ask the assistant about the game, for example `What should I do next based on what you can see?`

The browser only sends frames after you click `Desktop` and approve the share prompt. Clicking `Desktop` again stops sharing.

## Runtime Notes

- The frontend captures the current frame plus a bounded recent history, then sends it through `/api/assistant/context/chat/sessions/{session_id}/messages`.
- The gateway uses `OMNIX_VISION_BASE_URL`, `OMNIX_VISION_MODEL`, and optional `OMNIX_VISION_API_KEY` to call `/chat/completions` with image input.
- If the endpoint rejects multiple image inputs, the gateway falls back to a combined contact sheet, then to the current frame only.
- Desktop Mode enriches the next chat turn; it is not continuous game automation and does not control the game.
- Browser screen capture requires a secure context, so use `localhost` or HTTPS.
