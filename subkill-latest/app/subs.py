import json, re
from datetime import date, datetime, timedelta
from . import db

def norm(s): return re.sub(r"[^a-z0-9]+", "", (s or "").lower())
def key_for(merchant, plan): return norm(merchant) + "|" + norm(plan)
def today(): return date.today().isoformat()

def monthly_cents(amount_cents, cycle):
    f = {"weekly": 52 / 12, "monthly": 1, "quarterly": 1 / 3, "yearly": 1 / 12}.get(cycle, 1)
    return int(round(amount_cents * f))

def _d(s):
    try: return datetime.strptime((s or "")[:10], "%Y-%m-%d").date()
    except Exception: return None
def _dstr(s): return s if _d(s) else None

def upsert(user_id, item, source, owner="Me"):
    """Merge one extracted subscription into the DB. Returns 'new' | 'updated' | 'skipped'."""
    merchant = (item.get("merchant") or "").strip()[:80]
    try: amount = float(item.get("amount") or 0)
    except Exception: amount = 0
    if not merchant or amount <= 0:
        return "skipped"
    cycle = item.get("cycle") if item.get("cycle") in ("weekly", "monthly", "quarterly", "yearly") else "monthly"
    cents = int(round(amount * 100))
    status = item.get("status") if item.get("status") in ("active", "trial", "cancelled") else "active"
    cu = item.get("cancel_url") or ""
    cu = cu if re.match(r"^https://\S+$", cu) else None
    vals = dict(plan=(item.get("plan") or "")[:80], amount_cents=cents, currency=(item.get("currency") or "USD")[:3].upper(),
                cycle=cycle, monthly_cents=monthly_cents(cents, cycle), category=item.get("category") or "Other",
                started_at=_dstr(item.get("started_at")), last_charged_at=_dstr(item.get("last_charged_at")),
                last_used_at=_dstr(item.get("last_used_at")), next_renewal=_dstr(item.get("next_renewal")),
                cancel_url=cu, notes=(item.get("evidence") or "")[:200])
    k = key_for(merchant, vals["plan"])
    c = db.conn()
    row = c.execute("SELECT * FROM subscriptions WHERE user_id=? AND merchant_key=? AND owner=?",
                    (user_id, k, owner)).fetchone()
    with db.tx() as c:
        if not row:
            c.execute("""INSERT INTO subscriptions(user_id,merchant,merchant_key,owner,status,source,
                plan,amount_cents,currency,cycle,monthly_cents,category,started_at,last_charged_at,last_used_at,
                next_renewal,cancel_url,notes,cancelled_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (user_id, merchant, k, owner, status, source, vals["plan"], cents, vals["currency"], cycle,
                 vals["monthly_cents"], vals["category"], vals["started_at"], vals["last_charged_at"],
                 vals["last_used_at"], vals["next_renewal"], cu, vals["notes"],
                 today() if status == "cancelled" else None))
            return "new"
        new = {}
        # newest facts win, but never blank out what we already know
        for f, v in vals.items():
            if v not in (None, ""):
                new[f] = v
        for f in ("last_charged_at", "last_used_at"):  # keep the latest date
            if f in new and row[f] and row[f] > new[f]:
                new[f] = row[f]
        if "started_at" in new and row["started_at"] and row["started_at"] < new["started_at"]:
            new["started_at"] = row["started_at"]
        st = row["status"]
        if status == "cancelled" and st in ("active", "trial", "cancelling"):
            new["status"], new["cancelled_at"] = "cancelled", today()
        elif st == "trial" and status == "active":
            new["status"] = "active"
        # monitoring: a charge well after the kill means it didn't work
        if st in ("cancelling", "cancelled"):
            marker = _d(row["cancelled_at"]) or _d(row["cancel_requested_at"])
            lc = _d(new.get("last_charged_at"))
            if marker and lc and lc > marker + timedelta(days=3) and status != "cancelled":
                new["still_charging"] = 1
        if new:
            c.execute("UPDATE subscriptions SET " + ",".join(f"{k}=?" for k in new) + " WHERE id=?",
                      (*new.values(), row["id"]))
        return "updated"

SORTS = {
    "cost": "monthly_cents DESC",
    "unused": "COALESCE(last_used_at,'0000') ASC, monthly_cents DESC",
    "recent": "(last_used_at IS NULL), last_used_at DESC",
    "most_used": "use_count DESC, monthly_cents DESC",
    "oldest": "COALESCE(started_at, date(created_at)) ASC",
    "newest": "COALESCE(started_at, date(created_at)) DESC",
    "renewal": "(next_renewal IS NULL), next_renewal ASC",
    "name": "merchant COLLATE NOCASE ASC",
}

def list_subs(user_id, sort="cost", status="live", owner=None, category=None, cycle=None, q=None, unused=False):
    where, args = ["user_id=?"], [user_id]
    if status == "live": where.append("status IN ('active','trial','cancelling')")
    elif status in ("active", "trial", "cancelling", "cancelled"): where.append("status=?"); args.append(status)
    if owner: where.append("owner=?"); args.append(owner)
    if category: where.append("category=?"); args.append(category)
    if cycle: where.append("cycle=?"); args.append(cycle)
    if q: where.append("(merchant LIKE ? OR plan LIKE ?)"); args += [f"%{q}%"] * 2
    if unused:
        cutoff = (date.today() - timedelta(days=60)).isoformat()
        where.append("(last_used_at IS NULL OR last_used_at < ?)"); args.append(cutoff)
    order = SORTS.get(sort, SORTS["cost"])
    rows = db.conn().execute(f"SELECT * FROM subscriptions WHERE {' AND '.join(where)} ORDER BY {order}, id", args).fetchall()
    return [dict(r) for r in rows]

def summary(user_id):
    rows = [dict(r) for r in db.conn().execute("SELECT * FROM subscriptions WHERE user_id=?", (user_id,))]
    live = [r for r in rows if r["status"] in ("active", "trial", "cancelling")]
    cutoff = (date.today() - timedelta(days=60)).isoformat()
    unused = [r for r in live if not r["last_used_at"] or r["last_used_at"] < cutoff]
    soon = (date.today() + timedelta(days=7)).isoformat()
    cancelled = [r for r in rows if r["status"] == "cancelled"]
    by_owner = {}
    for r in live: by_owner[r["owner"]] = by_owner.get(r["owner"], 0) + r["monthly_cents"]
    return {
        "live_count": len(live), "monthly_cents": sum(r["monthly_cents"] for r in live),
        "yearly_cents": sum(r["monthly_cents"] for r in live) * 12,
        "unused_count": len(unused), "unused_monthly_cents": sum(r["monthly_cents"] for r in unused),
        "renewing_soon": sum(1 for r in live if r["next_renewal"] and today() <= r["next_renewal"] <= soon),
        "saved_yearly_cents": sum(r["monthly_cents"] for r in cancelled) * 12,
        "cancelled_count": len(cancelled),
        "still_charging": sum(1 for r in rows if r["still_charging"]),
        "by_owner": by_owner,
    }

def demo_seed(user_id):
    t = date.today()
    def ago(n): return (t - timedelta(days=n)).isoformat()
    def ahead(n): return (t + timedelta(days=n)).isoformat()
    demo = [
        ("Netflix", "Premium", 22.99, "monthly", "Streaming", "Me", 900, 12, 2, 20, 1),
        ("Disney+", "Bundle", 14.99, "monthly", "Streaming", "Kids", 700, 9, 140, 5, 0),
        ("Spotify", "Family", 19.99, "monthly", "Music", "Wife", 1500, 3, 1, 14, 85),
        ("Adobe Creative Cloud", "All Apps", 59.99, "monthly", "Software", "Me", 1100, 4, 200, 21, 0),
        ("Planet Fitness", "Black Card", 24.99, "monthly", "Fitness/Health", "Me", 1300, 11, 190, 8, 0),
        ("Amazon Prime", "", 139.00, "yearly", "Shopping/Membership", "Wife", 1800, 40, 3, 190, 60),
        ("iCloud+", "2TB", 9.99, "monthly", "Cloud/Storage", "Me", 1000, 6, 0, 17, 300),
        ("Xbox Game Pass", "Ultimate", 19.99, "monthly", "Gaming", "Kids", 400, 7, 75, 26, 6),
        ("Duolingo", "Super", 83.99, "yearly", "Education/Kids", "Kids", 350, 22, 120, 260, 0),
        ("NYTimes", "Digital", 25.00, "monthly", "News/Reading", "Wife", 600, 2, 95, 2, 0),
        ("HelloFresh", "4 meals", 71.88, "weekly", "Food/Delivery", "Wife", 250, 5, 60, 3, 2),
        ("Calm", "Annual", 69.99, "yearly", "Fitness/Health", "Wife", 500, 33, 210, 150, 0),
        ("Dropbox", "Plus", 11.99, "monthly", "Cloud/Storage", "Me", 1400, 15, 260, 11, 0),
        ("Hulu", "No Ads", 18.99, "monthly", "Streaming", "Me", 800, 1, 33, 29, 0),
    ]
    for m, p, a, cy, cat, own, started, cnt, used_ago, renew, _ in demo:
        upsert(user_id, dict(merchant=m, plan=p, amount=a, cycle=cy, category=cat, started_at=ago(started),
               last_charged_at=ago(max(1, 30 - renew) if cy == "monthly" else 20), next_renewal=ahead(renew % 28 + 1),
               last_used_at=ago(used_ago) if used_ago < 250 else "", status="active"), "demo", own)
        db.conn().execute("UPDATE subscriptions SET use_count=? WHERE user_id=? AND merchant=?", (cnt, user_id, m))
    db.conn().commit()
    db.conn().execute("UPDATE users SET members=? WHERE id=?", (json.dumps(["Me", "Wife", "Kids"]), user_id))
    db.conn().commit()
