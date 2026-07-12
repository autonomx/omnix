# Milestone 8 — Approval-gated Google Calendar

Status: implementation complete; operator OAuth connection still required.

## Runtime flow

```text
live voice request
  -> Hermes proposal-only calendar action
  -> deterministic Omnix validation
  -> editable Chatbot review card
  -> explicit user approval
  -> Google Calendar API
  -> durable assistant-tool ledger
```

Hermes never receives Google credentials and cannot call Google directly. The backend keeps OAuth tokens private, refreshes expired access tokens, rechecks the tool policy at execution time, and rejects duplicate approved proposal IDs.

Ambiguous requests remain non-executable. For example, “Create a reminder for six” requires the user to provide an exact date, AM/PM choice, end time, and timezone in the review card. `OMNIX_TIMEZONE` supplies the default IANA timezone label but does not authorize the model to invent missing details.

## One-time Google setup

1. Create or select a Google Cloud project.
2. Enable the Google Calendar API.
3. Configure an OAuth consent screen and add the account as a test user for a personal installation.
4. Create an OAuth 2.0 Web application client.
5. Add this authorized redirect URI exactly:

   ```text
   http://127.0.0.1:8000/api/assistant/tools/connect/google/callback
   ```

6. In Omnix, open **Chatbot -> Tools -> Google Calendar**, enter the OAuth client ID and secret, and select **Connect account**.
7. Keep **Create events** on `always_ask` or `ask_sensitive`.

The OAuth callback uses a one-time state nonce with a ten-minute lifetime. OAuth client secrets and tokens are stored only in ignored local files under `resources/data/`; API responses and logs do not expose them.

## Verification

- A disconnected calendar proposal opens the Tools configuration surface.
- An ambiguous date or time disables approval.
- A complete proposal remains non-executing until the button is selected.
- Event creation uses `calendar.events.insert` against the authenticated primary calendar.
- Reminder minutes create a popup reminder override.
- A repeated proposal ID returns the original execution reference instead of creating another event.
- Google failures return a bounded adapter error and do not report state change.

No test or readiness check creates a real calendar event. Real execution verification should be performed only after the operator connects a disposable or intended calendar and explicitly approves a clearly labeled test event.
