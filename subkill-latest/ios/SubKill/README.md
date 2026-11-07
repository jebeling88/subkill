# SubKill for iOS (SwiftUI, iOS 17+)

Dashboard of everything still charging you (ranked by cost, sortable) with a chat pinned to the bottom where you ask Claude to kill things.

## 1. Start the backend (on your Mac)
```bash
cd ../..            # the subkill/ folder
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
No key yet? You can still sign up and tap **Load sample data**; only chat/kill needs the key.

## 2. Open the app in Xcode
**Option A — XcodeGen (fastest):** `brew install xcodegen && cd ios/SubKill && xcodegen && open SubKill.xcodeproj`

**Option B — by hand:** Xcode → File → New → Project → iOS App (SwiftUI, name `SubKill`, minimum iOS 17). Delete `ContentView.swift`, drag everything in `SubKill/SubKill/*.swift` into the project, then in the target's *Info* tab add **App Transport Security Settings → Allow Arbitrary Loads = YES** (test builds use plain http).

## 3. Run
- **Simulator:** server address `http://localhost:8000`.
- **Real iPhone (same Wi-Fi):** set your team under Signing & Capabilities, then use your Mac's address, e.g. `http://192.168.1.20:8000` (System Settings → Wi-Fi → Details, or `ipconfig getifaddr en0`).

Create an account → Load sample data → type "cancel Netflix" in the bar at the bottom.

## Notes
- Token is stored in the Keychain. Cancelling is guided: Claude gives the official page, steps, and an email draft; you do the final tap and then confirm. It never sends email or logs into other sites.
- Remove the ATS exception and put the server behind https before real use.
