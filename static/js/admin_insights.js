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

function renderSkillBars(data) {
  const wrap = qs("skillsBars");
  wrap.innerHTML = "";

  const topSkills = data.top_skills || [];
  if (topSkills.length === 0) {
    wrap.textContent = "No presses recorded yet.";
    return;
  }

  const max = Math.max(...topSkills.map(s => s.presses));
  for (const skill of topSkills) {
    const row = document.createElement("div");
    row.className = "insightBar";

    const label = document.createElement("div");
    label.className = "insightBarLabel";
    label.textContent = skill.title;

    const track = document.createElement("div");
    track.className = "insightBarTrack";
    const fill = document.createElement("div");
    fill.className = "insightBarFill";
    fill.style.width = `${max ? (skill.presses / max) * 100 : 0}%`;
    track.appendChild(fill);

    const count = document.createElement("div");
    count.className = "insightBarCount";
    count.textContent = skill.presses;

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
  renderSkillBars(data);
}

document.addEventListener("DOMContentLoaded", loadInsights);
