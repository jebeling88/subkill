import hashlib, hmac, secrets
from fastapi import Cookie, Header, HTTPException
from . import db

def hash_pw(pw: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()

def create_user(email: str, pw: str):
    email = email.strip().lower()
    if "@" not in email or len(pw) < 8:
        raise HTTPException(400, "Use a valid email and a password of 8+ characters.")
    salt = secrets.token_hex(16)
    try:
        with db.tx() as c:
            cur = c.execute("INSERT INTO users(email,pw_hash,salt) VALUES(?,?,?)",
                            (email, hash_pw(pw, salt), salt))
            return cur.lastrowid
    except Exception:
        raise HTTPException(409, "That email is already registered.")

def verify_user(email: str, pw: str):
    row = db.conn().execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
    if not row or not hmac.compare_digest(row["pw_hash"], hash_pw(pw, row["salt"])):
        raise HTTPException(401, "Wrong email or password.")
    return row["id"]

def new_session(user_id: int) -> str:
    t = secrets.token_urlsafe(32)
    with db.tx() as c:
        c.execute("INSERT INTO sessions(token,user_id) VALUES(?,?)", (t, user_id))
    return t

def end_session(token: str):
    with db.tx() as c:
        c.execute("DELETE FROM sessions WHERE token=?", (token,))

def current_user(sk_session: str | None = Cookie(default=None), authorization: str | None = Header(default=None)):
    if not sk_session and authorization and authorization.lower().startswith("bearer "):
        sk_session = authorization[7:].strip()   # mobile apps send the session token as a Bearer token
    if sk_session:
        row = db.conn().execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?",
            (sk_session,)).fetchone()
        if row:
            return row
    raise HTTPException(401, "Not signed in.")
