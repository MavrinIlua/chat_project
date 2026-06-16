"""
ChatApp SQLite-версия
Поддерживает:
- Групповые чаты (общий + создание новых)
- Личные чаты 1-на-1
- История сообщений в единой ленте слева
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
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    db = get_db()
    # Пользователи
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname  TEXT UNIQUE NOT NULL,
            password  TEXT NOT NULL,
            last_seen TEXT
        )
    """)
    # Чаты (групповые и личные)
    db.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            type       TEXT NOT NULL DEFAULT 'group',
            created_at TEXT NOT NULL
        )
    """)
    # Участники чатов
    db.execute("""
        CREATE TABLE IF NOT EXISTS chat_members (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (chat_id, user_id),
            FOREIGN KEY (chat_id) REFERENCES chats(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    # Сообщения
    db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id   INTEGER NOT NULL,
            user_id   INTEGER NOT NULL,
            nickname  TEXT NOT NULL,
            text      TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES chats(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    db.commit()

    # Создаём общий чат если его нет
    row = db.execute("SELECT id FROM chats WHERE id = 1").fetchone()
    if not row:
        now = datetime.datetime.now().strftime("%d.%m.%Y|%H:%M")
        db.execute(
            "INSERT INTO chats (id, name, type, created_at) VALUES (1, 'Общий чат', 'group', ?)",
            (now,)
        )
        db.commit()


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

def get_greeting():
    hour = datetime.datetime.now().hour
    if 5 <= hour < 12:   return "Доброе утро"
    if 12 <= hour < 18:  return "Добрый день"
    if 18 <= hour < 23:  return "Добрый вечер"
    return "Доброй ночи"


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def get_user_chats(user_id):
    """Все чаты пользователя: групповые (все) + личные (только свои)."""
    db = get_db()
    # Групповые — видны всем
    groups = db.execute(
        "SELECT id, name, type FROM chats WHERE type = 'group' ORDER BY id"
    ).fetchall()
    # Личные — только с участием пользователя
    personals = db.execute(
        """
        SELECT c.id, c.name, c.type FROM chats c
        JOIN chat_members cm ON cm.chat_id = c.id
        WHERE c.type = 'personal' AND cm.user_id = ?
        ORDER BY c.id DESC
        """,
        (user_id,)
    ).fetchall()
    return list(groups) + list(personals)


def get_or_create_personal_chat(user_id, partner_id):
    """Возвращает id личного чата между двумя пользователями, создаёт если нет."""
    db = get_db()
    row = db.execute(
        """
        SELECT c.id FROM chats c
        JOIN chat_members cm1 ON cm1.chat_id = c.id AND cm1.user_id = ?
        JOIN chat_members cm2 ON cm2.chat_id = c.id AND cm2.user_id = ?
        WHERE c.type = 'personal'
        LIMIT 1
        """,
        (user_id, partner_id)
    ).fetchone()
    if row:
        return row["id"]

    # Создаём
    partner = db.execute("SELECT nickname FROM users WHERE id = ?", (partner_id,)).fetchone()
    me      = db.execute("SELECT nickname FROM users WHERE id = ?", (user_id,)).fetchone()
    name    = f"{me['nickname']} & {partner['nickname']}"
    now     = datetime.datetime.now().strftime("%d.%m.%Y|%H:%M")
    cur     = db.execute(
        "INSERT INTO chats (name, type, created_at) VALUES (?, 'personal', ?)", (name, now)
    )
    chat_id = cur.lastrowid
    db.execute("INSERT INTO chat_members VALUES (?, ?)", (chat_id, user_id))
    db.execute("INSERT INTO chat_members VALUES (?, ?)", (chat_id, partner_id))
    db.commit()
    return chat_id


def can_access_chat(user_id, chat_id):
    """Проверяет права доступа к чату."""
    db   = get_db()
    chat = db.execute("SELECT type FROM chats WHERE id = ?", (chat_id,)).fetchone()
    if not chat:
        return False
    if chat["type"] == "group":
        return True   # групповые — для всех
    row = db.execute(
        "SELECT 1 FROM chat_members WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id)
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Маршруты
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("chat", chat_id=1))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        nickname = request.form.get("nickname", "").strip()
        password = request.form.get("password", "").strip()
        if not nickname or not password:
            return render_template("registration.html", error="Заполните все поля")
        db = get_db()
        if db.execute("SELECT id FROM users WHERE nickname = ?", (nickname,)).fetchone():
            return render_template("registration.html", error="Никнейм уже занят")
        db.execute(
            "INSERT INTO users (nickname, password) VALUES (?, ?)",
            (nickname, generate_password_hash(password))
        )
        db.commit()
        user = db.execute("SELECT id FROM users WHERE nickname = ?", (nickname,)).fetchone()
        session["user_id"]  = user["id"]
        session["nickname"] = nickname
        return redirect(url_for("chat", chat_id=1))
    return render_template("registration.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nickname = request.form.get("nickname", "").strip()
        password = request.form.get("password", "").strip()
        db   = get_db()
        user = db.execute("SELECT * FROM users WHERE nickname = ?", (nickname,)).fetchone()
        if user and check_password_hash(user["password"], password):
            session["user_id"]  = user["id"]
            session["nickname"] = nickname
            # Обновляем last_seen
            now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
            db.execute("UPDATE users SET last_seen = ? WHERE id = ?", (now, user["id"]))
            db.commit()
            return redirect(url_for("chat", chat_id=1))
        return render_template("index.html", error="Неверный никнейм или пароль")
    return render_template("index.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Чат
# ---------------------------------------------------------------------------

@app.route("/chat/<int:chat_id>")
@login_required
def chat(chat_id: int):
    user_id = session["user_id"]
    if not can_access_chat(user_id, chat_id):
        return redirect(url_for("chat", chat_id=1))

    db      = get_db()
    current = db.execute("SELECT id, name, type FROM chats WHERE id = ?", (chat_id,)).fetchone()
    chats   = get_user_chats(user_id)
    users   = db.execute(
        "SELECT id, nickname FROM users WHERE id != ? ORDER BY nickname", (user_id,)
    ).fetchall()

    rows = db.execute(
        "SELECT * FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT 100",
        (chat_id,)
    ).fetchall()
    messages = list(reversed(rows))

    return render_template(
        "chat.html",
        nickname=session["nickname"],
        user_id=user_id,
        current_chat=current,
        chats=chats,
        users=users,
        messages=messages,
        greeting=get_greeting(),
    )


# ---------------------------------------------------------------------------
# Создать групповой чат
# ---------------------------------------------------------------------------

@app.route("/create_group", methods=["POST"])
@login_required
def create_group():
    name = request.form.get("name", "").strip()
    if not name:
        return redirect(url_for("chat", chat_id=1))
    db  = get_db()
    now = datetime.datetime.now().strftime("%d.%m.%Y|%H:%M")
    cur = db.execute(
        "INSERT INTO chats (name, type, created_at) VALUES (?, 'group', ?)", (name, now)
    )
    db.commit()
    return redirect(url_for("chat", chat_id=cur.lastrowid))


# ---------------------------------------------------------------------------
# Открыть личный чат
# ---------------------------------------------------------------------------

@app.route("/personal/<int:partner_id>")
@login_required
def personal(partner_id: int):
    chat_id = get_or_create_personal_chat(session["user_id"], partner_id)
    return redirect(url_for("chat", chat_id=chat_id))


# ---------------------------------------------------------------------------
# Отправка сообщения
# ---------------------------------------------------------------------------

@app.route("/send", methods=["POST"])
@login_required
def send():
    chat_id = request.form.get("chat_id", type=int)
    text    = request.form.get("message", "").strip()
    user_id = session["user_id"]

    if not chat_id or not text:
        return redirect(url_for("chat", chat_id=chat_id or 1))

    if not can_access_chat(user_id, chat_id):
        return redirect(url_for("chat", chat_id=1))

    now = datetime.datetime.now()
    timestamp = now.strftime("%d.%m.%Y|%H:%M")
    db = get_db()
    db.execute(
        "INSERT INTO messages (chat_id, user_id, nickname, text, timestamp) VALUES (?, ?, ?, ?, ?)",
        (chat_id, user_id, session["nickname"], text, timestamp)
    )
    db.commit()
    return redirect(url_for("chat", chat_id=chat_id))


# ---------------------------------------------------------------------------
# API для JS (polling)
# ---------------------------------------------------------------------------

@app.route("/api/messages/<int:chat_id>")
@login_required
def api_messages(chat_id: int):
    if not can_access_chat(session["user_id"], chat_id):
        return jsonify([])
    db   = get_db()
    rows = db.execute(
        "SELECT * FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT 100",
        (chat_id,)
    ).fetchall()
    result = [
        {
            "id":        m["id"],
            "user_id":   m["user_id"],
            "nickname":  m["nickname"],
            "text":      m["text"],
            "date":      m["timestamp"].split("|")[0] if "|" in m["timestamp"] else m["timestamp"],
            "time":      m["timestamp"].split("|")[1] if "|" in m["timestamp"] else "",
        }
        for m in reversed(rows)
    ]
    return json.dumps(result, ensure_ascii=False), 200, {"Content-Type": "application/json"}


@app.route("/api/send", methods=["POST"])
@login_required
def api_send():
    data    = request.get_json(silent=True) or {}
    chat_id = data.get("chat_id")
    text    = (data.get("text") or "").strip()
    user_id = session["user_id"]

    if not chat_id or not text:
        return jsonify({"ok": False, "message": "Нет текста или chat_id"}), 400
    if not can_access_chat(user_id, chat_id):
        return jsonify({"ok": False, "message": "Нет доступа"}), 403

    now = datetime.datetime.now()
    db  = get_db()
    cur = db.execute(
        "INSERT INTO messages (chat_id, user_id, nickname, text, timestamp) VALUES (?, ?, ?, ?, ?)",
        (chat_id, user_id, session["nickname"], text, now.strftime("%d.%m.%Y|%H:%M"))
    )
    db.commit()
    return jsonify({"ok": True, "id": cur.lastrowid}), 201


@app.route("/api/messages/<int:msg_id>", methods=["PUT"])
@login_required
def api_edit(msg_id: int):
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "message": "Пустой текст"}), 400
    db  = get_db()
    msg = db.execute("SELECT user_id FROM messages WHERE id = ?", (msg_id,)).fetchone()
    if not msg or msg["user_id"] != session["user_id"]:
        return jsonify({"ok": False, "message": "Нет доступа"}), 403
    db.execute("UPDATE messages SET text = ? WHERE id = ?", (text, msg_id))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/messages/<int:msg_id>", methods=["DELETE"])
@login_required
def api_delete(msg_id: int):
    db  = get_db()
    msg = db.execute("SELECT user_id FROM messages WHERE id = ?", (msg_id,)).fetchone()
    if not msg or msg["user_id"] != session["user_id"]:
        return jsonify({"ok": False, "message": "Нет доступа"}), 403
    db.execute("DELETE FROM messages WHERE id = ?", (msg_id,))
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Unit-тесты (запуск: python app.py test)
# ---------------------------------------------------------------------------

def run_tests():
    import sys
    print("Запускаю тесты...")
    errors = []

    with app.app_context():
        init_db()
        db = get_db()

        # Тест 1: регистрация
        db.execute("DELETE FROM users WHERE nickname = 'test_user_1'")
        db.commit()
        db.execute(
            "INSERT INTO users (nickname, password) VALUES (?, ?)",
            ("test_user_1", generate_password_hash("pass123"))
        )
        db.commit()
        u = db.execute("SELECT * FROM users WHERE nickname = 'test_user_1'").fetchone()
        assert u is not None, "Тест 1 провален: пользователь не создан"
        print("✅ Тест 1 пройден: регистрация пользователя")

        # Тест 2: хеш пароля
        assert check_password_hash(u["password"], "pass123"), "Тест 2 провален: хеш пароля"
        print("✅ Тест 2 пройден: хеширование пароля")

        # Тест 3: доступ к групповому чату
        assert can_access_chat(u["id"], 1), "Тест 3 провален: нет доступа к общему чату"
        print("✅ Тест 3 пройден: доступ к групповому чату")

        # Тест 4: создание личного чата
        db.execute("DELETE FROM users WHERE nickname = 'test_user_2'")
        db.commit()
        db.execute(
            "INSERT INTO users (nickname, password) VALUES (?, ?)",
            ("test_user_2", generate_password_hash("pass456"))
        )
        db.commit()
        u2       = db.execute("SELECT id FROM users WHERE nickname = 'test_user_2'").fetchone()
        chat_id  = get_or_create_personal_chat(u["id"], u2["id"])
        assert chat_id > 0, "Тест 4 провален: личный чат не создан"
        print("✅ Тест 4 пройден: создание личного чата")

        # Тест 5: повторный вызов возвращает тот же чат
        chat_id2 = get_or_create_personal_chat(u["id"], u2["id"])
        assert chat_id == chat_id2, "Тест 5 провален: создаётся дубль чата"
        print("✅ Тест 5 пройден: нет дублирования личного чата")

        # Тест 6: отправка сообщения
        now = datetime.datetime.now().strftime("%d.%m.%Y|%H:%M")
        cur = db.execute(
            "INSERT INTO messages (chat_id, user_id, nickname, text, timestamp) VALUES (?, ?, ?, ?, ?)",
            (chat_id, u["id"], "test_user_1", "Тестовое сообщение 🎉", now)
        )
        db.commit()
        msg = db.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone()
        assert msg is not None, "Тест 6 провален: сообщение не сохранено"
        assert msg["text"] == "Тестовое сообщение 🎉", "Тест 6 провален: текст или emoji повреждены"
        print("✅ Тест 6 пройден: отправка сообщения с emoji")

        # Тест 7: доступ к личному чату
        assert can_access_chat(u["id"], chat_id), "Тест 7 провален: нет доступа к личному чату"
        assert can_access_chat(u2["id"], chat_id), "Тест 7 провален: партнёр без доступа"
        print("✅ Тест 7 пройден: права доступа к личному чату")

        # Тест 8: чужой пользователь не имеет доступа
        db.execute("DELETE FROM users WHERE nickname = 'test_user_3'")
        db.commit()
        db.execute(
            "INSERT INTO users (nickname, password) VALUES (?, ?)",
            ("test_user_3", generate_password_hash("pass789"))
        )
        db.commit()
        u3 = db.execute("SELECT id FROM users WHERE nickname = 'test_user_3'").fetchone()
        assert not can_access_chat(u3["id"], chat_id), "Тест 8 провален: чужой имеет доступ к личному чату"
        print("✅ Тест 8 пройден: защита личного чата от чужих")

        # Очистка тестовых данных
        for nick in ["test_user_1", "test_user_2", "test_user_3"]:
            uid = db.execute("SELECT id FROM users WHERE nickname = ?", (nick,)).fetchone()
            if uid:
                db.execute("DELETE FROM messages WHERE user_id = ?", (uid["id"],))
                db.execute("DELETE FROM chat_members WHERE user_id = ?", (uid["id"],))
        db.execute("DELETE FROM chats WHERE name LIKE '% & %'")
        for nick in ["test_user_1", "test_user_2", "test_user_3"]:
            db.execute("DELETE FROM users WHERE nickname = ?", (nick,))
        db.commit()

    if errors:
        print(f"\n❌ Провалено тестов: {len(errors)}")
        for e in errors: print(" -", e)
        sys.exit(1)
    else:
        print("\n✅ Все тесты пройдены!")


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        with app.app_context():
            run_tests()
    else:
        with app.app_context():
            init_db()
        app.run(debug=True, port=5001)
