import sqlite3
import json
import secrets
import bcrypt
from datetime import datetime, timezone
from pathlib import Path
 
DB_PATH = Path("app.db")
 
 
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
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
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            folder_id INTEGER,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (folder_id) REFERENCES folders(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            final_answer TEXT NOT NULL,
            turns_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES chats(id)
        )
    """)
    conn.commit()
    conn.close()
 
 
# ---------------------------------------------------------------------------
# Users & sessions
# ---------------------------------------------------------------------------
def create_user(username: str, password: str):
    username = username.strip()
    if not username or not password:
        return False, "Username and password are required."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
 
    conn = get_connection()
    if conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
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
 
 
def create_session(user_id: int) -> str:
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
 
 
# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------
def create_folder(user_id: int, name: str) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO folders (user_id, name, created_at) VALUES (?, ?, ?)",
        (user_id, name.strip(), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    folder_id = cur.lastrowid
    conn.close()
    return folder_id
 
 
def get_folders(user_id: int) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name FROM folders WHERE user_id = ? ORDER BY created_at ASC", (user_id,)
    ).fetchall()
    conn.close()
    return [{"id": r["id"], "name": r["name"]} for r in rows]
 
 
def delete_folder(user_id: int, folder_id: int):
    """Deletes the folder; chats inside it become unfiled rather than deleted."""
    conn = get_connection()
    conn.execute(
        "UPDATE chats SET folder_id = NULL WHERE folder_id = ? AND user_id = ?",
        (folder_id, user_id),
    )
    conn.execute("DELETE FROM folders WHERE id = ? AND user_id = ?", (folder_id, user_id))
    conn.commit()
    conn.close()
 
 
# ---------------------------------------------------------------------------
# Chats
# ---------------------------------------------------------------------------
def create_chat(user_id: int, folder_id: int = None, title: str = "New Chat") -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO chats (user_id, folder_id, title, created_at) VALUES (?, ?, ?, ?)",
        (user_id, folder_id, title, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    chat_id = cur.lastrowid
    conn.close()
    return chat_id
 
 
def get_chats(user_id: int) -> list:
    """All of this user's chats, newest first. folder_id is None for unfiled chats."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, folder_id, title, created_at FROM chats WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [{"id": r["id"], "folder_id": r["folder_id"], "title": r["title"]} for r in rows]
 
 
def get_chat(chat_id: int, user_id: int):
    """Returns the chat only if it belongs to this user -- the ownership check."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, folder_id, title FROM chats WHERE id = ? AND user_id = ?", (chat_id, user_id)
    ).fetchone()
    conn.close()
    return {"id": row["id"], "folder_id": row["folder_id"], "title": row["title"]} if row else None
 
 
def rename_chat(chat_id: int, user_id: int, new_title: str):
    conn = get_connection()
    conn.execute(
        "UPDATE chats SET title = ? WHERE id = ? AND user_id = ?", (new_title.strip(), chat_id, user_id)
    )
    conn.commit()
    conn.close()
 
 
def move_chat(chat_id: int, user_id: int, folder_id: int):
    """folder_id may be None to unfile the chat."""
    conn = get_connection()
    conn.execute(
        "UPDATE chats SET folder_id = ? WHERE id = ? AND user_id = ?", (folder_id, chat_id, user_id)
    )
    conn.commit()
    conn.close()
 
 
def delete_chat(chat_id: int, user_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM conversations WHERE chat_id = ?", (chat_id,))
    conn.execute("DELETE FROM chats WHERE id = ? AND user_id = ?", (chat_id, user_id))
    conn.commit()
    conn.close()
 
 
# ---------------------------------------------------------------------------
# Conversations (scoped to one chat thread)
# ---------------------------------------------------------------------------
def save_conversation(chat_id: int, question: str, final_answer: str, turns: list):
    conn = get_connection()
    conn.execute(
        "INSERT INTO conversations (chat_id, question, final_answer, turns_json, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (chat_id, question, final_answer, json.dumps(turns), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
 
 
def get_conversations(chat_id: int) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT question, final_answer, turns_json FROM conversations "
        "WHERE chat_id = ? ORDER BY id ASC",
        (chat_id,),
    ).fetchall()
    conn.close()
    return [
        {"question": r["question"], "final_answer": r["final_answer"], "turns": json.loads(r["turns_json"])}
        for r in rows
    ]
 
 
def get_recent_context(chat_id: int, n: int = 3) -> str:
    """Context is scoped to THIS chat only -- a new chat starts with no
    carried-over context, exactly like starting a fresh conversation."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT question, final_answer FROM conversations WHERE chat_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (chat_id, n),
    ).fetchall()
    conn.close()
    if not rows:
        return ""
    rows = list(reversed(rows))
    lines = ["Context from earlier in this conversation (for reference only):"]
    for r in rows:
        lines.append(f"- Q: {r['question']}\n  A: {r['final_answer'][:300]}")
    return "\n".join(lines)
 