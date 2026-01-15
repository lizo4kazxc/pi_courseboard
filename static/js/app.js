let ws = null;
let state = {
  courses: [],
  pressed_pins: [],
  history_course_ids: [],
  clear_pin: null,
};

const selectedSkills = document.getElementById("cardsRow");

const skillsMap = {
  "1": "Graphic Design",
  "2": "3D Design",
  "3": "VFX"
};

document.addEventListener("keydown", (e) => {
  const skill = skillsMap[e.key];
  if (!skill) return;

  const existing = document.getElementById(skill);

  if (existing) {
    existing.remove();
    return;
  }

  const card = document.createElement("div");
  card.className = "miniCard";
  card.id = skill;
  card.textContent = skill + " selected";

  selectedSkills.appendChild(card);
});


function qs(id) { return document.getElementById(id); }

function setWsStatus(ok, text) {
  const el = qs("wsStatus");
  el.classList.remove("ok");
  el.classList.remove("bad");
  el.classList.add(ok ? "ok" : "bad");
  el.textContent = text;
}

function buildButtonsGrid() {
  const grid = qs("buttonsGrid");
  grid.innerHTML = "";

  const byPin = new Map(state.courses.map(c => [c.button_gpio_pin, c]));
  const allPins = new Set(state.courses.map(c => c.button_gpio_pin));
  if (state.clear_pin !== null) allPins.add(state.clear_pin);

  const pins = Array.from(allPins).sort((a, b) => a - b);

  for (const pin of pins) {
    const course = byPin.get(pin);
    const isEnter = state.clear_pin === pin;

    const tile = document.createElement("div");
    tile.className = "btnTile" + (isEnter ? " enter" : "");
    tile.dataset.pin = String(pin);

    const pinLine = document.createElement("div");
    pinLine.className = "pin";
    pinLine.textContent = `GPIO BCM ${pin}`;

    const label = document.createElement("div");
    label.className = "label";
    label.textContent = isEnter ? "Enter" : (course ? course.title : "Unassigned");

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = isEnter
      ? "Clears history"
      : (course ? `Room ${course.room}` : "Add a course in Admin");

    tile.appendChild(pinLine);
    tile.appendChild(label);
    tile.appendChild(meta);

    grid.appendChild(tile);
  }

  updatePressedUI();
  updateHintLine();
}

function updatePressedUI() {
  const pressed = new Set(state.pressed_pins);
  document.querySelectorAll(".btnTile").forEach(tile => {
    const pin = Number(tile.dataset.pin);
    tile.classList.toggle("pressed", pressed.has(pin));
  });
}

function updateHintLine() {
  const el = qs("hintLine");
  const enterPin = state.clear_pin !== null ? `Enter is GPIO BCM ${state.clear_pin}.` : "Enter not configured.";
  el.textContent = `Multiple buttons can be pressed simultaneously. ${enterPin}`;
}

function courseCard(course) {
  const card = document.createElement("div");
  card.className = "card";
  card.dataset.courseId = course.course_id;

  const header = document.createElement("div");
  header.className = "cardHeader";

  const title = document.createElement("h3");
  title.className = "cardTitle";
  title.textContent = course.title;

  const room = document.createElement("div");
  room.className = "cardRoom";
  room.textContent = `Room ${course.room}`;

  header.appendChild(title);
  header.appendChild(room);

  const body = document.createElement("div");
  body.className = "cardBody";

  const ph = document.createElement("div");
  ph.className = "imagePh";
  ph.textContent = "Image placeholder";

  const desc = document.createElement("div");
  desc.className = "cardBlock";
  desc.innerHTML = `<div class="k">Description</div><div class="v"></div>`;
  desc.querySelector(".v").textContent = course.description;

  const ov = document.createElement("div");
  ov.className = "cardBlock";
  ov.innerHTML = `<div class="k">Overview</div><div class="v"></div>`;
  ov.querySelector(".v").textContent = course.overview;

  body.appendChild(ph);
  body.appendChild(desc);
  body.appendChild(ov);

  card.appendChild(header);
  card.appendChild(body);
  return card;
}

function rebuildCardsFromHistory() {
  const row = qs("cardsRow");
  row.innerHTML = "";
  const empty = qs("emptyState");

  const byId = new Map(state.courses.map(c => [c.course_id, c]));
  for (const cid of state.history_course_ids) {
    const course = byId.get(cid);
    if (course) row.appendChild(courseCard(course));
  }

  empty.style.display = row.children.length ? "none" : "block";
}

async function loadInitial() {
  const res = await fetch("/api/state");
  state = await res.json();
  buildButtonsGrid();
  rebuildCardsFromHistory();
}

function connectWs() {
  const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;
  ws = new WebSocket(url);

  ws.addEventListener("open", () => setWsStatus(true, "Connected"));
  ws.addEventListener("close", () => {
    setWsStatus(false, "Disconnected");
    setTimeout(connectWs, 1000);
  });
  ws.addEventListener("error", () => setWsStatus(false, "Error"));

  ws.addEventListener("message", async (ev) => {
    let msg = null;
    try { msg = JSON.parse(ev.data); } catch { return; }

    if (msg.type === "state") {
      state = msg;
      buildButtonsGrid();
      rebuildCardsFromHistory();
      return;
    }

    if (msg.type === "pressed_update") {
      state.pressed_pins = msg.pressed_pins || [];
      updatePressedUI();
      return;
    }

    if (msg.type === "course_added") {
      if (msg.course && msg.course.course_id) {
        state.history_course_ids.push(msg.course.course_id);
        const row = qs("cardsRow");
        row.appendChild(courseCard(msg.course));
        qs("emptyState").style.display = "none";
        row.scrollLeft = row.scrollWidth;
      }
      return;
    }

    if (msg.type === "history_cleared") {
      state.history_course_ids = [];
      rebuildCardsFromHistory();
      return;
    }

    if (msg.type === "courses_updated") {
      await loadInitial();
      return;
    }
  });
}

async function clearHistory() {
  await fetch("/api/clear", { method: "POST" });
}

document.addEventListener("DOMContentLoaded", async () => {
  qs("clearBtn").addEventListener("click", clearHistory);
  await loadInitial();
  connectWs();
});
