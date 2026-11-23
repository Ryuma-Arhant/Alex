# Real phone calls (Twilio → LiveKit)

The agent can phone borrowers' real numbers, for individual calls and for bulk calls. Phone calls stay
**switched off** until `SIP_OUTBOUND_TRUNK_ID` is set; until then the app behaves exactly as before
(browser calls only, and Bulk Call says that calling is not switched on).

## How a phone call works

1. The backend creates the call (direction `OUTBOUND`, the number in `calls.dial_to`), dispatches the agent
   into a new LiveKit room through the API, and gives the user's browser a listen-only token.
2. The agent fetches `/internal/calls/{id}/context`, which carries `dial: {to, trunk_id, ringing_timeout_s}`,
   and dials through the LiveKit outbound trunk → Twilio Elastic SIP trunk → the borrower's phone, waiting
   until they answer.
3. Answered: the agent links its session to the phone participant only, greets, and the call runs as usual
   (transcript, summary, Dashboard). The browser hears both sides and shows Ringing / On the phone.
4. Not answered: the agent reports `busy`, `no_answer`, `declined`, `invalid_number` or `dial_failed`
   (from the SIP status), the room is closed, and the Call Page / Dashboard / bulk list show the reason.
5. The full number is erased (`dial_to = NULL`) as soon as the call ends; only its last 4 digits are kept.

Bulk calls use the same path from a queue: the backend calls the valid rows of the uploaded CSV **one at a
time** (the agent worker's 1 GB memory allows one call at a time), records each result, and can be paused,
resumed or cancelled from the Bulk Call pop-up.

## One-time setup (after the Twilio account is upgraded)

1. In the Twilio console: upgrade the account, add funds, and buy a voice-capable number.
2. Add to `.env`: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` (E.164).
3. Run (checks the account first, then creates or updates everything; safe to run again):

   ```
   cd backend
   uv run python -m app.scripts.setup_phone_calls --dry-run
   uv run python -m app.scripts.setup_phone_calls --country IN
   ```

   It creates the Twilio trunk `alex-livekit` (domain `*.pstn.twilio.com`), its SIP credential, attaches the
   number, allows calls to India, and creates the LiveKit outbound trunk `alex-twilio`.
4. Put the printed `SIP_OUTBOUND_TRUNK_ID` (and `SIP_AUTH_*` if generated) in `.env`, restart the backend.
   `GET /api/v1/auth/config` then returns `"phone_calls": true`, and the Individual Call pop-up offers
   "Call their phone".

## Testing

1. Individual call to your own phone: it rings, the agent greets after you answer, the transcript appears,
   and hanging up ends the call and writes the summary.
2. Reject the call, and let it ring out: the Call Page should say "Busy" / "Declined" / "No answer".
3. Bulk: upload a CSV with two of your own numbers, Proceed, and watch them called one after the other;
   try Pause, Resume and Cancel.
4. Then set `SIP_OUTBOUND_TRUNK_ID` on Railway (backend service) and deploy agent → backend → frontend.
