// Any interaction wakes the kiosk back up to the skill-selection screen.
function goToStart() {
  window.location.href = "/";
}

document.addEventListener("keydown", goToStart);
document.addEventListener("click", goToStart);
document.addEventListener("touchstart", goToStart);
