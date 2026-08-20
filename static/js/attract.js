// Any interaction wakes the kiosk back up to the skill-selection screen.
function goToStart() {
  window.location.href = "/";
}

document.addEventListener("keydown", goToStart);
document.addEventListener("click", goToStart);
document.addEventListener("touchstart", goToStart);

// Physical Arduino/GPIO button presses don't fire browser DOM events, so
// the listeners above never see them. Open the same WS the main app uses
// and treat any real input broadcast as a wake-up too. Skip the initial
// "state" snapshot sent right on connect - that's not an actual button press.
function connectWakeWs() {
  const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;
  console.log("[attract] connecting to", url);
  const ws = new WebSocket(url);
  ws.addEventListener("open", () => console.log("[attract] ws open"));
  ws.addEventListener("error", (e) => console.log("[attract] ws error", e));
  ws.addEventListener("message", (ev) => {
    console.log("[attract] ws message", ev.data);
    let msg = null;
    try { msg = JSON.parse(ev.data); } catch { return; }
    if (msg && msg.type && msg.type !== "state" && msg.type !== "hello") {
      console.log("[attract] waking up due to", msg.type);
      goToStart();
    }
  });
  ws.addEventListener("close", () => {
    console.log("[attract] ws closed, retrying in 1s");
    setTimeout(connectWakeWs, 1000);
  });
}
connectWakeWs();
