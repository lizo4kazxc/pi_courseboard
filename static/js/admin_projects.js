function qs(id) { return document.getElementById(id); }

let courses = [];
let projects = [];
let editingId = null;
const IMAGE_SLOT_COUNT = 3;

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
  courses.sort((a, b) => a.title.localeCompare(b.title));
}

async function loadProjects() {
  const res = await fetch("/api/projects");
  projects = await res.json();
  projects.sort((a, b) => a.project_id.localeCompare(b.project_id));
  renderTable();
}

function renderSkillChecks(selectedIds) {
  const wrap = qs("skillChecks");
  wrap.innerHTML = "";
  const selected = new Set(selectedIds || []);
  for (const c of courses) {
    const label = document.createElement("label");
    label.className = "skillCheck";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = c.course_id;
    cb.checked = selected.has(c.course_id);
    label.appendChild(cb);
    label.appendChild(document.createTextNode(c.title));
    wrap.appendChild(label);
  }
}

function renderImageSlots(imagePaths) {
  const wrap = qs("imageSlots");
  wrap.innerHTML = "";
  for (let i = 0; i < IMAGE_SLOT_COUNT; i++) {
    const slot = document.createElement("div");
    slot.className = "imageSlot";
    slot.innerHTML = `
      <img id="image_preview_${i}" />
      <input id="image_path_${i}" placeholder="/static/uploads/..." />
      <input id="image_file_${i}" type="file" accept="image/*" />
    `;
    wrap.appendChild(slot);
  }
  for (let i = 0; i < IMAGE_SLOT_COUNT; i++) {
    qs(`image_path_${i}`).value = (imagePaths && imagePaths[i]) || "";
    wireImageUploadField(`image_file_${i}`, `image_path_${i}`, `image_preview_${i}`);
  }
}

function readForm() {
  const selectedSkills = Array.from(qs("skillChecks").querySelectorAll("input:checked")).map(cb => cb.value);
  const imagePaths = [];
  for (let i = 0; i < IMAGE_SLOT_COUNT; i++) imagePaths.push(qs(`image_path_${i}`).value.trim());
  return {
    project_id: qs("project_id").value.trim(),
    title: qs("title").value.trim(),
    description: qs("description").value.trim(),
    skill_ids: selectedSkills,
    image_path: imagePaths[0] || "",
    image_paths: imagePaths,
  };
}

function resetForm() {
  editingId = null;
  qs("formTitle").textContent = "Add project";
  qs("project_id").disabled = false;
  qs("project_id").value = "";
  qs("title").value = "";
  qs("description").value = "";
  renderSkillChecks([]);
  renderImageSlots([]);
}

function skillTitle(courseId) {
  const c = courses.find(x => x.course_id === courseId);
  return c ? c.title : courseId;
}

function renderTable() {
  const table = qs("projectsTable");
  table.innerHTML = "";

  const head = document.createElement("tr");
  head.innerHTML = "<th>ID</th><th>Title</th><th>Skills</th><th>Actions</th>";
  table.appendChild(head);

  for (const p of projects) {
    const tr = document.createElement("tr");
    const tdId = document.createElement("td");
    tdId.textContent = p.project_id;
    const tdTitle = document.createElement("td");
    tdTitle.textContent = p.title;
    const tdSkills = document.createElement("td");
    tdSkills.innerHTML = (p.skill_ids || []).map(id => `<span class="skillTag">${escapeHtml(skillTitle(id))}</span>`).join("");
    const tdActions = document.createElement("td");

    const editBtn = document.createElement("button");
    editBtn.className = "btn edit";
    editBtn.type = "button";
    editBtn.textContent = "Edit";
    editBtn.addEventListener("click", () => startEdit(p.project_id));

    const delBtn = document.createElement("button");
    delBtn.className = "btn danger";
    delBtn.type = "button";
    delBtn.textContent = "Delete";
    delBtn.addEventListener("click", () => deleteProject(p.project_id));

    const wrap = document.createElement("div");
    wrap.className = "rowBtns";
    wrap.appendChild(editBtn);
    wrap.appendChild(delBtn);
    tdActions.appendChild(wrap);

    tr.appendChild(tdId);
    tr.appendChild(tdTitle);
    tr.appendChild(tdSkills);
    tr.appendChild(tdActions);
    table.appendChild(tr);
  }
}

function startEdit(id) {
  const p = projects.find(x => x.project_id === id);
  if (!p) return;
  editingId = id;
  qs("formTitle").textContent = `Edit project ${id}`;
  qs("project_id").disabled = true;
  qs("project_id").value = p.project_id;
  qs("title").value = p.title;
  qs("description").value = p.description;
  renderSkillChecks(p.skill_ids);
  renderImageSlots(p.image_paths);
  qs("projectDialog").showModal();
}

async function saveProject(payload) {
  if (editingId) {
    const res = await fetch(`/api/admin/projects/${encodeURIComponent(editingId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
  } else {
    const res = await fetch("/api/admin/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
  }
}

async function deleteProject(id) {
  const ok = confirm(`Delete project ${id}?`);
  if (!ok) return;
  const res = await fetch(`/api/admin/projects/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!res.ok) {
    alert("Delete failed");
    return;
  }
  await loadProjects();
  resetForm();
}

document.addEventListener("DOMContentLoaded", async () => {
  await loadCourses();
  await loadProjects();
  resetForm();

  qs("addProjectBtn").addEventListener("click", () => {
    resetForm();
    qs("projectDialog").showModal();
  });

  qs("resetBtn").addEventListener("click", () => {
    resetForm();
    qs("projectDialog").close();
  });

  qs("projectForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = readForm();

    if (!payload.project_id) {
      alert("Project ID is required");
      return;
    }
    if (payload.skill_ids.length === 0) {
      alert("Pick at least one skill this project combines");
      return;
    }

    try {
      await saveProject(payload);
      await loadProjects();
      resetForm();
      qs("projectDialog").close();
    } catch (err) {
      alert("Save failed");
    }
  });
});
