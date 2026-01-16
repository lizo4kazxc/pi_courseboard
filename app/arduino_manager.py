# app/arduino_manager.py
import asyncio
import serial
import serial_asyncio
from typing import Callable, Optional, Dict
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class ArduinoEvent:
    input_id: int  # 0-9 for the 10 inputs
    kind: str  # "down" or "up"
    timestamp: float

class ArduinoManager:
    def __init__(
        self,
        serial_port: str = "/dev/ttyACM0",
        baud_rate: int = 9600,
        on_event: Callable[[ArduinoEvent], None] = None
    ):
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.on_event = on_event
        self._running = False
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        
        # Track button states (0-9 inputs)
        self.button_states = [False] * 10
        
    async def start(self):
        """Start reading from Arduino serial port"""
        self._running = True
        logger.info(f"Starting Arduino manager on {self.serial_port} at {self.baud_rate} baud")
        
        try:
            # Open serial connection
            self._reader, self._writer = await serial_asyncio.open_serial_connection(
                url=self.serial_port,
                baudrate=self.baud_rate
            )
            
            # Start reading loop
            asyncio.create_task(self._read_loop())
            
        except Exception as e:
            logger.error(f"Failed to start Arduino manager: {e}")
            raise
    
    async def stop(self):
        """Stop the Arduino manager"""
        self._running = False
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        logger.info("Arduino manager stopped")
    
    async def _read_loop(self):
        """Main loop for reading serial data"""
        while self._running and self._reader:
            try:
                # Read line from Arduino
                line = await self._reader.readline()
                if not line:
                    continue
                    
                # Decode and parse
                message = line.decode('utf-8', errors='ignore').strip()
                await self._parse_message(message)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error reading from Arduino: {e}")
                await asyncio.sleep(1)  # Wait before retrying
    
    async def _parse_message(self, message: str):
        """Parse messages from Arduino"""
        # Example message formats:
        # "BTN:1:DOWN" - Button 1 pressed down
        # "BTN:3:UP"   - Button 3 released
        # "STATE:0101010101" - Bitmask of all 10 inputs
        
        if message.startswith("BTN:"):
            # Single button event
            parts = message.split(":")
            if len(parts) == 4:
                try:
                    input_id = int(parts[1])
                    kind = parts[2].lower()
                    
                    if 0 <= input_id < 10 and kind in ["down", "up"]:
                        # Update state
                        self.button_states[input_id] = (kind == "down")
                        
                        # Trigger event callback
                        if self.on_event:
                            event = ArduinoEvent(
                                input_id=input_id,
                                kind=kind,
                                timestamp=asyncio.get_event_loop().time()
                            )
                            self.on_event(event)
                            
                except (ValueError, IndexError):
                    logger.warning(f"Failed to parse button message: {message}")
        
        elif message.startswith("STATE:"):
            # Full state update (bitmask)
            state_str = message[6:]  # Remove "STATE:"
            if len(state_str) == 10:  # Should be 10 characters for 10 inputs
                for i, char in enumerate(state_str):
                    if i < 10:
                        new_state = (char == '1')
                        old_state = self.button_states[i]
                        
                        if new_state != old_state:
                            self.button_states[i] = new_state
                            if self.on_event:
                                event = ArduinoEvent(
                                    input_id=i,
                                    kind="down" if new_state else "up",
                                    timestamp=asyncio.get_event_loop().time()
                                )
                                self.on_event(event)