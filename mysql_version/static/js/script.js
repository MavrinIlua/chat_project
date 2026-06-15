/* ============================================================
   ChatApp — клиентская логика (без jQuery, чистый fetch API)
   ============================================================ */

"use strict";

/* ----------------------------------------------------------------
   Утилиты
   ---------------------------------------------------------------- */

/**
 * Показывает сообщение в блоке .alert внутри формы.
 * @param {HTMLElement} form
 * @param {string} message
 * @param {"error"|"success"} type
 */
function showAlert(form, message, type) {
  let alert = form.querySelector(".alert");
  if (!alert) {
    alert = document.createElement("p");
    alert.className = "alert";
    form.appendChild(alert);
  }
  alert.textContent = message;
  alert.className = `alert ${type}`;
}

/**
 * Отправляет JSON POST-запрос и возвращает промис с данными.
 * @param {string} url
 * @param {object} body
 * @returns {Promise<{ok: boolean, status: number, data: object}>}
 */
async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return { ok: res.ok, status: res.status, data };
}

/**
 * Возвращает инициалы из имени и фамилии (первые буквы).
 * @param {string} name
 * @param {string} surname
 * @returns {string}
 */
function initials(name, surname) {
  return ((name?.[0] ?? "") + (surname?.[0] ?? "")).toUpperCase();
}

/**
 * Возвращает число от 0 до 7 для цвета аватарки на основе строки.
 * @param {string} str
 * @returns {number}
 */
function avatarColor(str) {
  let hash = 0;
  for (const ch of str) hash = (hash * 31 + ch.charCodeAt(0)) & 0xff;
  return hash % 8;
}

/* ----------------------------------------------------------------
   Форма регистрации
   ---------------------------------------------------------------- */

const registerForm = document.getElementById("registerForm");

if (registerForm) {
  registerForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const btn  = registerForm.querySelector(".btn");
    btn.disabled = true;
    btn.textContent = "Регистрируем...";

    const { ok, data } = await postJSON("/api/register", {
      name:     registerForm.name.value.trim(),
      surname:  registerForm.surname.value.trim(),
      login:    registerForm.login.value.trim(),
      password: registerForm.password.value.trim(),
    }).catch(() => ({ ok: false, data: { message: "Ошибка сети" } }));

    if (ok) {
      showAlert(registerForm, "Аккаунт создан! Переходим...", "success");
      setTimeout(() => (window.location.href = "/users"), 800);
    } else {
      showAlert(registerForm, data.message || "Что-то пошло не так", "error");
      btn.disabled = false;
      btn.textContent = "Зарегистрироваться";
    }
  });
}

/* ----------------------------------------------------------------
   Форма авторизации
   ---------------------------------------------------------------- */

const loginForm = document.getElementById("loginForm");

if (loginForm) {
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const btn = loginForm.querySelector(".btn");
    btn.disabled = true;
    btn.textContent = "Входим...";

    const { ok, data } = await postJSON("/api/login", {
      login:    loginForm.login.value.trim(),
      password: loginForm.password.value.trim(),
    }).catch(() => ({ ok: false, data: { message: "Ошибка сети" } }));

    if (ok) {
      showAlert(loginForm, "Добро пожаловать!", "success");
      setTimeout(() => (window.location.href = "/users"), 600);
    } else {
      showAlert(loginForm, data.message || "Неверный логин или пароль", "error");
      btn.disabled = false;
      btn.textContent = "Войти";
    }
  });
}

/* ----------------------------------------------------------------
   Поиск по списку пользователей (users.html)
   ---------------------------------------------------------------- */

const searchInput = document.getElementById("usersSearch");

if (searchInput) {
  searchInput.addEventListener("input", () => {
    const q = searchInput.value.toLowerCase();
    document.querySelectorAll(".users-list__item").forEach((item) => {
      const text = item.textContent.toLowerCase();
      item.style.display = text.includes(q) ? "" : "none";
    });
  });
}

/* ----------------------------------------------------------------
   Чат 1-на-1 (chat.html)
   ---------------------------------------------------------------- */

// Данные, прокинутые из шаблона через data-атрибуты
const chatApp = document.getElementById("chatApp");

if (chatApp) {
  const ME_ID      = Number(chatApp.dataset.meId);
  const PARTNER_ID = Number(chatApp.dataset.partnerId);

  const messagesArea = document.getElementById("messagesArea");
  const messageInput = document.getElementById("messageInput");
  const sendBtn      = document.getElementById("sendBtn");

  // поиск по контактам в сайдбаре
  const sidebarSearch = document.getElementById("sidebarSearch");
  if (sidebarSearch) {
    sidebarSearch.addEventListener("input", () => {
      const q = sidebarSearch.value.toLowerCase();
      document.querySelectorAll(".contact-item").forEach((el) => {
        el.style.display = el.textContent.toLowerCase().includes(q) ? "" : "none";
      });
    });
  }

  /* ---- Рендер сообщений ---- */

  let lastDate = null; // для группировки по дате

  /**
   * Создаёт DOM-элемент одного сообщения.
   * @param {{ owner_id: number, text: string, date: string, time: string }} msg
   * @returns {DocumentFragment}
   */
  function buildMessage(msg) {
    const fragment = document.createDocumentFragment();

    // разделитель даты
    if (msg.date !== lastDate) {
      lastDate = msg.date;
      const divider = document.createElement("div");
      divider.className = "date-divider";
      divider.textContent = msg.date;
      fragment.appendChild(divider);
    }

    const isSent = msg.owner_id === ME_ID;
    const wrap   = document.createElement("div");
    wrap.className = `message ${isSent ? "sent" : "received"}`;
    wrap.innerHTML = `
      <div class="bubble">
        ${escapeHtml(msg.text)}
        <span class="bubble__time">${msg.time}</span>
      </div>`;
    fragment.appendChild(wrap);
    return fragment;
  }

  /**
   * Экранирует спецсимволы HTML (защита от XSS).
   * @param {string} str
   * @returns {string}
   */
  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /* ---- Загрузка сообщений ---- */

  let lastMessageId = 0; // ID последнего загруженного сообщения (для polling)
  let isFirstLoad   = true;

  async function loadMessages() {
    try {
      const res  = await fetch(`/api/messages/${PARTNER_ID}`);
      const msgs = await res.json();

      if (!Array.isArray(msgs) || msgs.length === 0) return;

      // Определяем новые сообщения (id > последнего известного)
      const newMsgs = isFirstLoad
        ? msgs
        : msgs.filter((m) => m.id > lastMessageId);

      if (newMsgs.length === 0) return;

      if (isFirstLoad) {
        messagesArea.innerHTML = "";
        lastDate = null;
        isFirstLoad = false;
      }

      newMsgs.forEach((msg) => {
        messagesArea.appendChild(buildMessage(msg));
        if (msg.id > lastMessageId) lastMessageId = msg.id;
      });

      // Прокручиваем вниз только если пользователь не читает историю
      const isNearBottom =
        messagesArea.scrollHeight - messagesArea.scrollTop - messagesArea.clientHeight < 120;
      if (isNearBottom || isFirstLoad) {
        messagesArea.scrollTop = messagesArea.scrollHeight;
      }
    } catch (err) {
      console.error("Ошибка загрузки сообщений:", err);
    }
  }

  /* ---- Отправка сообщения ---- */

  async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text) return;

    messageInput.value = "";
    sendBtn.disabled   = true;

    try {
      const { ok, data } = await postJSON(`/api/messages/${PARTNER_ID}`, { text });
      if (ok) {
        await loadMessages(); // сразу подгружаем новые
      } else {
        console.error("Ошибка отправки:", data.message);
        messageInput.value = text; // возвращаем текст
      }
    } catch (err) {
      console.error("Ошибка сети:", err);
      messageInput.value = text;
    } finally {
      sendBtn.disabled = false;
      messageInput.focus();
    }
  }

  sendBtn.addEventListener("click", sendMessage);

  messageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  /* ---- Polling — автообновление каждые 4 секунды ---- */

  loadMessages();
  setInterval(loadMessages, 4000);
}
