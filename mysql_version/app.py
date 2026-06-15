"""
ChatApp — MySQL-версия
Чат 1-на-1 с регистрацией, авторизацией и историей сообщений.
"""

import os
from functools import wraps

import mysql.connector
from flask import (
    Flask, g, jsonify, redirect, render_template,
    request, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash

# ---------------------------------------------------------------------------
# Инициализация приложения
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "секрет123")

# ---------------------------------------------------------------------------
# Подключение к базе данных
# ---------------------------------------------------------------------------

def get_db() -> mysql.connector.MySQLConnection:
    """Возвращает соединение с MySQL, создаёт его при первом обращении за запрос."""
    if "db" not in g:
        g.db = mysql.connector.connect(
            host=os.getenv("DB_HOST", "185.114.247.43"),
            database=os.getenv("DB_NAME", "sch688_maga1"),
            user=os.getenv("DB_USER", "sch688_maga1"),
            password=os.getenv("DB_PASSWORD", "Fqx8irSU"),
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
        )
    return g.db


@app.teardown_appcontext
def close_db(error):
    """Закрывает соединение после завершения запроса."""
    db = g.pop("db", None)
    if db is not None and db.is_connected():
        db.close()


def query(sql: str, params: tuple = (), *, one: bool = False, commit: bool = False):
    """
    Универсальная обёртка для SQL-запросов.
    one=True    — вернуть одну строку (или None).
    commit=True — для INSERT/UPDATE/DELETE, возвращает lastrowid.
    """
    db = get_db()
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


# ---------------------------------------------------------------------------
# Инициализация таблиц (создаём, если не существуют)
# ---------------------------------------------------------------------------

def init_db():
    """Создаёт таблицы users и messages при первом запуске."""
    db = get_db()
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
            owner_id   INT       NOT NULL,
            deliver_id INT       NOT NULL,
            text       TEXT      NOT NULL,
            sent_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id)   REFERENCES users(id),
            FOREIGN KEY (deliver_id) REFERENCES users(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    db.commit()
    cursor.close()


# ---------------------------------------------------------------------------
# Декоратор защиты маршрутов
# ---------------------------------------------------------------------------

def login_required(f):
    """Перенаправляет неавторизованных пользователей на страницу входа."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Страницы — Регистрация / Вход / Выход
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("users_list"))
    return redirect(url_for("register"))


@app.route("/register", methods=["GET"])
def register():
    return render_template("registration.html")


@app.route("/login", methods=["GET"])
def login():
    return render_template("avtorization.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# API — Регистрация и авторизация
# ---------------------------------------------------------------------------

@app.route("/api/register", methods=["POST"])
def api_register():
    """Регистрация. Принимает JSON: name, surname, login, password."""
    data     = request.get_json(silent=True) or {}
    name     = data.get("name", "").strip()
    surname  = data.get("surname", "").strip()
    login_   = data.get("login", "").strip()
    password = data.get("password", "").strip()

    if not all([name, surname, login_, password]):
        return jsonify({"ok": False, "message": "Заполните все поля"}), 400

    if len(password) < 6:
        return jsonify({"ok": False, "message": "Пароль — минимум 6 символов"}), 400

    if query("SELECT id FROM users WHERE login = %s", (login_,), one=True):
        return jsonify({"ok": False, "message": "Логин уже занят"}), 409

    hashed  = generate_password_hash(password)
    user_id = query(
        "INSERT INTO users (name, surname, login, password) VALUES (%s, %s, %s, %s)",
        (name, surname, login_, hashed),
        commit=True,
    )

    session["user_id"]      = user_id
    session["user_login"]   = login_
    session["user_name"]    = name
    session["user_surname"] = surname

    return jsonify({"ok": True, "user_id": user_id}), 201


@app.route("/api/login", methods=["POST"])
def api_login():
    """Авторизация. Принимает JSON: login, password."""
    data     = request.get_json(silent=True) or {}
    login_   = data.get("login", "").strip()
    password = data.get("password", "").strip()

    if not login_ or not password:
        return jsonify({"ok": False, "message": "Введите логин и пароль"}), 400

    user = query(
        "SELECT id, name, surname, login, password FROM users WHERE login = %s",
        (login_,),
        one=True,
    )

    if not user or not check_password_hash(user["password"], password):
        return jsonify({"ok": False, "message": "Неверный логин или пароль"}), 401

    session["user_id"]      = user["id"]
    session["user_login"]   = user["login"]
    session["user_name"]    = user["name"]
    session["user_surname"] = user["surname"]

    return jsonify({"ok": True, "user_id": user["id"]}), 200


# ---------------------------------------------------------------------------
# Страница со списком пользователей
# ---------------------------------------------------------------------------

@app.route("/users")
@login_required
def users_list():
    """Список всех пользователей кроме текущего — для выбора собеседника."""
    users = query(
        "SELECT id, name, surname, login FROM users WHERE id != %s ORDER BY name",
        (session["user_id"],),
    )
    me = {
        "id":      session["user_id"],
        "name":    session["user_name"],
        "surname": session["user_surname"],
        "login":   session["user_login"],
    }
    return render_template("users.html", users=users, me=me)


# ---------------------------------------------------------------------------
# Страница чата 1-на-1
# ---------------------------------------------------------------------------

@app.route("/chat/<int:partner_id>")
@login_required
def chat(partner_id: int):
    """Открывает чат с конкретным пользователем."""
    me_id = session["user_id"]

    partner = query(
        "SELECT id, name, surname, login FROM users WHERE id = %s",
        (partner_id,),
        one=True,
    )
    if not partner:
        return redirect(url_for("users_list"))

    users = query(
        "SELECT id, name, surname, login FROM users WHERE id != %s ORDER BY name",
        (me_id,),
    )
    me = {
        "id":      me_id,
        "name":    session["user_name"],
        "surname": session["user_surname"],
        "login":   session["user_login"],
    }
    return render_template("chat.html", me=me, partner=partner, users=users)


# ---------------------------------------------------------------------------
# API — Сообщения
# ---------------------------------------------------------------------------

@app.route("/api/messages/<int:partner_id>", methods=["GET"])
@login_required
def api_get_messages(partner_id: int):
    """Возвращает историю переписки с партнёром (JSON)."""
    me_id = session["user_id"]
    messages = query(
        """
        SELECT
            m.id,
            m.owner_id,
            m.deliver_id,
            m.text,
            DATE_FORMAT(m.sent_at, '%%d.%%m.%%Y') AS date,
            DATE_FORMAT(m.sent_at, '%%H:%%i')     AS time
        FROM messages m
        WHERE (m.owner_id = %s AND m.deliver_id = %s)
           OR (m.owner_id = %s AND m.deliver_id = %s)
        ORDER BY m.sent_at ASC
        LIMIT 200
        """,
        (me_id, partner_id, partner_id, me_id),
    )
    return jsonify(messages or [])


@app.route("/api/messages/<int:partner_id>", methods=["POST"])
@login_required
def api_send_message(partner_id: int):
    """Сохраняет новое сообщение. Принимает JSON: text."""
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"ok": False, "message": "Пустое сообщение"}), 400

    me_id  = session["user_id"]
    msg_id = query(
        "INSERT INTO messages (owner_id, deliver_id, text) VALUES (%s, %s, %s)",
        (me_id, partner_id, text),
        commit=True,
    )
    return jsonify({"ok": True, "id": msg_id}), 201


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Загружаем .env, если установлен python-dotenv
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    with app.app_context():
        init_db()

    app.run(debug=True, port=5000)  # MySQL-версия: http://127.0.0.1:5000
