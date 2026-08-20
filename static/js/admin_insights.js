function qs(id) { return document.getElementById(id); }

function statTile(label, value) {
  const el = document.createElement("div");
  el.className = "insightStat";
  el.innerHTML = `<div class="k"></div><div class="v"></div>`;
  el.querySelector(".k").textContent = label;
  el.querySelector(".v").textContent = value;
  return el;
}

function renderOverview(data) {
  const grid = qs("insightsGrid");
  grid.innerHTML = "";
  grid.appendChild(statTile("Total skill presses", data.total_button_presses));
  grid.appendChild(statTile("Sessions confirmed", data.sessions_confirmed));
  grid.appendChild(statTile("Sessions finished", data.sessions_finished));
  grid.appendChild(statTile("Abandoned mid-selection", data.sessions_abandoned_mid_selection));
  grid.appendChild(statTile(
    "Avg. projects viewed / session",
    data.avg_projects_viewed_per_session === null ? "—" : data.avg_projects_viewed_per_session
  ));
}

function renderBars(containerId, items, countKey, emptyText) {
  const wrap = qs(containerId);
  wrap.innerHTML = "";

  if (items.length === 0) {
    wrap.textContent = emptyText;
    return;
  }

  const max = Math.max(...items.map(s => s[countKey]));
  for (const item of items) {
    const row = document.createElement("div");
    row.className = "insightBar";

    const label = document.createElement("div");
    label.className = "insightBarLabel";
    label.textContent = item.title;

    const track = document.createElement("div");
    track.className = "insightBarTrack";
    const fill = document.createElement("div");
    fill.className = "insightBarFill";
    fill.style.width = `${max ? (item[countKey] / max) * 100 : 0}%`;
    track.appendChild(fill);

    const count = document.createElement("div");
    count.className = "insightBarCount";
    count.textContent = item[countKey];

    row.appendChild(label);
    row.appendChild(track);
    row.appendChild(count);
    wrap.appendChild(row);
  }
}

async function loadInsights() {
  const res = await fetch("/api/admin/insights");
  const data = await res.json();
  renderOverview(data);
  renderBars("skillsBars", data.top_skills || [], "presses", "No presses recorded yet.");
  renderBars("projectsBars", data.top_projects || [], "views", "No projects viewed yet.");
}

function renderLogTable(entries) {
  const table = qs("logTable");
  table.innerHTML = "";
  qs("logCount").textContent = entries.length;

  const head = document.createElement("tr");
  head.innerHTML = "<th>Time</th><th>Pin</th><th>Course</th><th>Event</th>";
  table.appendChild(head);

  const recent = entries.slice(-50).reverse();
  for (const e of recent) {
    const tr = document.createElement("tr");
    const time = e.timestamp ? new Date(e.timestamp).toLocaleString() : "";
    tr.innerHTML = `<td>${time}</td><td>${e.pin ?? ""}</td><td>${e.course_id ?? ""}</td><td>${e.event_type ?? ""}</td>`;
    table.appendChild(tr);
  }
}

let fullLog = [];

async function loadLog() {
  const res = await fetch("/api/admin/press-log");
  fullLog = await res.json();
  renderLogTable(fullLog);
}

document.addEventListener("DOMContentLoaded", async () => {
  await Promise.all([loadInsights(), loadLog()]);

  qs("downloadLogBtn").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(fullLog, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `presses-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  });

  qs("clearLogBtn").addEventListener("click", async () => {
    if (!confirm("Clear the press log? Download it first if you want to keep the data.")) return;
    await fetch("/api/admin/press-log", { method: "DELETE" });
    await Promise.all([loadInsights(), loadLog()]);
  });
});
