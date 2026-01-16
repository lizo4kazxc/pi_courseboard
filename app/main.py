import asyncio
import base64
from typing import Any, Dict, List, Optional, Set

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import (
    APP_TITLE,
    ADMIN_PASS,
    ADMIN_USER,
    COURSES_PATH,
    GPIO_MAP_PATH,
    PRESSES_LOG_PATH,
    BACKEND_CONFIG_PATH,
    DEFAULT_BACKEND,
    InputBackend
)
from .models import Course, ArduinoConfig
from .storage import JSONStorage
from .input_manager import InputManager, InputEvent  # NEW

app = FastAPI(title=APP_TITLE)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

storage = JSONStorage(COURSES_PATH, GPIO_MAP_PATH, PRESSES_LOG_PATH)

ws_clients: Set[WebSocket] = set()
ws_lock = asyncio.Lock()

pressed_pins: Set[int] = set()
history_course_ids: List[str] = []

course_by_pin: Dict[int, Course] = {}
clear_pin: Optional[int] = None
course_pins: Set[int] = set()

input_manager: Optional[InputManager] = None  # NEW: Replace gpio/arduino managers

def _check_basic_auth(request: Request) -> None:
    # ... (keep existing code) ...

def require_admin(request: Request):
    _check_basic_auth(request)
    return True

async def ws_broadcast(message: Dict[str, Any]) -> None:
    dead: List[WebSocket] = []
    async with ws_lock:
        for ws in ws_clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            ws_clients.discard(ws)

def _course_for_pin(pin: int) -> Optional[Course]:
    return course_by_pin.get(pin)

def _reset_history() -> None:
    history_course_ids.clear()

def _state_payload() -> Dict[str, Any]:
    courses = storage.load_courses()
    
    # Get backend info if available
    backend_info = {}
    if input_manager:
        backend_info = input_manager.get_backend_info()
    
    return {
        "type": "state",
        "pressed_pins": sorted(list(pressed_pins)),
        "history_course_ids": list(history_course_ids),
        "courses": [c.model_dump() for c in courses],
        "clear_pin": clear_pin,
        "backend": backend_info  # NEW: Include backend info
    }

def on_input_event(event: InputEvent) -> None:  # UPDATED: Changed from on_gpio_event
    global pressed_pins, clear_pin
    
    pin = event.pin
    kind = event.kind
    
    print(f"Input event: pin={pin}, kind={kind}, source={event.source}")
    
    if kind == "down":
        pressed_pins.add(pin)

        if clear_pin is not None and pin == clear_pin:
            storage.log_press(pin, None, f"clear_down_{event.source}")
            _reset_history()
            asyncio.create_task(ws_broadcast({"type": "history_cleared"}))
        else:
            course = _course_for_pin(pin)
            course_id = course.course_id if course else None
            storage.log_press(pin, course_id, f"button_down_{event.source}")
            if course:
                history_course_ids.append(course.course_id)
                asyncio.create_task(ws_broadcast({
                    "type": "course_added", 
                    "course": course.model_dump()
                }))

        asyncio.create_task(ws_broadcast({
            "type": "pressed_update", 
            "pressed_pins": sorted(list(pressed_pins))
        }))

    elif kind == "up":
        pressed_pins.discard(pin)
        storage.log_press(pin, None, f"button_up_{event.source}")
        asyncio.create_task(ws_broadcast({
            "type": "pressed_update", 
            "pressed_pins": sorted(list(pressed_pins))
        }))

@app.on_event("startup")
async def startup() -> None:
    global course_by_pin, clear_pin, course_pins, input_manager
    
    # Load GPIO map (still needed for pin assignments)
    gpio_map = storage.load_gpio_map()
    clear_pin = gpio_map.clear_pin
    course_pins = set(gpio_map.course_pins)
    
    # Load courses
    course_by_pin = storage.get_courses_by_pin()
    
    # Load Arduino config if needed
    arduino_config = None
    if DEFAULT_BACKEND == InputBackend.ARDUINO:
        try:
            arduino_config = storage.load_arduino_config()
        except Exception as e:
            print(f"Could not load Arduino config, using defaults: {e}")
            arduino_config = ArduinoConfig()
    
    # Create and start input manager
    input_manager = InputManager(
        backend=DEFAULT_BACKEND,
        course_pins=course_pins,
        clear_pin=clear_pin,
        on_event=on_input_event,
        arduino_config=arduino_config
    )
    
    await input_manager.start()
    print(f"Input manager started with backend: {DEFAULT_BACKEND.value}")

@app.on_event("shutdown")
async def shutdown() -> None:
    global input_manager
    if input_manager:
        await input_manager.stop()
        input_manager = None

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": APP_TITLE},
    )

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, ok: bool = Depends(require_admin)):
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "title": f"{APP_TITLE} Admin"},
    )

@app.get("/api/state")
async def get_state():
    return JSONResponse(_state_payload())

@app.get("/api/courses")
async def list_courses():
    courses = storage.load_courses()
    return [c.model_dump() for c in courses]

@app.post("/api/admin/courses")
async def create_course(course: Course, ok: bool = Depends(require_admin)):
    storage.upsert_course(course)
    _reload_courses_cache()
    await ws_broadcast({"type": "courses_updated"})
    return {"ok": True}

@app.put("/api/admin/courses/{course_id}")
async def update_course(course_id: str, course: Course, ok: bool = Depends(require_admin)):
    if course.course_id != course_id:
        raise HTTPException(status_code=400, detail="course_id in path and body must match")
    storage.upsert_course(course)
    _reload_courses_cache()
    await ws_broadcast({"type": "courses_updated"})
    return {"ok": True}

@app.delete("/api/admin/courses/{course_id}")
async def delete_course(course_id: str, ok: bool = Depends(require_admin)):
    deleted = storage.delete_course(course_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Course not found")
    _reload_courses_cache()
    await ws_broadcast({"type": "courses_updated"})
    return {"ok": True}

@app.post("/api/clear")
async def clear_history():
    _reset_history()
    await ws_broadcast({"type": "history_cleared"})
    return {"ok": True}

def _reload_courses_cache() -> None:
    global course_by_pin
    course_by_pin = storage.get_courses_by_pin()

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    async with ws_lock:
        ws_clients.add(ws)
    try:
        await ws.send_json({"type": "hello", "title": APP_TITLE})
        await ws.send_json(_state_payload())
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        async with ws_lock:
            ws_clients.discard(ws)

@app.get("/api/admin/arduino-config")
async def get_arduino_config(ok: bool = Depends(require_admin)):
    try:
        config = storage.load_arduino_config()
        return config.model_dump()
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to load Arduino config: {str(e)}"}
        )

@app.post("/api/admin/arduino-config")
async def update_arduino_config(config: ArduinoConfig, ok: bool = Depends(require_admin)):
    try:
        storage.save_arduino_config(config)
        
        # Restart input manager if using Arduino backend
        if input_manager and input_manager.backend == InputBackend.ARDUINO:
            await input_manager.stop()
            input_manager.arduino_config = config
            await input_manager.start()
            
        return {"ok": True, "message": "Arduino configuration updated"}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to update Arduino config: {str(e)}"}
        )
@app.post("/api/admin/change-backend")
async def change_backend(backend: InputBackend, ok: bool = Depends(require_admin)):
    global input_manager
    
    try:
        if input_manager:
            await input_manager.stop()
        
        # Reload with new backend
        arduino_config = None
        if backend == InputBackend.ARDUINO:
            arduino_config = storage.load_arduino_config()
            
        input_manager = InputManager(
            backend=backend,
            course_pins=course_pins,
            clear_pin=clear_pin,
            on_event=on_input_event,
            arduino_config=arduino_config
        )
        
        await input_manager.start()
        
        # Update environment or config file to persist the change
        # (You might want to save this to a config file)
        
        return {
            "ok": True, 
            "message": f"Backend changed to {backend.value}",
            "backend_info": input_manager.get_backend_info()
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to change backend: {str(e)}"}
        )