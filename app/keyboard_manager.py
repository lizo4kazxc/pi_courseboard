import threading
import sys
import time
from typing import Callable, Dict

from .gpio_manager import GPIOEvent

class KeyboardManager:
    """
    Listens for key presses in the terminal and maps them to GPIOEvent.
    Intended for development/testing only.
    """

    def __init__(
        self,
        key_to_pin: Dict[str, int],
        clear_key: str,
        on_event: Callable[[GPIOEvent], None],
    ):
        self.key_to_pin = {k.lower(): v for k, v in key_to_pin.items()}
        self.clear_key = clear_key.lower()
        self.on_event = on_event
        self._thread = None
        self._running = False
        pin = clear_pin

        

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print("Keyboard simulation enabled")

    def stop(self):
        self._running = False

    def _run(self):
        print("Press mapped keys to simulate GPIO buttons (Ctrl+C to quit)")
        while self._running:
            key = sys.stdin.read(1)
            if not key:
                continue

            key = key.lower()

            if key == "\n" and self.clear_key == "enter":
                self.on_event(GPIOEvent(gpio_pin=-1, kind="down"))
                self.on_event(GPIOEvent(gpio_pin=-1, kind="up"))
                continue

            if key in self.key_to_pin:
                pin = self.key_to_pin[key]
                self.on_event(GPIOEvent(gpio_pin=pin, kind="down"))
                time.sleep(0.05)
                self.on_event(GPIOEvent(gpio_pin=pin, kind="up"))
