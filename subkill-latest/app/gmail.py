import base64, json, os, secrets, time, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
import httpx
from . import db

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPES = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send"
QUERY = ('newer_than:12m (subscription OR "your receipt" OR invoice OR "free trial" OR renewal OR '
         '"auto-renew" OR "billing" OR membership OR "payment received" OR "has been charged" OR "will renew")')
_states = {}

def enabled(): return bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))
def redirect_uri(): return os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/") + "/api/gmail/callback"

def auth_url(user_id):
    s = secrets.token_urlsafe(16); _states[s] = (user_id, time.time())
    q = dict(client_id=os.environ["GOOGLE_CLIENT_ID"], redirect_uri=redirect_uri(), response_type="code",
             scope=SCOPES, access_type="offline", prompt="consent", state=s)
    return AUTH + "?" + urllib.parse.urlencode(q)

def finish(code, state):
    uid, ts = _states.pop(state, (None, 0))
    if not uid or time.time() - ts > 600:
        raise ValueError("Bad or expired state.")
    r = httpx.post(TOKEN, data=dict(code=code, client_id=os.environ["GOOGLE_CLIENT_ID"],
                   client_secret=os.environ["GOOGLE_CLIENT_SECRET"], redirect_uri=redirect_uri(),
                   grant_type="authorization_code"), timeout=20)
    r.raise_for_status()
    t = r.json(); t["obtained"] = time.time()
    with db.tx() as c:
        c.execute("UPDATE users SET gmail_tokens=? WHERE id=?", (json.dumps(t), uid))
    return uid

def _access(user):
    t = json.loads(user["gmail_tokens"] or "null")
    if not t: raise RuntimeError("Gmail is not connected.")
    if time.time() > t["obtained"] + t.get("expires_in", 3600) - 60:
        r = httpx.post(TOKEN, data=dict(client_id=os.environ["GOOGLE_CLIENT_ID"],
                       client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
                       refresh_token=t["refresh_token"], grant_type="refresh_token"), timeout=20)
        r.raise_for_status()
        t.update(r.json()); t["obtained"] = time.time()
        with db.tx() as c:
            c.execute("UPDATE users SET gmail_tokens=? WHERE id=?", (json.dumps(t), user["id"]))
    return t["access_token"]

def _body(payload):
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"] + "==").decode("utf-8", "ignore")
    for p in payload.get("parts", []) or []:
        b = _body(p)
        if b: return b
    return ""

def fetch_text(user, limit=150):
    h = {"Authorization": f"Bearer {_access(user)}"}
    ids, tok = [], None
    while len(ids) < limit:
        r = httpx.get(f"{API}/messages", headers=h, timeout=30,
                      params=dict(q=QUERY, maxResults=min(100, limit - len(ids)), **({"pageToken": tok} if tok else {})))
        r.raise_for_status(); j = r.json()
        ids += [m["id"] for m in j.get("messages", [])]
        tok = j.get("nextPageToken")
        if not tok: break
    def get(i):
        m = httpx.get(f"{API}/messages/{i}", headers=h, params=dict(format="full"), timeout=30).json()
        hd = {x["name"].lower(): x["value"] for x in m.get("payload", {}).get("headers", [])}
        body = " ".join(_body(m.get("payload", {})).split())[:1500] or m.get("snippet", "")
        return f"From: {hd.get('from','')}\nDate: {hd.get('date','')}\nSubject: {hd.get('subject','')}\n{body}\n---"
    with ThreadPoolExecutor(8) as ex:
        return "\n".join(ex.map(get, ids))

def send(user, to, subject, body):
    msg = EmailMessage(); msg["To"] = to; msg["Subject"] = subject; msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    r = httpx.post(f"{API}/messages/send", headers={"Authorization": f"Bearer {_access(user)}"},
                   json={"raw": raw}, timeout=30)
    r.raise_for_status()
