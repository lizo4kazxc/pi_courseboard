# app/config.py
import os
from pathlib import Path
from enum import Enum

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

COURSES_PATH = DATA_DIR / "courses.json"
GPIO_MAP_PATH = DATA_DIR / "gpio_map.json"
PRESSES_LOG_PATH = LOG_DIR / "presses.log"
BACKEND_CONFIG_PATH = DATA_DIR / "backend_config.json"  # New

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123")

APP_TITLE = "KDG Course Board"

# Backend types
class InputBackend(str, Enum):
    GPIO = "gpio"
    ARDUINO = "arduino"
    SIMULATION = "simulation"
    MOCK = "mock"  # For backward compatibility

# Default backend (can be overridden by environment variable)
DEFAULT_BACKEND = InputBackend(os.getenv("INPUT_BACKEND", "gpio"))

# Arduino settings (only used if backend is ARDUINO)
ARDUINO_SERIAL_PORT = os.getenv("ARDUINO_SERIAL_PORT", "/dev/ttyACM0")
ARDUINO_BAUD_RATE = int(os.getenv("ARDUINO_BAUD_RATE", "9600"))

# GPIO settings (only used if backend is GPIO)
GPIO_MODE = os.getenv("GPIO_MODE", "BCM")  # BCM or BOARD
GPIO_PULL_UP = os.getenv("GPIO_PULL_UP", "true").lower() == "true"