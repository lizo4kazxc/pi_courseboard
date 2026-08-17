let ws = null;
let state = {
  courses: [],
  projects: [],
  pressed_pins: [],
  history_course_ids: [],
  clear_pin: null,
  confirmed: false,
  project_sequence: [],
  project_index: 0,
};

// Keyboard-simulated button presses for testing without hardware.
// Keys "1"-"9" map to course pins (sorted, same order as the grid), "0" maps to the clear pin.
let keyPinMap = {};
const activeKeyPresses = new Set();

function buildKeyPinMap() {
  keyPinMap = {};
  // Exclude the clear pin from the numbered course keys so a course pin that
  // happens to collide with clear_pin doesn't get double-mapped to two keys.
  const coursePins = state.courses
    .map(c => c.button_gpio_pin)
    .filter(pin => pin !== state.clear_pin)
    .sort((a, b) => a - b);
  coursePins.forEach((pin, i) => {
    if (i < 9) keyPinMap[String(i + 1)] = pin;
  });
  if (state.clear_pin !== null) keyPinMap["0"] = state.clear_pin;
}

async function sendSimulatedPress(pin, kind) {
  try {
    await fetch("/api/debug/press", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin, kind }),
    });
  } catch (err) {
    console.error("Simulated press failed", err);
  }
}

// Short synthesized tones for button feedback (Web Audio API, no audio files).
// The AudioContext must be created/unlocked directly inside a real user
// gesture, so it's done eagerly on the first keydown even though tones are
// actually played later, in response to WS confirmation of what happened.
let audioCtx = null;
function ensureAudioCtx() {
  if (!audioCtx) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (Ctx) audioCtx = new Ctx();
  }
  if (audioCtx && audioCtx.state === "suspended") audioCtx.resume();
  return audioCtx;
}

function playTone(freq, durationMs = 100) {
  const ctx = audioCtx;
  if (!ctx) return;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "sine";
  osc.frequency.value = freq;
  gain.gain.setValueAtTime(0.16, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + durationMs / 1000);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start();
  osc.stop(ctx.currentTime + durationMs / 1000);
}

function playChime(freqs, stepMs = 90) {
  freqs.forEach((freq, i) => setTimeout(() => playTone(freq, stepMs + 20), i * stepMs));
}

document.addEventListener("keydown", (e) => {
  if (e.repeat) return;
  ensureAudioCtx();
  const pin = keyPinMap[e.key];
  if (pin === undefined || activeKeyPresses.has(e.key)) return;
  activeKeyPresses.add(e.key);
  sendSimulatedPress(pin, "down");
});

document.addEventListener("keyup", (e) => {
  const pin = keyPinMap[e.key];
  if (pin === undefined) return;
  activeKeyPresses.delete(e.key);
  sendSimulatedPress(pin, "up");
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
  buildKeyPinMap();

  const grid = qs("buttonsGrid");
  grid.innerHTML = "";

  // Enter/clear is not shown as a tile here anymore (see updateHintLine).
  const byPin = new Map(state.courses.map(c => [c.button_gpio_pin, c]));
  const pins = state.courses.map(c => c.button_gpio_pin).sort((a, b) => a - b);

  // Two rows: top row gets the larger half when the count is odd.
  const topCount = Math.ceil(pins.length / 2);
  const rows = [pins.slice(0, topCount), pins.slice(topCount)];

  for (const rowPins of rows) {
    if (rowPins.length === 0) continue;

    const row = document.createElement("div");
    row.className = "skillsRow";
    row.style.gridTemplateColumns = `repeat(${rowPins.length}, minmax(0, 1fr))`;

    for (const pin of rowPins) {
      const course = byPin.get(pin);

      const tile = document.createElement("div");
      tile.className = "btnTile";
      tile.dataset.pin = String(pin);

      const pinLine = document.createElement("div");
      pinLine.className = "pin";
      pinLine.textContent = `GPIO BCM ${pin}`;

      const label = document.createElement("div");
      label.className = "label";
      label.textContent = course ? course.title : "Unassigned";

      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = course ? `Room ${course.room}` : "Add a course in Admin";

      tile.appendChild(pinLine);
      tile.appendChild(label);
      tile.appendChild(meta);

      row.appendChild(tile);
    }

    grid.appendChild(row);
  }

  updatePressedUI();
}

function updatePressedUI() {
  const pressed = new Set(state.pressed_pins);
  document.querySelectorAll(".btnTile").forEach(tile => {
    const pin = Number(tile.dataset.pin);
    tile.classList.toggle("pressed", pressed.has(pin));
  });
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

  body.appendChild(ph);
  body.appendChild(desc);

  card.appendChild(header);
  card.appendChild(body);
  return card;
}

function skillTitle(courseId) {
  const course = state.courses.find(c => c.course_id === courseId);
  return course ? course.title : courseId;
}

function projectById(projectId) {
  return (state.projects || []).find(p => p.project_id === projectId) || null;
}

const MCT_INFO_URL = "kdg.be/en/bachelor-multimedia-creative-technologies";

// Within-project photo gallery cycling: purely local/decorative, no server
// round-trip. Resets whenever the current project changes.
const PICTURE_CYCLE_MS = 4000;
let pictureIndex = 0;
let pictureCycleTimer = null;

function stopPictureCycle() {
  if (pictureCycleTimer) { clearInterval(pictureCycleTimer); pictureCycleTimer = null; }
}

function startPictureCycle(project) {
  stopPictureCycle();
  pictureIndex = 0;
  const slideCount = Math.max(1, (project.image_paths || []).length);
  if (slideCount <= 1) return;
  pictureCycleTimer = setInterval(() => {
    pictureIndex = (pictureIndex + 1) % slideCount;
    updatePlayerImage(project);
  }, PICTURE_CYCLE_MS);
}

function updatePlayerImage(project) {
  const slideCount = Math.max(1, (project.image_paths || []).length);
  const img = qs("projectPlayerImage");
  if (img) img.textContent = `Image placeholder ${pictureIndex + 1} / ${slideCount}`;

  const dots = qs("projectPictureDots");
  if (dots) {
    dots.innerHTML = "";
    for (let i = 0; i < slideCount; i++) {
      const dot = document.createElement("span");
      dot.className = "pictureDot" + (i === pictureIndex ? " active" : "");
      dots.appendChild(dot);
    }
  }
}

function replayProjectTransition() {
  const player = qs("projectPlayer");
  if (!player) return;
  player.classList.remove("projectPlayer-animate");
  // Force reflow so the animation class can be re-applied and replay.
  void player.offsetWidth;
  player.classList.add("projectPlayer-animate");
}

function renderProjectPlayer() {
  const sequence = state.project_sequence || [];
  const total = sequence.length;
  const progress = qs("projectsProgress");

  if (total === 0) {
    if (progress) progress.textContent = "";
    const title = qs("projectPlayerTitle");
    if (title) title.textContent = "No matching projects";
    const desc = qs("projectPlayerDesc");
    if (desc) desc.textContent = "";
    const skills = qs("projectPlayerSkills");
    if (skills) skills.innerHTML = "";
    const img = qs("projectPlayerImage");
    if (img) img.textContent = "Image placeholder";
    const dots = qs("projectPictureDots");
    if (dots) dots.innerHTML = "";
    const nextUp = qs("projectNextUp");
    if (nextUp) nextUp.innerHTML = "";
    stopPictureCycle();
    return;
  }

  const currentId = sequence[state.project_index] || sequence[0];
  const project = projectById(currentId);
  if (!project) return;

  const selected = new Set(state.history_course_ids);

  qs("projectsProgress").textContent = `Project ${state.project_index + 1} of ${total}`;
  qs("projectPlayerTitle").textContent = project.title;
  qs("projectPlayerDesc").textContent = project.description;

  const skills = qs("projectPlayerSkills");
  skills.innerHTML = "";
  for (const sid of project.skill_ids) {
    const chip = document.createElement("span");
    chip.className = "projectSkillChip" + (selected.has(sid) ? " matched" : "");
    chip.textContent = skillTitle(sid);
    skills.appendChild(chip);
  }

  const nextUp = qs("projectNextUp");
  nextUp.innerHTML = "";
  const nextId = sequence[state.project_index + 1];
  if (nextId) {
    const nextProject = projectById(nextId);
    const label = document.createElement("div");
    label.className = "projectNextUpLabel";
    label.textContent = "Continue to next project";
    const thumb = document.createElement("div");
    thumb.className = "projectNextUpThumb";
    thumb.textContent = "Thumbnail";
    const title = document.createElement("div");
    title.className = "projectNextUpTitle";
    title.textContent = nextProject ? nextProject.title : "";
    nextUp.appendChild(label);
    nextUp.appendChild(thumb);
    nextUp.appendChild(title);
  } else {
    const label = document.createElement("div");
    label.className = "projectNextUpLabel";
    label.textContent = "This is the last project";
    const finish = document.createElement("div");
    finish.className = "projectNextUpFinish";
    finish.textContent = "Press confirm to finish";
    nextUp.appendChild(label);
    nextUp.appendChild(finish);
  }

  // Shown on every project, not just the last one.
  const cta = document.createElement("div");
  cta.className = "projectCta";
  const ctaQr = document.createElement("div");
  ctaQr.className = "projectCtaQr";
  ctaQr.textContent = "QR code placeholder";
  const ctaText = document.createElement("div");
  ctaText.className = "projectCtaText";
  ctaText.innerHTML = `Curious to learn more?<br><strong>${MCT_INFO_URL}</strong>`;
  cta.appendChild(ctaQr);
  cta.appendChild(ctaText);
  nextUp.appendChild(cta);

  replayProjectTransition();
  startPictureCycle(project);
  updatePlayerImage(project);
}

// Auto-return to skill selection after a period of inactivity on the
// projects screen, so a finished session doesn't sit on-screen indefinitely.
const PROJECTS_IDLE_TIMEOUT_MS = 30000;
let idleTimer = null;
let idleCountdownInterval = null;
let idleDeadline = null;

function clearIdleTimer() {
  if (idleTimer) { clearTimeout(idleTimer); idleTimer = null; }
  if (idleCountdownInterval) { clearInterval(idleCountdownInterval); idleCountdownInterval = null; }
  idleDeadline = null;
  const el = qs("projectsIdleHint");
  if (el) el.textContent = "";
}

function startIdleTimer() {
  clearIdleTimer();
  idleDeadline = Date.now() + PROJECTS_IDLE_TIMEOUT_MS;

  idleTimer = setTimeout(() => {
    clearIdleTimer();
    clearHistory();
  }, PROJECTS_IDLE_TIMEOUT_MS);

  idleCountdownInterval = setInterval(() => {
    const el = qs("projectsIdleHint");
    if (!el) return;
    const secondsLeft = Math.max(0, Math.ceil((idleDeadline - Date.now()) / 1000));
    el.textContent = `Returning to start in ${secondsLeft}s`;
  }, 250);
}

// If nobody interacts with the skill-selection screen for a while, hand off
// to the /attract screensaver page (separate page, not part of this SPA).
const SELECTION_IDLE_TIMEOUT_MS = 60000;
let selectionIdleTimer = null;

function clearSelectionIdleTimer() {
  if (selectionIdleTimer) { clearTimeout(selectionIdleTimer); selectionIdleTimer = null; }
}

function startSelectionIdleTimer() {
  clearSelectionIdleTimer();
  if (state.confirmed) return;
  selectionIdleTimer = setTimeout(async () => {
    await clearHistory(); // leave a clean slate for the next visitor
    window.location.href = "/attract";
  }, SELECTION_IDLE_TIMEOUT_MS);
}

document.addEventListener("keydown", () => {
  if (state.confirmed) {
    startIdleTimer();
  } else {
    startSelectionIdleTimer();
  }
});

function applyStep() {
  document.body.classList.toggle("step-projects", !!state.confirmed);
  if (state.confirmed) {
    clearSelectionIdleTimer();
    renderProjectPlayer();
    startIdleTimer();
  } else {
    stopPictureCycle();
    clearIdleTimer();
    startSelectionIdleTimer();
  }
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
  applyStep();
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
      applyStep();
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
        playTone(660, 90);
      }
      return;
    }

    if (msg.type === "course_removed") {
      if (msg.course_id) {
        state.history_course_ids = state.history_course_ids.filter(id => id !== msg.course_id);
        const row = qs("cardsRow");
        const card = row.querySelector(`[data-course-id="${msg.course_id}"]`);
        if (card) card.remove();
        qs("emptyState").style.display = row.children.length ? "none" : "block";
        playTone(330, 90);
      }
      return;
    }

    if (msg.type === "history_cleared") {
      state.history_course_ids = [];
      state.confirmed = false;
      state.project_sequence = [];
      state.project_index = 0;
      rebuildCardsFromHistory();
      applyStep();
      playTone(220, 160);
      return;
    }

    if (msg.type === "confirmed") {
      state.confirmed = true;
      state.project_sequence = msg.project_sequence || [];
      state.project_index = msg.project_index || 0;
      applyStep();
      playChime([523, 659, 784]);
      return;
    }

    if (msg.type === "project_advanced") {
      state.project_index = msg.project_index;
      renderProjectPlayer();
      startIdleTimer();
      playTone(494, 80);
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
