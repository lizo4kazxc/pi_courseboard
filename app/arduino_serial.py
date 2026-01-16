import threading
import serial
import time
from .gpio_manager import GPIOEvent

class ArduinoSerialManager:
    def __init__(self, port: str, baudrate: int, pin_map: dict[int, int], on_event):
        """
        pin_map: {button_number: gpio_pin}
        example: {1: 17, 2: 27}
        """
        self.port = port
        self.baudrate = baudrate
        self.pin_map = pin_map
        self.on_event = on_event
        self._running = False
        self._thread = None
        self.ser = None

    def start(self):
        self._running = True
        self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("Arduino serial listener started")

    def stop(self):
        self._running = False
        if self.ser:
            self.ser.close()

    def _loop(self):
        while self._running:
            try:
                line = self.ser.readline().decode().strip()
                if line.startswith("BTN_"):
                    btn_num = int(line.replace("BTN_", ""))
                    if btn_num in self.pin_map:
                        pin = self.pin_map[btn_num]

                        # simulate button press + release
                        self.on_event(GPIOEvent(pin, "down"))
                        time.sleep(0.05)
                        self.on_event(GPIOEvent(pin, "up"))
            except Exception:
                pass
                