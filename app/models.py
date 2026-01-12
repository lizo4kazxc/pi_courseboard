from pydantic import BaseModel, Field
from typing import Optional, List

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
