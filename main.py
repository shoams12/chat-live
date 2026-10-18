import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

from pathlib import Path

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

DB_PATH = "messages.db"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Chat", docs_url=None, redoc_url=None)


@app.get("/", include_in_schema=False)
def chat_page():
    return FileResponse(STATIC_DIR / "index.html")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                author TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


init_db()


class MessageCreate(BaseModel):
    author: str = Field(min_length=1)
    content: str = Field(min_length=1)


class MessagePatch(BaseModel):
    author: Optional[str] = Field(default=None, min_length=1)
    content: Optional[str] = Field(default=None, min_length=1)


class Message(MessageCreate):
    id: int
    created_at: str
    updated_at: str


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_message(db, message_id: int) -> Message:
    row = db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return Message(**dict(row))


@app.get("/messages", response_model=list[Message])
def list_messages():
    with get_db() as db:
        rows = db.execute("SELECT * FROM messages ORDER BY id").fetchall()
        return [Message(**dict(r)) for r in rows]


@app.get("/messages/{message_id}", response_model=Message)
def get_message(message_id: int):
    with get_db() as db:
        return fetch_message(db, message_id)


@app.post("/messages", response_model=Message, status_code=status.HTTP_201_CREATED)
def create_message(msg: MessageCreate):
    ts = now()
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO messages (author, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (msg.author, msg.content, ts, ts),
        )
        return fetch_message(db, cur.lastrowid)


@app.put("/messages/{message_id}", response_model=Message)
def replace_message(message_id: int, msg: MessageCreate):
    with get_db() as db:
        fetch_message(db, message_id)
        db.execute(
            "UPDATE messages SET author = ?, content = ?, updated_at = ? WHERE id = ?",
            (msg.author, msg.content, now(), message_id),
        )
        return fetch_message(db, message_id)


@app.patch("/messages/{message_id}", response_model=Message)
def update_message(message_id: int, msg: MessagePatch):
    changes = msg.model_dump(exclude_unset=True, exclude_none=True)
    with get_db() as db:
        fetch_message(db, message_id)
        if changes:
            changes["updated_at"] = now()
            assignments = ", ".join(f"{k} = ?" for k in changes)
            db.execute(
                f"UPDATE messages SET {assignments} WHERE id = ?",
                (*changes.values(), message_id),
            )
        return fetch_message(db, message_id)


@app.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(message_id: int):
    with get_db() as db:
        fetch_message(db, message_id)
        db.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
