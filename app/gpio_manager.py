from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Set

@dataclass
class GPIOEvent:
    gpio_pin: int
    kind: str  # "down" or "up"

class GPIOManager:
    """
    Uses gpiozero when running on Raspberry Pi.
    Falls back to a no op manager if gpiozero is unavailable..
    """
    def __init__(
        self,
        course_pins: Set[int],
        clear_pin: int,
        on_event: Callable[[GPIOEvent], None],
        bounce_seconds: float = 0.05,
    ):
        self.course_pins = set(course_pins)
        self.clear_pin = clear_pin
        self.on_event = on_event
        self.bounce_seconds = bounce_seconds

        self._buttons: Dict[int, object] = {}
        self._last_down: Dict[int, float] = {}

    def start(self) -> None:
        try:
            from gpiozero import Button
        except Exception:
            print("gpiozero not available, GPIO disabled")
            return

        pins = sorted(list(self.course_pins | {self.clear_pin}))
        for pin in pins:
            btn = Button(pin, pull_up=True, bounce_time=self.bounce_seconds, hold_time=0.0)
            btn.when_pressed = self._make_pressed_handler(pin)
            btn.when_released = self._make_released_handler(pin)
            self._buttons[pin] = btn

        print(f"GPIO ready. Listening on pins: {pins}")

    def stop(self) -> None:
        for btn in self._buttons.values():
            try:
                btn.close()
            except Exception:
                pass
        self._buttons.clear()

    def _make_pressed_handler(self, pin: int):
        def handler():
            now = time.monotonic()
            last = self._last_down.get(pin, 0.0)
            if now - last < self.bounce_seconds:
                return
            self._last_down[pin] = now
            self.on_event(GPIOEvent(gpio_pin=pin, kind="down"))
        return handler

    def _make_released_handler(self, pin: int):
        def handler():
            self.on_event(GPIOEvent(gpio_pin=pin, kind="up"))
        return handler
