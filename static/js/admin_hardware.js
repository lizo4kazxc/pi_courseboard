function qs(id) { return document.getElementById(id); }

let courses = [];      // sorted by button_gpio_pin ascending
let arduinoConfig = null;

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function loadBackendStatus() {
  const res = await fetch("/api/state");
  const state = await res.json();
  const backend = state.backend || {};
  const pill = qs("backendStatus");
  const ok = !!backend.active;
  pill.classList.remove("ok", "bad");
  pill.classList.add(ok ? "ok" : "bad");
  const detail = backend.type === "arduino" && backend.serial_port ? ` (${backend.serial_port})` : "";
  pill.textContent = `${backend.type || "unknown"}${detail} - ${ok ? "active" : "inactive"}`;
  if (backend.type) qs("backendSelect").value = backend.type;
  return backend;
}

async function loadCourses() {
  const res = await fetch("/api/courses");
  courses = await res.json();
  courses.sort((a, b) => a.button_gpio_pin - b.button_gpio_pin);
}

async function loadArduinoConfig() {
  const res = await fetch("/api/admin/arduino-config");
  arduinoConfig = await res.json();
  qs("serial_port").value = arduinoConfig.serial_port || "";
  qs("baud_rate").value = arduinoConfig.baud_rate ?? 9600;
  qs("clear_input").value = arduinoConfig.clear_input ?? "";
  qs("input_count").value = arduinoConfig.input_count ?? 10;
}

function inputCount() {
  return Math.max(1, Number(qs("input_count").value) || 10);
}

function renderMappingTable() {
  const table = qs("mappingTable");
  table.innerHTML = "";

  const head = document.createElement("tr");
  head.innerHTML = "<th>Course</th><th>Pin</th><th>Raw input ID</th>";
  table.appendChild(head);

  const n = inputCount();
  const courseInputs = arduinoConfig.course_inputs || [];

  courses.forEach((c, i) => {
    const tr = document.createElement("tr");
    const tdTitle = document.createElement("td");
    tdTitle.textContent = c.title;
    const tdPin = document.createElement("td");
    tdPin.textContent = c.button_gpio_pin;
    const tdSelect = document.createElement("td");

    const select = document.createElement("select");
    select.id = `map_${i}`;
    select.dataset.courseIndex = String(i);
    for (let raw = 0; raw < n; raw++) {
      const opt = document.createElement("option");
      opt.value = String(raw);
      opt.textContent = String(raw);
      select.appendChild(opt);
    }
    select.value = String(courseInputs[i] ?? i);
    tdSelect.appendChild(select);

    tr.appendChild(tdTitle);
    tr.appendChild(tdPin);
    tr.appendChild(tdSelect);
    table.appendChild(tr);
  });
}

function currentMappingSelects() {
  return courses.map((_, i) => qs(`map_${i}`));
}

function rawIdToCourseTitle(rawId) {
  const clearInput = Number(qs("clear_input").value);
  if (rawId === clearInput) return "Clear / Confirm";
  const selects = currentMappingSelects();
  for (let i = 0; i < selects.length; i++) {
    if (Number(selects[i].value) === rawId) return courses[i].title;
  }
  return "Unmapped";
}

function renderTestGrid() {
  const grid = qs("testGrid");
  grid.innerHTML = "";
  const n = inputCount();
  for (let raw = 0; raw < n; raw++) {
    const tile = document.createElement("div");
    tile.className = "testTile";
    tile.dataset.rawId = String(raw);

    const idEl = document.createElement("div");
    idEl.className = "rawId";
    idEl.textContent = raw;

    const mappedEl = document.createElement("div");
    mappedEl.className = "mapped";
    mappedEl.textContent = rawIdToCourseTitle(raw);

    tile.appendChild(idEl);
    tile.appendChild(mappedEl);
    grid.appendChild(tile);
  }
}

async function refreshPortPicker() {
  const select = qs("portPicker");
  select.innerHTML = "<option value=\"\">Scanning...</option>";
  try {
    const res = await fetch("/api/admin/serial-ports");
    const ports = await res.json();
    select.innerHTML = "<option value=\"\">Select a detected port...</option>";
    for (const p of ports) {
      const opt = document.createElement("option");
      opt.value = p.device;
      opt.textContent = `${p.device} - ${p.description}`;
      select.appendChild(opt);
    }
    if (ports.length === 0) {
      select.innerHTML = "<option value=\"\">No ports found</option>";
    }
  } catch (err) {
    select.innerHTML = "<option value=\"\">Scan failed</option>";
  }
}

function connectTestWs() {
  const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;
  const ws = new WebSocket(url);
  ws.addEventListener("message", (ev) => {
    let msg = null;
    try { msg = JSON.parse(ev.data); } catch { return; }
    if (msg && msg.type === "raw_input") {
      const tile = document.querySelector(`.testTile[data-raw-id="${msg.input_id}"]`);
      if (!tile) return;
      tile.classList.toggle("active", msg.kind === "down");
    }
  });
  ws.addEventListener("close", () => setTimeout(connectTestWs, 1000));
}

document.addEventListener("DOMContentLoaded", async () => {
  await Promise.all([loadBackendStatus(), loadCourses(), loadArduinoConfig()]);
  renderMappingTable();
  renderTestGrid();
  connectTestWs();

  qs("input_count").addEventListener("change", () => {
    renderMappingTable();
    renderTestGrid();
  });
  qs("clear_input").addEventListener("change", renderTestGrid);

  qs("portPicker").addEventListener("focus", refreshPortPicker, { once: false });
  qs("portPicker").addEventListener("change", () => {
    const val = qs("portPicker").value;
    if (val) qs("serial_port").value = val;
  });

  qs("switchBackendBtn").addEventListener("click", async () => {
    const backend = qs("backendSelect").value;
    if (!confirm(`Switch input backend to "${backend}"? This takes effect immediately.`)) return;
    try {
      const res = await fetch(`/api/admin/change-backend?backend=${encodeURIComponent(backend)}`, { method: "POST" });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || "Switch failed");
      alert(`Backend switched to ${backend}`);
      await loadBackendStatus();
    } catch (err) {
      alert(`Failed to switch backend: ${err.message}`);
    }
  });

  qs("arduinoForm").addEventListener("submit", async (e) => {
    e.preventDefault();

    const selects = currentMappingSelects();
    const values = selects.map(s => Number(s.value));
    const clearInput = Number(qs("clear_input").value);

    const seen = new Map();
    for (let i = 0; i < values.length; i++) {
      const v = values[i];
      if (seen.has(v)) {
        alert(`Raw input ${v} is assigned to both "${courses[i].title}" and "${courses[seen.get(v)].title}". Each raw input must be unique.`);
        return;
      }
      seen.set(v, i);
    }
    if (seen.has(clearInput)) {
      alert(`Raw input ${clearInput} is used by both the Clear/Confirm button and "${courses[seen.get(clearInput)].title}". Pick a different raw input for one of them.`);
      return;
    }

    const payload = {
      serial_port: qs("serial_port").value.trim(),
      baud_rate: Number(qs("baud_rate").value),
      course_inputs: values,
      clear_input: clearInput,
      input_count: inputCount(),
    };

    try {
      const res = await fetch("/api/admin/arduino-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || "Save failed");
      alert("Arduino config saved and applied.");
      arduinoConfig = payload;
      renderTestGrid();
      await loadBackendStatus();
    } catch (err) {
      alert(`Failed to save: ${err.message}`);
    }
  });
});
