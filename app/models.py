from pydantic import BaseModel, Field
from typing import List, Optional

class Course(BaseModel):
    course_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    room: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    overview: str = Field(..., min_length=1)
    button_gpio_pin: int
    image_path: Optional[str] = ""

class GPIOMap(BaseModel):
    course_pins: List[int] = Field(default_factory=list)
    clear_pin: int

# Add to app/models.py
class ArduinoConfig(BaseModel):
    """Arduino configuration - which inputs map to which actions"""
    serial_port: str = "/dev/ttyACM0"  # Common Arduino port on Raspberry Pi
    baud_rate: int = 9600
    course_inputs: List[int] = Field(default_factory=list)  # Which inputs are course buttons
    clear_input: Optional[int] = None  # Which input is the clear button
    input_count: int = 10  # Total number of inputs

class SimulatedPress(BaseModel):
    """Body for the keyboard-simulated button press debug endpoint."""
    pin: int
    kind: str  # "down" or "up"

class Project(BaseModel):
    """A placeholder project combining multiple skills/courses."""
    project_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    skill_ids: List[str] = Field(default_factory=list)  # course_ids this project combines
    image_path: Optional[str] = ""
    image_paths: List[str] = Field(default_factory=list)  # gallery slides for the picture cycle