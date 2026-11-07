# SubKill → TestFlight, step by step

Total time: about 1–2 hours of your attention, plus Apple's waiting time.

## A. Apple Developer account ($99/year) — start this first
1. developer.apple.com/programs/enroll → sign in with your Apple ID → enroll as an **Individual**.
2. Approval can take minutes to 48 hours. You can do part B meanwhile.

## B. Put the server online (Render)
1. Make a free account at github.com. Click **New repository** → name it `subkill` → **Private** → Create.
2. Click **uploading an existing file**, drag in everything *inside* the unzipped `subkill` folder (so `render.yaml` and `Dockerfile` sit at the top level), and commit.
3. Make an account at render.com → **New → Blueprint** → connect GitHub → pick `subkill`.
4. Render asks for four values:
   - `ANTHROPIC_API_KEY` — a NEW key from console.anthropic.com (never reuse one you pasted into chat).
   - `SUBKILL_INVITE_CODE` — a passphrase you invent. Only people who know it can sign up, which protects your Anthropic bill.
   - `PUBLIC_BASE_URL` — `https://subkill.onrender.com` (use the exact address Render shows after it's created; you can edit this later).
   - `SUBKILL_SUPPORT_EMAIL` — an email you're happy to show publicly on the privacy page.
5. Wait for the deploy to finish. Then open `https://<your-address>/healthz` (should show `{"ok":true}`) and `https://<your-address>/privacy`.
6. Also try signing up in Safari at your address using the invite code. If that works, the server is ready.

## C. Point the app at your server
1. Open `ios/SubKill/SubKill/Config.swift` and replace the address with yours (https, no trailing slash).
2. In `ios/SubKill/project.yml`, change `com.example` (in two places) to something unique to you, e.g. `com.jamesebeling`. Bundle ID becomes `com.jamesebeling.subkill`.

## D. Register the app with Apple (once your Developer account is active)
1. appstoreconnect.apple.com → **Apps → + → New App**. Platform iOS, name **SubKill** (if taken, try "SubKill: Cancel Subscriptions"), language English, bundle ID = the one from step C (if it isn't listed, add it first at developer.apple.com → Certificates, IDs & Profiles → Identifiers), SKU = anything, e.g. `subkill1`.

## E. Build and upload from your Mac
1. Install Xcode from the Mac App Store (large download). Open it once and accept the license. Sign in under Xcode → Settings → Accounts with your Apple ID.
2. In Terminal: `brew install xcodegen` (install Homebrew first from brew.sh if needed), then:
   `cd /Users/jamesebeling/Downloads/subkill/ios/SubKill && xcodegen && open SubKill.xcodeproj`
3. In Xcode: click SubKill (top of left sidebar) → **Signing & Capabilities** → tick *Automatically manage signing* → choose your Team.
4. Top bar destination: **Any iOS Device (arm64)**. Menu **Product → Archive**.
5. When the Organizer window opens: **Distribute App → App Store Connect → Distribute**. Accept the defaults.

## F. TestFlight
1. In App Store Connect → your app → **TestFlight**. The build shows "Processing" for 10–30 minutes, then appears. If it asks about export compliance, answer that the app uses only standard encryption (HTTPS).
2. **Test Information:** add your email, a short "what to test" note, and the privacy policy URL: `https://<your-address>/privacy`.
3. **You (fastest):** App Store Connect → Users and Access → invite yourself/family as users (role *App Manager* or *Developer*), then TestFlight → *Internal Testing* → create a group → add them. No Apple review needed; they get an email.
4. **Anyone else (wife, kids, friends):** *External Testing* → new group → add their emails or turn on a public link. The first build gets a one-time Apple review, usually about a day.
5. Testers install Apple's **TestFlight** app from the App Store, accept the invite, tap Install. They sign up in SubKill with your invite code.

## G. Shipping updates
Change code → in project.yml raise `CURRENT_PROJECT_VERSION` (1 → 2 → 3…) → xcodegen → Archive → Distribute. Server updates just need a push to GitHub; Render redeploys automatically.

## Notes
- Render's Starter plan (~$7/mo) is required for the saved-data disk. On the free plan your data would vanish on every restart.
- Gmail scanning is off on the hosted server unless you add Google OAuth keys. Paste-in emails and CSV upload work without it.
- Per-user daily caps (chat 100, plans 40, scans 20) keep a runaway login from running up your bill. Change them with SUBKILL_DAILY_CHAT / _PLAN / _INGEST.
- If Xcode shows a build error, screenshot it. The Swift code hasn't been compiled by me, so a small fix on first build is possible.
