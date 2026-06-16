"use strict";

/* ── Утилиты ─────────────────────────────────────────── */
function esc(s) {
  return String(s)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
async function apiJSON(url, method, body) {
  const r = await fetch(url, {
    method: method || "GET",
    headers: body ? {"Content-Type":"application/json;charset=utf-8"} : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  return r.json();
}

/* ── Auth-формы ──────────────────────────────────────── */
["registerForm","loginForm"].forEach(id => {
  const form = document.getElementById(id);
  if (!form) return;
  form.addEventListener("submit", e => {
    // Стандартная отправка (сервер делает редирект) — просто показываем спиннер
    const btn = form.querySelector(".btn");
    if (btn) { btn.disabled = true; btn.textContent = "Загрузка..."; }
  });
});

/* ── Чат ─────────────────────────────────────────────── */
const cfg = window.__CHAT__;
if (cfg) {
  const { meId, chatId, greeting } = cfg;
  const msgsEl   = document.getElementById("messages");
  const inputEl  = document.getElementById("msgInput");
  const sendBtn  = document.getElementById("sendBtn");
  const emojiBtn = document.getElementById("emojiBtn");
  const emojiPanel = document.getElementById("emojiPanel");

  let lastMsgId    = 0;
  let lastDate     = null;
  let firstLoad    = true;
  let greetingDone = false;
  let editingId    = null;

  /* ---- Поиск в сайдбаре ---- */
  const searchEl = document.getElementById("chatSearch");
  if (searchEl) {
    searchEl.addEventListener("input", () => {
      const q = searchEl.value.toLowerCase();
      document.querySelectorAll(".chat-list__item").forEach(li => {
        li.style.display = li.textContent.toLowerCase().includes(q) ? "" : "none";
      });
    });
  }

  /* ---- Приветствие ---- */
  function showGreeting() {
    if (greetingDone) return;
    greetingDone = true;
    const d = document.createElement("div");
    d.className   = "date-div";
    d.textContent = "👋 " + greeting + "! Начните общение.";
    msgsEl.appendChild(d);
  }

  /* ---- Построить пузырёк ---- */
  function buildBubble(m) {
    const frag   = document.createDocumentFragment();
    const isSent = m.user_id === meId;

    if (m.date !== lastDate) {
      lastDate = m.date;
      const d = document.createElement("div");
      d.className   = "date-div";
      d.textContent = m.date;
      frag.appendChild(d);
    }

    const wrap = document.createElement("div");
    wrap.className    = "msg " + (isSent ? "sent" : "received");
    wrap.dataset.msgId = m.id;

    const actionsHtml = isSent
      ? `<div class="bubble__actions">
           <button class="bubble__btn" onclick="editMsg(${m.id}, this)">✏️</button>
           <button class="bubble__btn" onclick="deleteMsg(${m.id})">🗑️</button>
         </div>`
      : "";

    const nickHtml = !isSent
      ? `<div class="bubble__nick">${esc(m.nickname)}</div>` : "";

    wrap.innerHTML =
      `<div class="bubble">
        ${nickHtml}
        <span class="bubble__text">${esc(m.text)}</span>
        <div class="bubble__time">${esc(m.time)}</div>
        ${actionsHtml}
       </div>`;
    frag.appendChild(wrap);
    return frag;
  }

  /* ---- Загрузить сообщения ---- */
  async function loadMessages() {
    try {
      const msgs = await apiJSON("/api/messages/" + chatId);
      if (!Array.isArray(msgs)) return;

      const newMsgs = firstLoad ? msgs : msgs.filter(m => m.id > lastMsgId);

      if (firstLoad) {
        msgsEl.innerHTML = "";
        lastDate  = null;
        firstLoad = false;
        if (msgs.length === 0) showGreeting();
      }

      newMsgs.forEach(m => {
        msgsEl.appendChild(buildBubble(m));
        if (m.id > lastMsgId) lastMsgId = m.id;
      });

      const near = msgsEl.scrollHeight - msgsEl.scrollTop - msgsEl.clientHeight < 150;
      if (near) msgsEl.scrollTop = msgsEl.scrollHeight;
    } catch(e) { console.error(e); }
  }

  /* ---- Отправить ---- */
  async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text) return;
    inputEl.value    = "";
    sendBtn.disabled = true;
    try {
      await apiJSON("/api/send", "POST", { chat_id: chatId, text });
      await loadMessages();
    } finally {
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }

  sendBtn.addEventListener("click", sendMessage);
  inputEl.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });

  /* ---- Emoji ---- */
  emojiBtn.addEventListener("click", e => {
    e.stopPropagation();
    emojiPanel.hidden = !emojiPanel.hidden;
  });
  document.addEventListener("click", e => {
    if (!emojiPanel.contains(e.target) && e.target !== emojiBtn)
      emojiPanel.hidden = true;
  });
  emojiPanel.querySelectorAll(".emoji-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      inputEl.value += btn.textContent;
      inputEl.focus();
      emojiPanel.hidden = true;
    });
  });

  /* ---- Редактирование ---- */
  const modal      = document.getElementById("editModal");
  const editInput  = document.getElementById("editInput");
  const editSave   = document.getElementById("editSave");
  const editCancel = document.getElementById("editCancel");

  window.editMsg = function(msgId, btn) {
    const bubble = btn.closest(".bubble");
    editingId    = msgId;
    editInput.value = bubble.querySelector(".bubble__text").textContent;
    modal.hidden    = false;
    editInput.focus();
  };
  editCancel.addEventListener("click", () => { modal.hidden = true; editingId = null; });
  editSave.addEventListener("click", async () => {
    const text = editInput.value.trim();
    if (!text || !editingId) return;
    const res = await apiJSON("/api/messages/" + editingId, "PUT", { text });
    if (res.ok) {
      // Обновляем текст прямо в DOM
      const wrap = document.querySelector(`.msg[data-msg-id="${editingId}"]`);
      if (wrap) wrap.querySelector(".bubble__text").textContent = text;
    }
    modal.hidden = true; editingId = null;
  });
  // Закрыть по клику на оверлей
  modal.addEventListener("click", e => { if (e.target === modal) { modal.hidden=true; editingId=null; } });

  /* ---- Удаление ---- */
  window.deleteMsg = async function(msgId) {
    if (!confirm("Удалить сообщение?")) return;
    const res = await apiJSON("/api/messages/" + msgId, "DELETE");
    if (res.ok) {
      const wrap = document.querySelector(`.msg[data-msg-id="${msgId}"]`);
      if (wrap) wrap.remove();
    }
  };

  /* ---- Polling ---- */
  loadMessages();
  setInterval(loadMessages, 4000);
}
