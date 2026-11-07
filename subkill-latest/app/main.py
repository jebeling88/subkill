import json, os
from datetime import date
from pathlib import Path
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from . import agent, ai, auth, db, gmail, subs

app = FastAPI(title="SubKill")
STATIC = Path(__file__).parent / "static"

@app.middleware("http")
async def csrf_guard(request: Request, call_next):
    # Cheap CSRF defence: state-changing API calls must carry a header a cross-site form can't set.
    if request.url.path.startswith("/api") and request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("x-subkill") != "1":
            return JSONResponse({"detail": "Missing X-SubKill header."}, status_code=403)
    return await call_next(request)

class Creds(BaseModel):
    email: str
    password: str
    invite: str = ""

# ---- abuse protection (this server spends YOUR Anthropic credit) --------
import hmac, time
from collections import defaultdict, deque
_hits = defaultdict(deque)
_usage = defaultdict(int)

def _throttle(key, limit, window):
    now, q = time.time(), _hits[key]
    while q and q[0] < now - window: q.popleft()
    if len(q) >= limit: raise HTTPException(429, "Too many attempts. Try again in a few minutes.")
    q.append(now)

def _cap(u, kind, default):
    """Per-user daily cap on AI calls so a leaked login can't run up the bill."""
    limit = int(os.environ.get(f"SUBKILL_DAILY_{kind.upper()}", default))
    k = (u["id"], date.today().isoformat(), kind)
    if _usage[k] >= limit: raise HTTPException(429, f"Daily {kind} limit reached ({limit}). Try again tomorrow.")
    _usage[k] += 1

def _ip(request): return request.client.host if request.client else "?"

def _set_cookie(resp, token):
    resp.set_cookie("sk_session", token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30,
                    secure=os.environ.get("PUBLIC_BASE_URL", "").startswith("https"))

@app.post("/api/signup")
def signup(c: Creds, resp: Response, request: Request):
    _throttle(("signup", _ip(request)), 10, 3600)
    need = os.environ.get("SUBKILL_INVITE_CODE", "")
    if need and not hmac.compare_digest(need.encode(), c.invite.strip().encode()):
        raise HTTPException(403, "That invite code isn't right.")
    t = auth.new_session(auth.create_user(c.email, c.password)); _set_cookie(resp, t)
    return {"ok": True, "token": t}

@app.post("/api/login")
def login(c: Creds, resp: Response, request: Request):
    _throttle(("login", _ip(request)), 20, 900)
    t = auth.new_session(auth.verify_user(c.email, c.password)); _set_cookie(resp, t)
    return {"ok": True, "token": t}

@app.post("/api/logout")
def logout(request: Request, resp: Response):
    t = request.cookies.get("sk_session") or request.headers.get("authorization", "")[7:].strip()
    if t: auth.end_session(t)
    resp.delete_cookie("sk_session")
    return {"ok": True}

@app.get("/api/me")
def me(u=Depends(auth.current_user)):
    return {"email": u["email"], "members": json.loads(u["members"]), "gmail_available": gmail.enabled(),
            "gmail_connected": bool(u["gmail_tokens"]), "ai_ready": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "categories": ai.CATEGORIES}

class Members(BaseModel):
    members: list[str]

@app.put("/api/members")
def set_members(m: Members, u=Depends(auth.current_user)):
    names = [n.strip()[:30] for n in m.members if n.strip()][:12] or ["Me"]
    with db.tx() as c:
        c.execute("UPDATE users SET members=? WHERE id=?", (json.dumps(names), u["id"]))
    return {"members": names}

@app.get("/api/subscriptions")
def list_(sort: str = "cost", status: str = "live", owner: str | None = None, category: str | None = None,
          cycle: str | None = None, q: str | None = None, unused: bool = False, u=Depends(auth.current_user)):
    return subs.list_subs(u["id"], sort, status, owner, category, cycle, q, unused)

@app.get("/api/summary")
def summary(u=Depends(auth.current_user)):
    return subs.summary(u["id"])

class NewSub(BaseModel):
    merchant: str
    amount: float
    cycle: str = "monthly"
    plan: str = ""
    category: str = "Other"
    owner: str = "Me"
    next_renewal: str = ""
    last_used_at: str = ""

@app.post("/api/subscriptions")
def add(s: NewSub, u=Depends(auth.current_user)):
    r = subs.upsert(u["id"], s.model_dump(), "manual", s.owner)
    if r == "skipped": raise HTTPException(400, "Need a name and an amount above zero.")
    return {"result": r}

def _own(sub_id, u):
    row = db.conn().execute("SELECT * FROM subscriptions WHERE id=? AND user_id=?", (sub_id, u["id"])).fetchone()
    if not row: raise HTTPException(404, "Not found.")
    return dict(row)

class Patch(BaseModel):
    owner: str | None = None
    category: str | None = None
    last_used_at: str | None = None
    next_renewal: str | None = None
    notes: str | None = None

@app.patch("/api/subscriptions/{sid}")
def patch(sid: int, p: Patch, u=Depends(auth.current_user)):
    _own(sid, u)
    f = {k: v for k, v in p.model_dump().items() if v is not None}
    if f:
        with db.tx() as c:
            c.execute("UPDATE subscriptions SET " + ",".join(f"{k}=?" for k in f) + " WHERE id=?", (*f.values(), sid))
    return {"ok": True}

@app.post("/api/subscriptions/{sid}/used")
def used(sid: int, u=Depends(auth.current_user)):
    _own(sid, u)
    with db.tx() as c:
        c.execute("UPDATE subscriptions SET last_used_at=?, use_count=use_count+1 WHERE id=?", (date.today().isoformat(), sid))
    return {"ok": True}

@app.delete("/api/subscriptions/{sid}")
def delete(sid: int, u=Depends(auth.current_user)):
    _own(sid, u)
    with db.tx() as c: c.execute("DELETE FROM subscriptions WHERE id=?", (sid,))
    return {"ok": True}

# ---- ingestion ----------------------------------------------------------
def _ingest(u, text, kind, owner):
    if not text.strip(): raise HTTPException(400, "Nothing to read.")
    try:
        found = ai.extract_subscriptions(text, kind, date.today().isoformat())
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(502, f"The AI step failed: {type(e).__name__}")
    res = {"new": 0, "updated": 0, "skipped": 0}
    for it in found: res[subs.upsert(u["id"], it, kind, owner)] += 1
    return {**res, "found": len(found)}

class Paste(BaseModel):
    text: str
    kind: str = "email"
    owner: str = "Me"

@app.post("/api/ingest/text")
def ingest_text(p: Paste, u=Depends(auth.current_user)):
    _cap(u, "ingest", 20)
    return _ingest(u, p.text[:480_000], p.kind if p.kind in ("email", "bank statement", "other") else "other", p.owner)

@app.post("/api/ingest/upload")
async def ingest_upload(file: UploadFile = File(...), owner: str = Form("Me"), u=Depends(auth.current_user)):
    _cap(u, "ingest", 20)
    raw = await file.read(2_000_001)
    if len(raw) > 2_000_000: raise HTTPException(413, "File is over 2 MB.")
    try: text = raw.decode("utf-8-sig")
    except UnicodeDecodeError: text = raw.decode("latin-1")
    name = (file.filename or "").lower()
    return _ingest(u, text, "bank statement" if name.endswith((".csv", ".ofx", ".qfx")) else "email", owner)

# ---- gmail --------------------------------------------------------------
@app.get("/api/gmail/connect")
def gmail_connect(u=Depends(auth.current_user)):
    if not gmail.enabled(): raise HTTPException(503, "Gmail isn't configured on this server (see .env.example).")
    return RedirectResponse(gmail.auth_url(u["id"]))

@app.get("/api/gmail/callback")
def gmail_callback(code: str = "", state: str = "", error: str = ""):
    if error or not code: return RedirectResponse("/?gmail=denied")
    try: gmail.finish(code, state)
    except Exception: return RedirectResponse("/?gmail=error")
    return RedirectResponse("/?gmail=connected")

@app.post("/api/gmail/scan")
def gmail_scan(owner: str = "Me", u=Depends(auth.current_user)):
    _cap(u, "ingest", 20)
    try: text = gmail.fetch_text(u)
    except RuntimeError as e: raise HTTPException(400, str(e))
    except Exception: raise HTTPException(502, "Couldn't read Gmail. Try reconnecting.")
    return _ingest(u, text, "email", owner)

@app.post("/api/gmail/disconnect")
def gmail_disconnect(u=Depends(auth.current_user)):
    with db.tx() as c: c.execute("UPDATE users SET gmail_tokens=NULL WHERE id=?", (u["id"],))
    return {"ok": True}

# ---- the kill flow ------------------------------------------------------
@app.post("/api/subscriptions/{sid}/kill")
def kill(sid: int, u=Depends(auth.current_user)):
    """Ask Claude for the cancellation plan + a ready-to-send email. Nothing is cancelled yet."""
    s = _own(sid, u)
    _cap(u, "plan", 40)
    try: plan = ai.cancel_plan(s)
    except RuntimeError as e: raise HTTPException(503, str(e))
    except Exception as e: raise HTTPException(502, f"The AI step failed: {type(e).__name__}")
    with db.tx() as c:
        c.execute("UPDATE subscriptions SET cancel_plan=?, cancel_url=COALESCE(NULLIF(?,''),cancel_url) WHERE id=?",
                  (json.dumps(plan), plan.get("cancel_url", ""), sid))
    return plan

class Email(BaseModel):
    to: str
    subject: str
    body: str

@app.post("/api/subscriptions/{sid}/send-cancel-email")
def send_cancel(sid: int, e: Email, u=Depends(auth.current_user)):
    """Sends exactly what the user reviewed in the UI, from their own Gmail."""
    _own(sid, u)
    if not u["gmail_tokens"]: raise HTTPException(400, "Connect Gmail first.")
    if "@" not in e.to or "\n" in e.to or "\n" in e.subject: raise HTTPException(400, "Bad address or subject.")
    try: gmail.send(u, e.to.strip(), e.subject.strip(), e.body)
    except Exception: raise HTTPException(502, "Gmail refused to send. Try reconnecting.")
    _mark(sid, "cancelling")
    return {"ok": True}

def _mark(sid, status):
    now = date.today().isoformat()
    with db.tx() as c:
        if status == "cancelling":
            c.execute("UPDATE subscriptions SET status='cancelling', cancel_requested_at=COALESCE(cancel_requested_at,?), still_charging=0 WHERE id=? AND status!='cancelled'", (now, sid))
        else:
            c.execute("UPDATE subscriptions SET status='cancelled', cancelled_at=?, cancel_requested_at=COALESCE(cancel_requested_at,?), still_charging=0 WHERE id=?", (now, now, sid))

@app.post("/api/subscriptions/{sid}/mark-cancelling")
def mark_cancelling(sid: int, u=Depends(auth.current_user)):
    _own(sid, u); _mark(sid, "cancelling"); return {"ok": True}

@app.post("/api/subscriptions/{sid}/mark-cancelled")
def mark_cancelled(sid: int, u=Depends(auth.current_user)):
    _own(sid, u); _mark(sid, "cancelled"); return {"ok": True}

@app.post("/api/subscriptions/{sid}/restore")
def restore(sid: int, u=Depends(auth.current_user)):
    _own(sid, u)
    with db.tx() as c:
        c.execute("UPDATE subscriptions SET status='active', cancelled_at=NULL, cancel_requested_at=NULL, still_charging=0 WHERE id=?", (sid,))
    return {"ok": True}

@app.post("/api/demo/seed")
def seed(u=Depends(auth.current_user)):
    subs.demo_seed(u["id"]); return {"ok": True}

class ChatIn(BaseModel):
    messages: list[dict]

@app.post("/api/chat")
def chat(c: ChatIn, u=Depends(auth.current_user)):
    _cap(u, "chat", 100)
    msgs = [{"role": m["role"], "content": str(m["content"])[:4000]} for m in c.messages[-20:]
            if m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()]
    if not msgs or msgs[-1]["role"] != "user": raise HTTPException(400, "Say something first.")
    try: return agent.run(u, msgs)
    except RuntimeError as e: raise HTTPException(503, str(e))
    except Exception as e: raise HTTPException(502, f"The AI step failed: {type(e).__name__}")

@app.delete("/api/account")
def delete_account(u=Depends(auth.current_user)):
    """Apple requires in-app account deletion. Removes everything we store about the user."""
    with db.tx() as c:
        c.execute("DELETE FROM subscriptions WHERE user_id=?", (u["id"],))
        c.execute("DELETE FROM sessions WHERE user_id=?", (u["id"],))
        c.execute("DELETE FROM users WHERE id=?", (u["id"],))
    return {"ok": True}

@app.get("/healthz")
def healthz(): return {"ok": True}

def _page(name):
    html = (STATIC / name).read_text()
    contact = os.environ.get("SUBKILL_SUPPORT_EMAIL", "the developer (contact details are on the App Store / TestFlight page)")
    return HTMLResponse(html.replace("{{SUPPORT}}", contact))

@app.get("/privacy")
def privacy(): return _page("privacy.html")

@app.get("/support")
def support(): return _page("support.html")

@app.get("/")
def index(): return FileResponse(STATIC / "index.html")

app.mount("/static", StaticFiles(directory=STATIC), name="static")
