"""
ChatApp — MySQL-версия
Работает в двух режимах:
  1. С MySQL (если сервер доступен)
  2. Без БД — данные хранятся в памяти приложения (_temp_users, _temp_messages)
"""

import os
import datetime
from functools import wraps

from flask import (
    Flask, g, jsonify, redirect, render_template,
    request, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash

# ---------------------------------------------------------------------------
# Инициализация
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "secret123")

# Временное хранилище (используется когда MySQL недоступен)
_temp_users    = []   # [{id, name, surname, login, password_hash}]
_temp_messages = []   # [{id, owner_id, deliver_id, text, date, time}]

# ---------------------------------------------------------------------------
# Подключение к MySQL
# ---------------------------------------------------------------------------

def get_db():
    """Возвращает соединение с MySQL или None если сервер недоступен."""
    if "db" in g:
        return g.db
    try:
        import mysql.connector
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST", "185.114.247.43"),
            database=os.getenv("DB_NAME", "sch688_maga1"),
            user=os.getenv("DB_USER", "sch688_maga1"),
            password=os.getenv("DB_PASSWORD", "Fqx8irSU"),
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
            connection_timeout=3,
        )
        g.db = conn
        return g.db
    except Exception:
        g.db = None
        return None


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        try:
            if db.is_connected():
                db.close()
        except Exception:
            pass


def query(sql, params=(), *, one=False, commit=False):
    """SQL-запрос к MySQL. Возвращает None если БД недоступна."""
    db = get_db()
    if db is None:
        return None
    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute(sql, params)
        if commit:
            db.commit()
            last_id = cursor.lastrowid
            cursor.close()
            return last_id
        result = cursor.fetchone() if one else cursor.fetchall()
        cursor.close()
        return result
    except Exception:
        return None


def using_db():
    """True если MySQL доступен."""
    return get_db() is not None

# ---------------------------------------------------------------------------
# Инициализация таблиц
# ---------------------------------------------------------------------------

def init_db():
    db = get_db()
    if db is None:
        return
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            name       VARCHAR(64)  NOT NULL,
            surname    VARCHAR(64)  NOT NULL,
            login      VARCHAR(64)  NOT NULL UNIQUE,
            password   VARCHAR(256) NOT NULL,
            created_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            owner_id   INT  NOT NULL,
            deliver_id INT  NOT NULL,
            text       TEXT NOT NULL,
            sent_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id)   REFERENCES users(id),
            FOREIGN KEY (deliver_id) REFERENCES users(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    db.commit()
    cursor.close()

# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

def get_greeting():
    hour = datetime.datetime.now().hour
    if 5 <= hour < 12:
        return "Доброе утро"
    elif 12 <= hour < 18:
        return "Добрый день"
    elif 18 <= hour < 23:
        return "Добрый вечер"
    return "Доброй ночи"


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def _next_temp_id(lst):
    return max((x["id"] for x in lst), default=0) + 1

# ---------------------------------------------------------------------------
# Страницы — Регистрация / Вход / Выход
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("users_list"))
    return redirect(url_for("register"))


@app.route("/register")
def register():
    return render_template("registration.html")


@app.route("/login")
def login():
    return render_template("avtorization.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------------------------------------------------------------------
# API — Регистрация
# ---------------------------------------------------------------------------

@app.route("/api/register", methods=["POST"])
def api_register():
    data     = request.get_json(silent=True) or {}
    name     = data.get("name", "").strip()
    surname  = data.get("surname", "").strip()
    login_   = data.get("login", "").strip()
    password = data.get("password", "").strip()

    if not all([name, surname, login_, password]):
        return jsonify({"ok": False, "message": "Заполните все поля"}), 400
    if len(password) < 6:
        return jsonify({"ok": False, "message": "Пароль — минимум 6 символов"}), 400

    hashed = generate_password_hash(password)

    if using_db():
        # --- Режим MySQL ---
        if query("SELECT id FROM users WHERE login = %s", (login_,), one=True):
            return jsonify({"ok": False, "message": "Логин уже занят"}), 409
        user_id = query(
            "INSERT INTO users (name, surname, login, password) VALUES (%s,%s,%s,%s)",
            (name, surname, login_, hashed), commit=True,
        )
    else:
        # --- Режим без БД ---
        if any(u["login"] == login_ for u in _temp_users):
            return jsonify({"ok": False, "message": "Логин уже занят"}), 409
        user_id = _next_temp_id(_temp_users)
        _temp_users.append({
            "id": user_id, "name": name, "surname": surname,
            "login": login_, "password": hashed,
        })

    session["user_id"]      = user_id
    session["user_login"]   = login_
    session["user_name"]    = name
    session["user_surname"] = surname
    return jsonify({"ok": True, "user_id": user_id}), 201

# ---------------------------------------------------------------------------
# API — Авторизация
# ---------------------------------------------------------------------------

@app.route("/api/login", methods=["POST"])
def api_login():
    data     = request.get_json(silent=True) or {}
    login_   = data.get("login", "").strip()
    password = data.get("password", "").strip()

    if not login_ or not password:
        return jsonify({"ok": False, "message": "Введите логин и пароль"}), 400

    if using_db():
        # --- Режим MySQL ---
        user = query(
            "SELECT id, name, surname, login, password FROM users WHERE login = %s",
            (login_,), one=True,
        )
        if not user or not check_password_hash(user["password"], password):
            return jsonify({"ok": False, "message": "Неверный логин или пароль"}), 401
        uid, name, surname = user["id"], user["name"], user["surname"]
    else:
        # --- Режим без БД ---
        user = next((u for u in _temp_users if u["login"] == login_), None)
        if not user or not check_password_hash(user["password"], password):
            return jsonify({"ok": False, "message": "Неверный логин или пароль"}), 401
        uid, name, surname = user["id"], user["name"], user["surname"]

    session["user_id"]      = uid
    session["user_login"]   = login_
    session["user_name"]    = name
    session["user_surname"] = surname
    return jsonify({"ok": True, "user_id": uid}), 200

# ---------------------------------------------------------------------------
# Список пользователей
# ---------------------------------------------------------------------------

@app.route("/users")
@login_required
def users_list():
    me_id = session["user_id"]
    if using_db():
        users = query(
            "SELECT id, name, surname, login FROM users WHERE id != %s ORDER BY name",
            (me_id,),
        ) or []
    else:
        users = [
            {"id": u["id"], "name": u["name"], "surname": u["surname"], "login": u["login"]}
            for u in _temp_users if u["id"] != me_id
        ]
    me = {
        "id": me_id, "name": session["user_name"],
        "surname": session["user_surname"], "login": session["user_login"],
    }
    greeting = get_greeting()
    return render_template("users.html", users=users, me=me, greeting=greeting)

# ---------------------------------------------------------------------------
# Чат 1-на-1
# ---------------------------------------------------------------------------

@app.route("/chat/<int:partner_id>")
@login_required
def chat(partner_id: int):
    me_id = session["user_id"]
    if using_db():
        partner = query(
            "SELECT id, name, surname, login FROM users WHERE id = %s",
            (partner_id,), one=True,
        )
        users = query(
            "SELECT id, name, surname, login FROM users WHERE id != %s ORDER BY name",
            (me_id,),
        ) or []
    else:
        partner = next(
            ({"id": u["id"], "name": u["name"], "surname": u["surname"], "login": u["login"]}
             for u in _temp_users if u["id"] == partner_id),
            None,
        )
        users = [
            {"id": u["id"], "name": u["name"], "surname": u["surname"], "login": u["login"]}
            for u in _temp_users if u["id"] != me_id
        ]

    if not partner:
        return redirect(url_for("users_list"))

    me = {
        "id": me_id, "name": session["user_name"],
        "surname": session["user_surname"], "login": session["user_login"],
    }
    greeting = get_greeting()
    return render_template("chat.html", me=me, partner=partner, users=users, greeting=greeting)

# ---------------------------------------------------------------------------
# API — Сообщения
# ---------------------------------------------------------------------------

@app.route("/api/messages/<int:partner_id>", methods=["GET"])
@login_required
def api_get_messages(partner_id: int):
    me_id = session["user_id"]
    if using_db():
        messages = query(
            """
            SELECT m.id, m.owner_id, m.deliver_id, m.text,
                DATE_FORMAT(m.sent_at, '%%d.%%m.%%Y') AS date,
                DATE_FORMAT(m.sent_at, '%%H:%%i')     AS time
            FROM messages m
            WHERE (m.owner_id=%s AND m.deliver_id=%s)
               OR (m.owner_id=%s AND m.deliver_id=%s)
            ORDER BY m.sent_at ASC LIMIT 200
            """,
            (me_id, partner_id, partner_id, me_id),
        ) or []
    else:
        messages = [
            m for m in _temp_messages
            if (m["owner_id"] == me_id   and m["deliver_id"] == partner_id)
            or (m["owner_id"] == partner_id and m["deliver_id"] == me_id)
        ]
    return jsonify(messages)


@app.route("/api/messages/<int:partner_id>", methods=["POST"])
@login_required
def api_send_message(partner_id: int):
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"ok": False, "message": "Пустое сообщение"}), 400

    me_id = session["user_id"]
    if using_db():
        msg_id = query(
            "INSERT INTO messages (owner_id, deliver_id, text) VALUES (%s,%s,%s)",
            (me_id, partner_id, text), commit=True,
        )
    else:
        now    = datetime.datetime.now()
        msg_id = _next_temp_id(_temp_messages)
        _temp_messages.append({
            "id": msg_id, "owner_id": me_id, "deliver_id": partner_id,
            "text": text,
            "date": now.strftime("%d.%m.%Y"),
            "time": now.strftime("%H:%M"),
        })
    return jsonify({"ok": True, "id": msg_id}), 201

# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    with app.app_context():
        init_db()
    app.run(debug=True, port=5000)
