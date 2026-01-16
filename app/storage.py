import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# Import models
from .models import GPIOMap, Course, ArduinoConfig

class JSONStorage:
    def __init__(self, courses_path, gpio_map_path, presses_log_path):
        self.courses_path = Path(courses_path)
        self.gpio_map_path = Path(gpio_map_path)
        self.presses_log_path = Path(presses_log_path)
    
    # GPIO Map methods
    def load_gpio_map(self) -> GPIOMap:
        if not self.gpio_map_path.exists():
            # Return default GPIO map - you might want to adjust this
            return GPIOMap(course_pins=[], clear_pin=0)
        
        with open(self.gpio_map_path, "r") as f:
            raw = f.read()
        
        # Handle both Pydantic v1 and v2
        try:
            # Pydantic v2 method
            return GPIOMap.model_validate_json(raw)
        except AttributeError:
            try:
                # Pydantic v1 method
                return GPIOMap.parse_raw(raw)
            except AttributeError:
                # Fallback to direct JSON parsing
                data = json.loads(raw)
                return GPIOMap(**data)
    
    def save_gpio_map(self, gpio_map: GPIOMap) -> None:
        self.gpio_map_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.gpio_map_path, "w") as f:
            # Handle both Pydantic v1 and v2
            if hasattr(gpio_map, 'model_dump_json'):
                # Pydantic v2
                f.write(gpio_map.model_dump_json(indent=2))
            elif hasattr(gpio_map, 'json'):
                # Pydantic v1
                f.write(gpio_map.json(indent=2))
            else:
                # Fallback
                f.write(json.dumps(gpio_map.dict(), indent=2))
    
    # Courses methods
    def load_courses(self) -> List[Course]:
        if not self.courses_path.exists():
            return []
        
        with open(self.courses_path, "r") as f:
            data = json.load(f)
        
        courses = []
        for item in data:
            try:
                # Handle both Pydantic v1 and v2
                try:
                    # Pydantic v2 method
                    course = Course.model_validate(item)
                except AttributeError:
                    # Pydantic v1 method
                    course = Course.parse_obj(item)
                courses.append(course)
            except Exception as e:
                print(f"Error loading course {item.get('course_id', 'unknown')}: {e}")
        
        return courses
    
    def save_courses(self, courses: List[Course]) -> None:
        self.courses_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.courses_path, "w") as f:
            # Convert courses to dictionaries
            courses_data = []
            for course in courses:
                if hasattr(course, 'model_dump'):
                    # Pydantic v2
                    courses_data.append(course.model_dump())
                elif hasattr(course, 'dict'):
                    # Pydantic v1
                    courses_data.append(course.dict())
                else:
                    # Fallback
                    courses_data.append(dict(course))
            
            json.dump(courses_data, f, indent=2)
    
    def get_courses_by_pin(self) -> Dict[int, Course]:
        """Return mapping from GPIO pin to Course object."""
        courses = self.load_courses()
        result = {}
        for course in courses:
            # Use button_gpio_pin field (not gpio_pin)
            if hasattr(course, 'button_gpio_pin') and course.button_gpio_pin is not None:
                result[course.button_gpio_pin] = course
        return result
    
    def upsert_course(self, course: Course) -> None:
        """Insert or update a course."""
        courses = self.load_courses()
        
        # Find existing course with same ID
        found = False
        for i, existing in enumerate(courses):
            if existing.course_id == course.course_id:
                courses[i] = course
                found = True
                break
        
        # If not found, add new course
        if not found:
            courses.append(course)
        
        self.save_courses(courses)
    
    def delete_course(self, course_id: str) -> bool:
        """Delete a course by ID. Returns True if deleted, False if not found."""
        courses = self.load_courses()
        
        new_courses = [c for c in courses if c.course_id != course_id]
        
        if len(new_courses) == len(courses):
            return False  # No course was deleted
        
        self.save_courses(new_courses)
        return True
    
    # Press log methods
    def log_press(self, pin: int, course_id: Optional[str], event_type: str) -> None:
        """Log a button press event."""
        if not self.presses_log_path.exists():
            log_entries = []
        else:
            with open(self.presses_log_path, "r") as f:
                log_entries = json.load(f)
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "pin": pin,
            "course_id": course_id,
            "event_type": event_type
        }
        
        log_entries.append(log_entry)
        
        # Keep only last 1000 entries to prevent file from growing too large
        if len(log_entries) > 1000:
            log_entries = log_entries[-1000:]
        
        self.presses_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.presses_log_path, "w") as f:
            json.dump(log_entries, f, indent=2)
    
    def load_presses_log(self) -> List[Dict[str, Any]]:
        """Load the press log history."""
        if not self.presses_log_path.exists():
            return []
        
        with open(self.presses_log_path, "r") as f:
            return json.load(f)
    
    def load_arduino_config(self) -> ArduinoConfig:
        arduino_config_path = self.courses_path.parent / "arduino_config.json"
        
        if not arduino_config_path.exists():
            # Default config
            return ArduinoConfig()
        
        with open(arduino_config_path, "r") as f:
            raw = f.read()
        
        try:
            return ArduinoConfig.model_validate_json(raw)
        except AttributeError:
            return ArduinoConfig.parse_raw(raw)
    
    def save_arduino_config(self, config: ArduinoConfig) -> None:
        arduino_config_path = self.courses_path.parent / "arduino_config.json"
        arduino_config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(arduino_config_path, "w") as f:
            if hasattr(config, 'model_dump_json'):
                f.write(config.model_dump_json(indent=2))
            else:
                f.write(config.json(indent=2))