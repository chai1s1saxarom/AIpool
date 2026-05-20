const API = "";

const $ = (id) => document.getElementById(id);

let currentChatId = null;
let pollTimer = null;

function uuid() {
  return crypto.randomUUID();
}

function getUserId() {
  let id = localStorage.getItem("aipool_user_id");
  if (!id) {
    id = uuid();
    localStorage.setItem("aipool_user_id", id);
  }
  $("userId").value = id;
  return id;
}

async function api(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: res.statusText }));
    throw new Error(err.message || err.detail?.message || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

async function refreshServices() {
  try {
    const s = await api("/v1/services/status");
    $("servicesStatus").innerHTML = [
      `<span style="color:${s.llm === "ok" ? "#3dd68c" : "#f07178"}">LLM: ${s.llm}</span>`,
      `<span style="color:${s.image === "ok" ? "#3dd68c" : "#f07178"}">Image: ${s.image}</span>`,
      `<span style="color:${s.cost === "ok" ? "#3dd68c" : "#f07178"}">Cost: ${s.cost}</span>`,
    ].join(" · ");
  } catch {
    $("servicesStatus").textContent = "Сервисы недоступны";
  }
}

async function loadChats() {
  const userId = getUserId();
  const data = await api(`/v1/chats?user_id=${userId}`);
  const list = $("chatList");
  list.innerHTML = "";
  data.items.forEach((chat) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.textContent = chat.name || `Чат ${chat.chat_id.slice(0, 8)}`;
    btn.classList.toggle("active", chat.chat_id === currentChatId);
    btn.onclick = () => selectChat(chat.chat_id, chat.name);
    li.appendChild(btn);
    list.appendChild(li);
  });
}

async function selectChat(chatId, name) {
  currentChatId = chatId;
  $("chatTitle").textContent = name || "Чат";
  $("messageInput").disabled = false;
  $("btnSend").disabled = false;
  await loadChats();
  await loadHistory();
}

async function loadHistory() {
  if (!currentChatId) return;
  const data = await api(`/v1/chats/${currentChatId}/history`);
  const box = $("messages");
  box.innerHTML = "";
  data.messages.forEach((m) => {
    const div = document.createElement("div");
    div.className = `msg ${m.role}`;
    div.innerHTML = `<div>${escapeHtml(m.content)}</div>`;
    if (m.processing_type) {
      div.innerHTML += `<div class="meta">${m.processing_type} · ${m.role}</div>`;
    }
    box.appendChild(div);
  });
  box.scrollTop = box.scrollHeight;
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function updateModelSelect() {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const sel = $("modelSelect");
  sel.innerHTML = "";
  if (mode === "llm") {
    ["openai_gpt-4o-mini", "openai_gpt-4o", "google_gemini-1.5-flash"].forEach((m) => {
      const o = document.createElement("option");
      o.value = m;
      o.textContent = m;
      sel.appendChild(o);
    });
  } else {
    ["dalle-3", "kandinsky", "yandexart"].forEach((p) => {
      const o = document.createElement("option");
      o.value = p;
      o.textContent = p;
      sel.appendChild(o);
    });
  }
}

async function pollStatus(requestId) {
  const bar = $("statusBar");
  bar.classList.remove("hidden", "done", "error", "pending");
  bar.classList.add("pending");
  bar.textContent = "Обработка запроса…";

  const tick = async () => {
    try {
      const st = await api(`/v1/messages/${requestId}/status`);
      bar.textContent = `Статус: ${st.status}`;
      if (st.status === "done") {
        bar.classList.remove("pending");
        bar.classList.add("done");
        if (st.result?.content) bar.textContent += ` — ${st.result.content.slice(0, 80)}`;
        if (st.costs_summary) bar.textContent += ` · $${st.costs_summary.total_usd}`;
        clearInterval(pollTimer);
        await loadHistory();
        return;
      }
      if (st.status === "failed") {
        bar.classList.add("error");
        bar.textContent = st.error || "Ошибка";
        clearInterval(pollTimer);
        return;
      }
    } catch (e) {
      bar.classList.add("error");
      bar.textContent = e.message;
      clearInterval(pollTimer);
    }
  };
  await tick();
  pollTimer = setInterval(tick, 1500);
}

$("btnNewUser").onclick = () => {
  const id = uuid();
  localStorage.setItem("aipool_user_id", id);
  $("userId").value = id;
  currentChatId = null;
  loadChats();
};

$("userId").onchange = () => {
  localStorage.setItem("aipool_user_id", $("userId").value.trim());
  loadChats();
};

$("btnNewChat").onclick = async () => {
  const userId = getUserId();
  const name = prompt("Название чата (опционально)") || undefined;
  const chat = await api("/v1/chats", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, name }),
  });
  await selectChat(chat.chat_id, chat.name);
};

$("sendForm").onsubmit = async (e) => {
  e.preventDefault();
  if (!currentChatId) return;
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const body = {
    chat_id: currentChatId,
    user_id: getUserId(),
    message: $("messageInput").value.trim(),
    processing_type: mode,
  };
  if (mode === "llm") body.model_id = $("modelSelect").value;
  else body.provider_id = $("modelSelect").value;

  $("btnSend").disabled = true;
  try {
    const accepted = await api("/v1/messages/send", {
      method: "POST",
      body: JSON.stringify(body),
    });
    $("messageInput").value = "";
    await loadHistory();
    await pollStatus(accepted.request_id);
  } catch (err) {
    $("statusBar").classList.remove("hidden");
    $("statusBar").classList.add("error");
    $("statusBar").textContent = err.message;
  } finally {
    $("btnSend").disabled = false;
  }
};

document.querySelectorAll('input[name="mode"]').forEach((r) => {
  r.onchange = updateModelSelect;
});

getUserId();
updateModelSelect();
refreshServices();
loadChats();
setInterval(refreshServices, 30000);
