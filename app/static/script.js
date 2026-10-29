const API = "/api/tasks";
const list = document.getElementById("list");
const statusEl = document.getElementById("status");

async function request(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ? JSON.stringify(body.detail) : "Request failed (" + res.status + ")");
  }
  return res.status === 204 ? null : res.json();
}

function show(msg) { statusEl.textContent = msg || ""; }

async function load() {
  try {
    const tasks = await request(API);
    render(tasks);
    show("");
  } catch (e) { show("Could not load tasks. " + e.message); }
}

function render(tasks) {
  list.innerHTML = "";
  if (!tasks.length) {
    list.innerHTML = '<li class="empty" style="display:block">No tasks yet. Add your first one above.</li>';
    return;
  }
  for (const t of tasks) {
    const li = document.createElement("li");
    if (t.done) li.className = "done";

    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.checked = t.done;
    cb.setAttribute("aria-label", "Mark done");
    cb.onchange = () => act(() => request(API + "/" + t.id, {
      method: "PATCH", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({done: cb.checked})
    }));

    const body = document.createElement("div");
    const title = document.createElement("div");
    title.className = "title"; title.textContent = t.title;
    body.appendChild(title);
    if (t.description) {
      const d = document.createElement("div");
      d.className = "desc"; d.textContent = t.description;
      body.appendChild(d);
    }

    const del = document.createElement("button");
    del.className = "danger"; del.textContent = "Delete";
    del.onclick = () => act(() => request(API + "/" + t.id, {method: "DELETE"}));

    li.append(cb, body, del);
    list.appendChild(li);
  }
}

async function act(fn) {
  try { await fn(); await load(); } catch (e) { show(e.message); }
}

document.getElementById("taskForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const title = document.getElementById("title");
  const description = document.getElementById("description");
  await act(() => request(API, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({title: title.value.trim(), description: description.value.trim()})
  }));
  title.value = ""; description.value = ""; title.focus();
});

load();
