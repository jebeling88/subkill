# SubKill

Find every forgotten subscription and auto-renewal, rank them by what they cost, and kill them.

## Run it
```bash
pip install -r requirements.txt
cp .env.example .env        # add ANTHROPIC_API_KEY (and optional Google keys)
set -a; . ./.env; set +a
uvicorn app.main:app --port 8000
```
Open http://localhost:8000, create an account, and use **Load sample data** to look around without a key.

## How it works
- **Ingest** (`app/ai.py`, `app/gmail.py`): paste emails, upload a bank CSV / .eml, or connect Gmail. Claude pulls out recurring charges, trials and renewals through a forced tool schema, then they're merged (deduped by merchant + plan + household member).
- **Dashboard**: ranked by monthly cost by default; sort by unused / recently used / most used / oldest / newest / renewal date / name; filter by household member, category, billing cycle, status, "unused 60+ days".
- **Kill**: Claude writes the exact cancellation path (official URL, steps, retention traps) plus a ready-to-send email. You review it, then open the cancel page or send the email from your own Gmail. Mark it cancelled when done.
- **Watchdog**: every later scan checks for charges that land after a cancellation and flags them as "Still charging!".

## Chat + iOS
- `POST /api/chat`: Claude agent with tools (list, plan a cancellation, add, mark used/cancelling/cancelled). It cannot send email or touch other sites; plans come back as cards you tap. Marking *cancelled* only happens after you say you finished.
- Web UI has the chat bar at the bottom (works in iPhone Safari too). Native SwiftUI app lives in `ios/SubKill` (see its README). Mobile auth uses Bearer tokens from `/api/login`.

## Honest limits
- SubKill does not log into other companies' sites for you. Fully hands-off cancelling would need a browser agent (e.g. Claude in Chrome with the user present) and is not built in.
- Subscriptions billed through Apple/Google/PayPal must be cancelled there; the plan says so when it applies.
- Extraction is AI-based: always glance at results before killing. "Last used" comes from signals in emails or the **Used** button.
- Raw emails are never stored, only the extracted fields. Emails/statements are untrusted input: prompts treat them as data, outputs are schema-forced, and URLs/addresses are validated and shown to you before anything is opened or sent.
- Totals add raw numbers across currencies. For production: add HTTPS, rate limiting, encrypted token storage, and Google's OAuth app verification for the Gmail scopes.

## Test
`python -m pytest -q`
