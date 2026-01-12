let courses = [];
let editingId = null;

function qs(id) { return document.getElementById(id); }

function readForm() {
  return {
    course_id: qs("course_id").value.trim(),
    button_gpio_pin: Number(qs("button_gpio_pin").value),
    title: qs("title").value.trim(),
    room: qs("room").value.trim(),
    description: qs("description").value.trim(),
    overview: qs("overview").value.trim(),
    image_path: qs("image_path").value.trim(),
  };
}

function setForm(c) {
  qs("course_id").value = c.course_id || "";
  qs("button_gpio_pin").value = c.button_gpio_pin ?? "";
  qs("title").value = c.title || "";
  qs("room").value = c.room || "";
  qs("description").value = c.description || "";
  qs("overview").value = c.overview || "";
  qs("image_path").value = c.image_path || "";
}

function resetForm() {
  editingId = null;
  qs("formTitle").textContent = "Add course";
  qs("course_id").disabled = false;
  setForm({});
}

function renderTable() {
  const table = qs("coursesTable");
  table.innerHTML = "";

  const head = document.createElement("tr");
  head.innerHTML = "<th>ID</th><th>GPIO</th><th>Title</th><th>Room</th><th>Actions</th>";
  table.appendChild(head);

  for (const c of courses) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(c.course_id)}</td>
      <td>${Number(c.button_gpio_pin)}</td>
      <td>${escapeHtml(c.title)}</td>
      <td>${escapeHtml(c.room)}</td>
      <td></td>
    `;
    const actions = tr.querySelector("td:last-child");

    const editBtn = document.createElement("button");
    editBtn.className = "btn secondary";
    editBtn.type = "button";
    editBtn.textContent = "Edit";
    editBtn.addEventListener("click", () => startEdit(c.course_id));

    const delBtn = document.createElement("button");
    delBtn.className = "btn danger";
    delBtn.type = "button";
    delBtn.textContent = "Delete";
    delBtn.addEventListener("click", () => deleteCourse(c.course_id));

    const wrap = document.createElement("div");
    wrap.className = "rowBtns";
    wrap.appendChild(editBtn);
    wrap.appendChild(delBtn);
    actions.appendChild(wrap);

    table.appendChild(tr);
  }
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function loadCourses() {
  const res = await fetch("/api/courses");
  courses = await res.json();
  courses.sort((a, b) => a.course_id.localeCompare(b.course_id));
  renderTable();
}

function startEdit(id) {
  const c = courses.find(x => x.course_id === id);
  if (!c) return;
  editingId = id;
  qs("formTitle").textContent = `Edit course ${id}`;
  qs("course_id").disabled = true;
  setForm(c);
}

async function saveCourse(payload) {
  if (editingId) {
    const res = await fetch(`/api/admin/courses/${encodeURIComponent(editingId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
  } else {
    const res = await fetch("/api/admin/courses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
  }
}

async function deleteCourse(id) {
  const ok = confirm(`Delete course ${id}?`);
  if (!ok) return;
  const res = await fetch(`/api/admin/courses/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!res.ok) {
    alert("Delete failed");
    return;
  }
  await loadCourses();
  resetForm();
}

document.addEventListener("DOMContentLoaded", async () => {
  await loadCourses();

  qs("resetBtn").addEventListener("click", resetForm);

  qs("courseForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = readForm();

    if (!payload.course_id) {
      alert("Course ID is required");
      return;
    }

    const usedPins = new Map(courses.map(c => [Number(c.button_gpio_pin), c.course_id]));
    if (!editingId || editingId !== payload.course_id) {
      if (usedPins.has(payload.button_gpio_pin)) {
        alert(`GPIO pin already used by ${usedPins.get(payload.button_gpio_pin)}`);
        return;
      }
    } else {
      for (const [pin, cid] of usedPins) {
        if (cid !== editingId && pin === payload.button_gpio_pin) {
          alert(`GPIO pin already used by ${cid}`);
          return;
        }
      }
    }

    try {
      await saveCourse(payload);
      await loadCourses();
      resetForm();
      alert("Saved");
    } catch (err) {
      alert("Save failed");
    }
  });
});
