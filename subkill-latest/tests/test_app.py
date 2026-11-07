import os, tempfile
from datetime import date, timedelta
import pytest
from fastapi.testclient import TestClient

@pytest.fixture()
def cl(monkeypatch, tmp_path):
    monkeypatch.setenv("SUBKILL_DB", str(tmp_path / "t.db"))
    from app import db, ai, main
    db._local.__dict__.clear(); main._hits.clear(); main._usage.clear()
    c = TestClient(main.app, headers={"X-SubKill": "1"})
    monkeypatch.setattr(ai, "extract_subscriptions", lambda text, kind, today: [
        {"merchant": "Netflix", "plan": "Premium", "amount": 22.99, "cycle": "monthly", "status": "active",
         "category": "Streaming", "last_charged_at": (date.today() - timedelta(days=5)).isoformat()},
        {"merchant": "Junk", "amount": 0, "cycle": "monthly", "status": "active"}])
    monkeypatch.setattr(ai, "cancel_plan", lambda s: {"method": "online", "difficulty": "easy", "steps": ["a"],
        "cancel_url": "https://netflix.com/cancel", "contact_email": "", "email_subject": "Cancel", "email_body": "Please cancel."})
    return c

def signed(cl, email="a@b.co"):
    assert cl.post("/api/signup", json={"email": email, "password": "password1"}).status_code == 200
    return cl

def test_auth_and_csrf(cl):
    assert cl.get("/api/summary").status_code == 401
    assert cl.post("/api/signup", json={"email": "x@y.z", "password": "short"}).status_code == 400
    bare = TestClient(cl.app)
    assert bare.post("/api/login", json={"email": "a", "password": "b"}).status_code == 403
    signed(cl)
    assert cl.get("/api/me").json()["email"] == "a@b.co"
    assert cl.post("/api/signup", json={"email": "a@b.co", "password": "password1"}).status_code == 409

def test_sorting_filtering_totals(cl):
    signed(cl); cl.post("/api/demo/seed")
    rows = cl.get("/api/subscriptions?sort=cost").json()
    costs = [r["monthly_cents"] for r in rows]
    assert costs == sorted(costs, reverse=True) and rows[0]["merchant"] == "HelloFresh"
    assert all(r["owner"] == "Kids" for r in cl.get("/api/subscriptions?owner=Kids").json())
    un = cl.get("/api/subscriptions?sort=unused&unused=true").json()
    assert un and un[0]["last_used_at"] is None or un[0]["last_used_at"] <= un[-1]["last_used_at"]
    mu = cl.get("/api/subscriptions?sort=most_used").json()
    assert mu[0]["use_count"] >= mu[-1]["use_count"]
    old = cl.get("/api/subscriptions?sort=oldest").json()
    assert old[0]["started_at"] <= old[-1]["started_at"]
    s = cl.get("/api/summary").json()
    assert s["monthly_cents"] == sum(costs) and s["yearly_cents"] == s["monthly_cents"] * 12

def test_ingest_dedupes(cl):
    signed(cl)
    r = cl.post("/api/ingest/text", json={"text": "hi", "owner": "Me"}).json()
    assert (r["new"], r["skipped"]) == (1, 1)
    r = cl.post("/api/ingest/text", json={"text": "hi again"}).json()
    assert (r["new"], r["updated"]) == (0, 1)
    assert len(cl.get("/api/subscriptions").json()) == 1

def test_kill_flow_and_rogue_charge(cl):
    signed(cl); cl.post("/api/ingest/text", json={"text": "x"})
    sid = cl.get("/api/subscriptions").json()[0]["id"]
    plan = cl.post(f"/api/subscriptions/{sid}/kill").json()
    assert plan["cancel_url"].startswith("https://")
    cl.post(f"/api/subscriptions/{sid}/mark-cancelled")
    assert cl.get("/api/subscriptions?status=cancelled").json()[0]["id"] == sid
    assert cl.get("/api/summary").json()["saved_yearly_cents"] > 0
    # a fresh charge well after the cancel date must be flagged
    from app import db
    db.conn().execute("UPDATE subscriptions SET cancelled_at=? WHERE id=?", ((date.today() - timedelta(days=20)).isoformat(), sid)); db.conn().commit()
    cl.post("/api/ingest/text", json={"text": "again"})
    assert cl.get("/api/summary").json()["still_charging"] == 1

def test_isolation(cl):
    signed(cl, "one@x.co"); cl.post("/api/demo/seed")
    sid = cl.get("/api/subscriptions").json()[0]["id"]
    cl.post("/api/logout")
    signed(cl, "two@x.co")
    assert cl.get("/api/subscriptions").json() == []
    assert cl.post(f"/api/subscriptions/{sid}/kill").status_code == 404
    assert cl.delete(f"/api/subscriptions/{sid}").status_code == 404

class _B:  # minimal stand-ins for SDK content blocks
    def __init__(s, **k): s.__dict__.update(k)
    def model_dump(s, exclude_none=True): return dict(s.__dict__)
class _R:
    def __init__(s, stop, blocks): s.stop_reason, s.content = stop, blocks

def test_chat_agent_plans_and_confirms(cl, monkeypatch):
    from app import ai
    signed(cl); cl.post("/api/ingest/text", json={"text": "x"})
    sid = cl.get("/api/subscriptions").json()[0]["id"]
    script = iter([
        _R("tool_use", [_B(type="tool_use", id="t1", name="get_cancel_plan", input={"subscription_id": sid})]),
        _R("end_turn", [_B(type="text", text="Here's the plan.")]),
        _R("tool_use", [_B(type="tool_use", id="t2", name="mark_cancelled", input={"subscription_id": sid})]),
        _R("end_turn", [_B(type="text", text="Marked as killed.")])])
    class FakeClient:
        class messages:
            @staticmethod
            def create(**kw): return next(script)
    monkeypatch.setattr(ai, "client", lambda: FakeClient)
    r = cl.post("/api/chat", json={"messages": [{"role": "user", "content": "cancel netflix"}]}).json()
    assert r["reply"] == "Here's the plan." and r["actions"][0]["type"] == "cancel_plan"
    assert cl.get("/api/subscriptions").json()[0]["status"] == "active"   # planning cancels nothing
    r = cl.post("/api/chat", json={"messages": [{"role": "user", "content": "done, got the confirmation"}]}).json()
    assert cl.get("/api/subscriptions?status=cancelled").json()[0]["id"] == sid

def test_bearer_token_auth(cl):
    t = cl.post("/api/signup", json={"email": "m@o.bi", "password": "password1"}).json()["token"]
    from fastapi.testclient import TestClient
    mobile = TestClient(cl.app, headers={"Authorization": f"Bearer {t}"})
    assert mobile.get("/api/me").json()["email"] == "m@o.bi"
    assert mobile.post("/api/chat", json={"messages": []}, headers={"X-SubKill": "1"}).status_code == 400

def test_invite_code_delete_account_and_caps(cl, monkeypatch):
    monkeypatch.setenv("SUBKILL_INVITE_CODE", "letmein")
    assert cl.post("/api/signup", json={"email": "i@x.co", "password": "password1"}).status_code == 403
    assert cl.post("/api/signup", json={"email": "i@x.co", "password": "password1", "invite": "nope"}).status_code == 403
    assert cl.post("/api/signup", json={"email": "i@x.co", "password": "password1", "invite": "letmein"}).status_code == 200
    cl.post("/api/demo/seed")
    monkeypatch.setenv("SUBKILL_DAILY_INGEST", "1")
    assert cl.post("/api/ingest/text", json={"text": "a"}).status_code == 200
    assert cl.post("/api/ingest/text", json={"text": "b"}).status_code == 429
    assert cl.delete("/api/account").status_code == 200
    assert cl.get("/api/me").status_code == 401
    from app import db
    assert db.conn().execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0] == 0
    assert db.conn().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0

def test_legal_pages_and_health(cl):
    assert cl.get("/healthz").json() == {"ok": True}
    assert "Privacy Policy" in cl.get("/privacy").text and "{{SUPPORT}}" not in cl.get("/privacy").text
    assert cl.get("/support").status_code == 200
