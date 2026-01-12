import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .models import Course, GPIOMap

class JSONStorage:
    """
    Thread safe JSON storage with atomic writes.
    """
    def __init__(self, courses_path: Path, gpio_map_path: Path, presses_log_path: Path):
        self.courses_path = courses_path
        self.gpio_map_path = gpio_map_path
        self.presses_log_path = presses_log_path
        self._lock = threading.Lock()

        self.courses_path.parent.mkdir(parents=True, exist_ok=True)
        self.gpio_map_path.parent.mkdir(parents=True, exist_ok=True)
        self.presses_log_path.parent.mkdir(parents=True, exist_ok=True)

    def _atomic_write(self, path: Path, data: str) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(data, encoding="utf-8")
        tmp.replace(path)

    def load_gpio_map(self) -> GPIOMap:
        if not self.gpio_map_path.exists():
            raise FileNotFoundError(f"Missing GPIO map file at {self.gpio_map_path}")
        raw = self.gpio_map_path.read_text(encoding="utf-8")
        return GPIOMap.model_validate_json(raw)

    def load_courses(self) -> List[Course]:
        if not self.courses_path.exists():
            return []
        raw = self.courses_path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        courses: List[Course] = []
        for item in data:
            try:
                courses.append(Course.model_validate(item))
            except Exception:
                continue
        return courses

    def save_courses(self, courses: List[Course]) -> None:
        with self._lock:
            payload = json.dumps([c.model_dump() for c in courses], indent=2, ensure_ascii=False)
            self._atomic_write(self.courses_path, payload)

    def get_courses_by_pin(self) -> Dict[int, Course]:
        courses = self.load_courses()
        mapping: Dict[int, Course] = {}
        for c in courses:
            mapping[c.button_gpio_pin] = c
        return mapping

    def upsert_course(self, course: Course) -> None:
        with self._lock:
            courses = self.load_courses()
            found = False
            for i, c in enumerate(courses):
                if c.course_id == course.course_id:
                    courses[i] = course
                    found = True
                    break
            if not found:
                courses.append(course)
            self.save_courses(courses)

    def delete_course(self, course_id: str) -> bool:
        with self._lock:
            courses = self.load_courses()
            new_courses = [c for c in courses if c.course_id != course_id]
            if len(new_courses) == len(courses):
                return False
            self.save_courses(new_courses)
            return True

    def log_press(self, gpio_pin: int, course_id: Optional[str], action: str) -> None:
        entry = {
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "gpio_pin": gpio_pin,
            "course_id": course_id,
            "action": action,
        }
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            with self.presses_log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
