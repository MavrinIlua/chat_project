"use strict";

/* ── Утилиты ─────────────────────────────────────────────── */

function showAlert(form, message, type) {
  let el = form.querySelector(".alert");
  if (!el) { el = document.createElement("p"); el.className = "alert"; form.appendChild(el); }
  el.textContent = message;
  el.className = `alert ${type}`;
}

async function postJSON(url, body) {
  const res  = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return { ok: res.ok, status: res.status, data };
}

function escapeHtml(str) {
  return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
            .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

/* ── Регистрация ─────────────────────────────────────────── */

const registerForm = document.getElementById("registerForm");
if (registerForm) {
  registerForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = registerForm.querySelector(".btn");
    btn.disabled = true; btn.textContent = "Создаём...";

    const { ok, data } = await postJSON("/api/register", {
      name:     registerForm.name.value.trim(),
      surname:  registerForm.surname.value.trim(),
      login:    registerForm.login.value.trim(),
      password: registerForm.password.value.trim(),
    }).catch(() => ({ ok: false, data: { message: "Ошибка сети" } }));

    if (ok) {
      showAlert(registerForm, "Аккаунт создан! ✅", "success");
      setTimeout(() => (window.location.href = "/users"), 700);
    } else {
      showAlert(registerForm, data.message || "Что-то пошло не так", "error");
      btn.disabled = false; btn.textContent = "Зарегистрироваться";
    }
  });
}

/* ── Авторизация ─────────────────────────────────────────── */

const loginForm = document.getElementById("loginForm");
if (loginForm) {
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = loginForm.querySelector(".btn");
    btn.disabled = true; btn.textContent = "Входим...";

    const { ok, data } = await postJSON("/api/login", {
      login:    loginForm.login.value.trim(),
      password: loginForm.password.value.trim(),
    }).catch(() => ({ ok: false, data: { message: "Ошибка сети" } }));

    if (ok) {
      showAlert(loginForm, "Добро пожаловать! 🎉", "success");
      setTimeout(() => (window.location.href = "/users"), 600);
    } else {
      showAlert(loginForm, data.message || "Неверный логин или пароль", "error");
      btn.disabled = false; btn.textContent = "Войти";
    }
  });
}

/* ── Поиск по пользователям ──────────────────────────────── */

const usersSearch = document.getElementById("usersSearch");
if (usersSearch) {
  usersSearch.addEventListener("input", () => {
    const q = usersSearch.value.toLowerCase();
    document.querySelectorAll(".users-list__item").forEach((item) => {
      item.style.display = item.textContent.toLowerCase().includes(q) ? "" : "none";
    });
  });
}

/* ── Чат ─────────────────────────────────────────────────── */

const chatApp = document.getElementById("chatApp");
if (chatApp) {
  const ME_ID      = Number(chatApp.dataset.meId);
  const PARTNER_ID = Number(chatApp.dataset.partnerId);
  const messagesArea = document.getElementById("messagesArea");
  const messageInput = document.getElementById("messageInput");
  const sendBtn      = document.getElementById("sendBtn");

  // Приветствие при входе в чат
  const greetingEl = document.getElementById("greetingData");
  if (greetingEl) {
    const greeting = greetingEl.dataset.greeting;
    const div = document.createElement("div");
    div.className = "chat-greeting";
    div.innerHTML = `<span class="chat-greeting__text">👋 ${escapeHtml(greeting)}! Начало переписки</span>`;
    messagesArea.appendChild(div);
  }

  // Поиск по контактам
  const sidebarSearch = document.getElementById("sidebarSearch");
  if (sidebarSearch) {
    sidebarSearch.addEventListener("input", () => {
      const q = sidebarSearch.value.toLowerCase();
      document.querySelectorAll(".contact-item").forEach((el) => {
        el.style.display = el.textContent.toLowerCase().includes(q) ? "" : "none";
      });
    });
  }

  /* Рендер сообщений */
  let lastDate      = null;
  let lastMessageId = 0;
  let firstLoad     = true;

  function buildMessage(msg) {
    const frag   = document.createDocumentFragment();
    const isSent = msg.owner_id === ME_ID;

    // Разделитель по дате
    if (msg.date !== lastDate) {
      lastDate = msg.date;
      const div = document.createElement("div");
      div.className = "date-divider";
      div.textContent = msg.date;
      frag.appendChild(div);
    }

    const wrap = document.createElement("div");
    wrap.className = `message ${isSent ? "sent" : "received"}`;
    wrap.innerHTML = `
      <div class="bubble">
        ${escapeHtml(msg.text)}
        <span class="bubble__time">${msg.time}</span>
      </div>`;
    frag.appendChild(wrap);
    return frag;
  }

  async function loadMessages() {
    try {
      const res  = await fetch(`/api/messages/${PARTNER_ID}`);
      const msgs = await res.json();
      if (!Array.isArray(msgs) || msgs.length === 0) return;

      const newMsgs = firstLoad ? msgs : msgs.filter(m => m.id > lastMessageId);
      if (newMsgs.length === 0) return;

      if (firstLoad) {
        // Убираем только дубль приветствия при первой загрузке реальных сообщений
        firstLoad = false;
        lastDate  = null;
      }

      newMsgs.forEach(msg => {
        messagesArea.appendChild(buildMessage(msg));
        if (msg.id > lastMessageId) lastMessageId = msg.id;
      });

      // Прокрутка вниз если пользователь внизу
      const nearBottom =
        messagesArea.scrollHeight - messagesArea.scrollTop - messagesArea.clientHeight < 150;
      if (nearBottom) messagesArea.scrollTop = messagesArea.scrollHeight;

    } catch (err) {
      console.error("Ошибка загрузки сообщений:", err);
    }
  }

  async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text) return;
    messageInput.value = "";
    sendBtn.disabled   = true;

    try {
      const { ok, data } = await postJSON(`/api/messages/${PARTNER_ID}`, { text });
      if (ok) {
        await loadMessages();
        messagesArea.scrollTop = messagesArea.scrollHeight;
      } else {
        messageInput.value = text;
        console.error(data.message);
      }
    } catch {
      messageInput.value = text;
    } finally {
      sendBtn.disabled = false;
      messageInput.focus();
    }
  }

  sendBtn.addEventListener("click", sendMessage);
  messageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });

  // Polling — каждые 4 секунды
  loadMessages();
  setInterval(loadMessages, 4000);
}
