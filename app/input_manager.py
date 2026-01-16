# app/input_manager.py
from __future__ import annotations
import asyncio
from typing import Dict, Optional, Callable
from dataclasses import dataclass

from .config import InputBackend, DEFAULT_BACKEND, ARDUINO_SERIAL_PORT, ARDUINO_BAUD_RATE
from .gpio_manager import GPIOEvent, GPIOManager
from .arduino_manager import ArduinoManager, ArduinoEvent
from .models import ArduinoConfig

@dataclass
class InputEvent:
    """Unified input event for any backend"""
    pin: int  # GPIO pin number
    kind: str  # "down" or "up"
    source: str  # "gpio", "arduino", "mock"
    timestamp: float

class InputManager:
    """Factory and wrapper for different input backends"""
    
    def __init__(
        self,
        backend: InputBackend = DEFAULT_BACKEND,
        course_pins: set[int] = None,
        clear_pin: Optional[int] = None,
        on_event: Callable[[InputEvent], None] = None,
        arduino_config: Optional[ArduinoConfig] = None
    ):
        self.backend = backend
        self.course_pins = course_pins or set()
        self.clear_pin = clear_pin
        self.on_event = on_event
        self.arduino_config = arduino_config
        
        self._gpio_manager: Optional[GPIOManager] = None
        self._arduino_manager: Optional[ArduinoManager] = None
        
        # Mapping from Arduino input IDs to GPIO pins
        self._arduino_to_gpio_map: Dict[int, int] = {}
        
    def _setup_arduino_mapping(self):
        """Setup mapping from Arduino inputs to GPIO pins"""
        if not self.arduino_config:
            return
            
        # Create mapping for course buttons
        for i, arduino_input in enumerate(self.arduino_config.course_inputs):
            if i < len(self.course_pins):
                gpio_pin = list(sorted(self.course_pins))[i]
                self._arduino_to_gpio_map[arduino_input] = gpio_pin
        
        # Add clear button mapping
        if self.arduino_config.clear_input is not None and self.clear_pin:
            self._arduino_to_gpio_map[self.arduino_config.clear_input] = self.clear_pin
    
    def _on_gpio_event(self, event: GPIOEvent):
        """Handle GPIO events"""
        if self.on_event:
            input_event = InputEvent(
                pin=event.gpio_pin,
                kind=event.kind,
                source="gpio",
                timestamp=asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0
            )
            self.on_event(input_event)
    
    def _on_arduino_event(self, event: ArduinoEvent):
        """Handle Arduino events"""
        # Map Arduino input ID to GPIO pin
        gpio_pin = self._arduino_to_gpio_map.get(event.input_id)
        
        if gpio_pin is not None and self.on_event:
            input_event = InputEvent(
                pin=gpio_pin,
                kind=event.kind,
                source="arduino",
                timestamp=event.timestamp
            )
            self.on_event(input_event)
    
    async def start(self):
        """Start the input manager based on selected backend"""
        print(f"Starting input manager with backend: {self.backend.value}")
        
        if self.backend == InputBackend.GPIO:
            # Use GPIO manager
            self._gpio_manager = GPIOManager(
                course_pins=self.course_pins,
                clear_pin=self.clear_pin,
                on_event=self._on_gpio_event,
                bounce_seconds=0.05
            )
            self._gpio_manager.start()
            
        elif self.backend == InputBackend.ARDUINO:
            # Use Arduino manager
            if not self.arduino_config:
                # Create default config if none provided
                self.arduino_config = ArduinoConfig()
                
            self._setup_arduino_mapping()
            
            self._arduino_manager = ArduinoManager(
                serial_port=self.arduino_config.serial_port,
                baud_rate=self.arduino_config.baud_rate,
                on_event=self._on_arduino_event
            )
            
            await self._arduino_manager.start()
            
        elif self.backend in [InputBackend.SIMULATION, InputBackend.MOCK]:
            # Simulation/Mock backend - useful for development
            print(f"Using {self.backend.value} backend - no actual hardware")
            # You could add simulation logic here
            
        else:
            raise ValueError(f"Unknown backend: {self.backend}")
    
    async def stop(self):
        """Stop the input manager"""
        if self._gpio_manager:
            self._gpio_manager.stop()
            self._gpio_manager = None
            
        if self._arduino_manager:
            await self._arduino_manager.stop()
            self._arduino_manager = None
    
    def get_backend_info(self) -> dict:
        """Get information about the current backend"""
        info = {
            "backend": self.backend.value,
            "course_pins": list(sorted(self.course_pins)) if self.course_pins else [],
            "clear_pin": self.clear_pin,
            "active": False
        }
        
        if self.backend == InputBackend.GPIO:
            info["active"] = self._gpio_manager is not None
            info["type"] = "gpio"
            
        elif self.backend == InputBackend.ARDUINO:
            info["active"] = self._arduino_manager is not None
            info["type"] = "arduino"
            if self.arduino_config:
                info.update({
                    "serial_port": self.arduino_config.serial_port,
                    "baud_rate": self.arduino_config.baud_rate,
                    "input_mapping": self._arduino_to_gpio_map
                })
                
        return info