import sqlite3
import json
import bcrypt
from datetime import datetime, timezone
from pathlib import Path
import secrets

DB_PATH = Path("app.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            final_answer TEXT NOT NULL,
            turns_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()

def create_user(username: str, password: str):
    """Returns (success: bool, message: str)."""
    username = username.strip()
    if not username or not password:
        return False, "Username and password are required."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    conn = get_connection()
    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        conn.close()
        return False, "That username is already taken."

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    conn.execute(
        "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
        (username, password_hash, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    return True, "Account created. You can log in now."


def authenticate_user(username: str, password: str):
    """Returns {'id': ..., 'username': ...} on success, or None on failure."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, username, password_hash FROM users WHERE username = ?", (username.strip(),)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    if bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8")):
        return {"id": row["id"], "username": row["username"]}
    return None


def save_conversation(user_id: int, question: str, final_answer: str, turns: list):
    conn = get_connection()
    conn.execute(
        "INSERT INTO conversations (user_id, question, final_answer, turns_json, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, question, final_answer, json.dumps(turns), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def get_conversations(user_id: int) -> list:
    """This user's past conversations, oldest first. Always filtered by
    user_id -- this WHERE clause is what guarantees isolation between users."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT question, final_answer, turns_json, created_at FROM conversations "
        "WHERE user_id = ? ORDER BY id ASC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "question": r["question"],
            "final_answer": r["final_answer"],
            "turns": json.loads(r["turns_json"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def get_recent_context(user_id: int, n: int = 3) -> str:
    conn = get_connection()
    rows = conn.execute(
        "SELECT question, final_answer FROM conversations WHERE user_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (user_id, n),
    ).fetchall()
    conn.close()
    if not rows:
        return ""
    rows = list(reversed(rows))
    lines = ["Context from earlier conversations (for reference only):"]
    for r in rows:
        lines.append(f"- Q: {r['question']}\n  A: {r['final_answer'][:300]}")
    return "\n".join(lines)

def create_session(user_id: int) -> str:
    """Generates a random token and ties it to this user, so a page refresh
    can re-authenticate without asking for the password again."""
    token = secrets.token_urlsafe(32)
    conn = get_connection()
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
        (token, user_id, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    return token


def get_user_by_session(token: str):
    conn = get_connection()
    row = conn.execute(
        "SELECT u.id, u.username FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
        (token,),
    ).fetchone()
    conn.close()
    return {"id": row["id"], "username": row["username"]} if row else None


def delete_session(token: str):
    conn = get_connection()
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()    