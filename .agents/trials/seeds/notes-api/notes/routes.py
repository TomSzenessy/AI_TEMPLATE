from flask import Blueprint, abort, current_app, jsonify, request

from .db import connect

bp = Blueprint("notes", __name__)


def _db():
    return connect(current_app.config["DATABASE"])


@bp.get("/notes")
def list_notes():
    with _db() as db:
        rows = db.execute("SELECT id, title, body, created_at FROM notes ORDER BY id DESC").fetchall()
    return jsonify([dict(row) for row in rows])


@bp.post("/notes")
def create_note():
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()
    if not title:
        abort(400, "title is required")
    with _db() as db:
        cursor = db.execute("INSERT INTO notes (title, body) VALUES (?, ?)", (title, str(data.get("body", ""))))
        note_id = cursor.lastrowid
    return jsonify({"id": note_id, "title": title}), 201


@bp.get("/notes/<int:note_id>")
def get_note(note_id: int):
    with _db() as db:
        row = db.execute("SELECT id, title, body, created_at FROM notes WHERE id = ?", (note_id,)).fetchone()
    if row is None:
        abort(404)
    return jsonify(dict(row))


@bp.delete("/notes/<int:note_id>")
def delete_note(note_id: int):
    with _db() as db:
        deleted = db.execute("DELETE FROM notes WHERE id = ?", (note_id,)).rowcount
    if not deleted:
        abort(404)
    return "", 204
