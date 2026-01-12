import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

COURSES_PATH = DATA_DIR / "courses.json"
GPIO_MAP_PATH = DATA_DIR / "gpio_map.json"
PRESSES_LOG_PATH = LOG_DIR / "presses.log"

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123")

APP_TITLE = "KDG Course Board"
