"""
ChatApp — SQLite-версия
Групповой чат + личные переписки 1-на-1.
Поддержка emoji через utf-8.
"""

import json
import sqlite3
import datetime
from functools import wraps
from flask import (
    Flask, g, jsonify, redirect, render_template,
    request, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "secret123"

# ---------------------------------------------------------------------------
# База данных
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect("chat.db")
        g.db.row_factory = sqlite3.Row
        # Включаем поддержку utf-8 / emoji
        g.db.execute("PRAGMA encoding = 'UTF-8'")
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    # Таблица пользователей
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    # Групповые сообщения
    db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname  TEXT NOT NULL,
            text      TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    # Личные сообщения 1-на-1
    db.execute("""
        CREATE TABLE IF NOT EXISTS direct_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id   INTEGER NOT NULL,
            deliver_id INTEGER NOT NULL,
            text       TEXT NOT NULL,
            sent_date  TEXT NOT NULL,
            sent_time  TEXT NOT NULL
        )
    """)
    db.commit()


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

def get_greeting():
    hour = datetime.datetime.now().hour
    if 5 <= hour < 12:  return "Доброе утро"
    elif 12 <= hour < 18: return "Добрый день"
    elif 18 <= hour < 23: return "Добрый вечер"
    return "Доброй ночи"


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "nickname" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Страницы — Вход / Регистрация
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    if "nickname" in session:
        return redirect(url_for("chat"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        nickname = request.form.get("nickname", "").strip()
        password = request.form.get("password", "").strip()
        if not nickname or not password:
            return render_template("registration.html", error="Заполните все поля")
        db = get_db()
        if db.execute("SELECT id FROM users WHERE nickname=?", (nickname,)).fetchone():
            return render_template("registration.html", error="Никнейм уже занят")
        db.execute("INSERT INTO users (nickname, password) VALUES (?,?)",
                   (nickname, generate_password_hash(password)))
        db.commit()
        session["nickname"] = nickname
        session["user_id"]  = db.execute(
            "SELECT id FROM users WHERE nickname=?", (nickname,)
        ).fetchone()["id"]
        return redirect(url_for("chat"))
    return render_template("registration.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nickname = request.form.get("nickname", "").strip()
        password = request.form.get("password", "").strip()
        db   = get_db()
        user = db.execute("SELECT * FROM users WHERE nickname=?", (nickname,)).fetchone()
        if user and check_password_hash(user["password"], password):
            session["nickname"] = nickname
            session["user_id"]  = user["id"]
            return redirect(url_for("chat"))
        return render_template("index.html", error="Неверный никнейм или пароль")
    return render_template("index.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Групповой чат
# ---------------------------------------------------------------------------

@app.route("/chat")
@login_required
def chat():
    db   = get_db()
    rows = db.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 100").fetchall()
    # Список всех пользователей для перехода в личный чат
    users = db.execute(
        "SELECT id, nickname FROM users WHERE nickname != ? ORDER BY nickname",
        (session["nickname"],)
    ).fetchall()
    return render_template(
        "chat.html",
        nickname=session["nickname"],
        messages=list(reversed(rows)),
        greeting=get_greeting(),
        users=users,
    )


@app.route("/send", methods=["POST"])
@login_required
def send():
    text = request.form.get("message", "").strip()
    if text:
        now = datetime.datetime.now()
        db  = get_db()
        db.execute(
            "INSERT INTO messages (nickname, text, timestamp) VALUES (?,?,?)",
            (session["nickname"], text, now.strftime("%d.%m.%Y|%H:%M"))
        )
        db.commit()
    return redirect(url_for("chat"))


@app.route("/messages")
@login_required
def get_messages():
    db   = get_db()
    rows = db.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 100").fetchall()
    result = [{"nickname": m["nickname"], "text": m["text"],
               "timestamp": m["timestamp"]} for m in reversed(rows)]
    return json.dumps(result, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Личный чат 1-на-1
# ---------------------------------------------------------------------------

@app.route("/direct/<int:partner_id>")
@login_required
def direct(partner_id):
    db      = get_db()
    me_id   = session["user_id"]
    partner = db.execute("SELECT id, nickname FROM users WHERE id=?",
                         (partner_id,)).fetchone()
    if not partner:
        return redirect(url_for("chat"))

    users = db.execute(
        "SELECT id, nickname FROM users WHERE nickname != ? ORDER BY nickname",
        (session["nickname"],)
    ).fetchall()

    return render_template(
        "direct.html",
        me_id=me_id,
        me_nickname=session["nickname"],
        partner=partner,
        users=users,
        greeting=get_greeting(),
    )


@app.route("/api/direct/<int:partner_id>", methods=["GET"])
@login_required
def api_direct_get(partner_id):
    db    = get_db()
    me_id = session["user_id"]
    rows  = db.execute("""
        SELECT id, owner_id, deliver_id, text, sent_date, sent_time
        FROM direct_messages
        WHERE (owner_id=? AND deliver_id=?) OR (owner_id=? AND deliver_id=?)
        ORDER BY id ASC LIMIT 200
    """, (me_id, partner_id, partner_id, me_id)).fetchall()
    result = [dict(r) for r in rows]
    return json.dumps(result, ensure_ascii=False)


@app.route("/api/direct/<int:partner_id>", methods=["POST"])
@login_required
def api_direct_send(partner_id):
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"ok": False}), 400
    me_id = session["user_id"]
    now   = datetime.datetime.now()
    db    = get_db()
    db.execute(
        "INSERT INTO direct_messages (owner_id, deliver_id, text, sent_date, sent_time) VALUES (?,?,?,?,?)",
        (me_id, partner_id, text, now.strftime("%d.%m.%Y"), now.strftime("%H:%M"))
    )
    db.commit()
    return jsonify({"ok": True}), 201


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(debug=True, port=5001)  # SQLite-версия: http://127.0.0.1:5001
