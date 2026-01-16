import asyncio
import base64
from typing import Any, Dict, List, Optional, Set
#from .arduino_serial import ArduinoSerialManager

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
)
from .gpio_manager import GPIOEvent, GPIOManager
from .models import Course
from .storage import JSONStorage

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

event_loop: Optional[asyncio.AbstractEventLoop] = None
gpio: Optional[GPIOManager] = None
arduino = None  # FIXED: Moved to global scope

def _check_basic_auth(request: Request) -> None:
    header = request.headers.get("authorization")
    if not header or not header.lower().startswith("basic "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    try:
        b64 = header.split(" ", 1)[1].strip()
        decoded = base64.b64decode(b64).decode("utf-8")
        username, password = decoded.split(":", 1)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication header",
            headers={"WWW-Authenticate": "Basic"},
        )
    if username != ADMIN_USER or password != ADMIN_PASS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

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
    return {
        "type": "state",
        "pressed_pins": sorted(list(pressed_pins)),
        "history_course_ids": list(history_course_ids),
        "courses": [c.model_dump() for c in courses],
        "clear_pin": clear_pin,
    }

def on_gpio_event(evt: GPIOEvent) -> None:
    global pressed_pins, clear_pin, event_loop

    pin = evt.gpio_pin
    kind = evt.kind

    if kind == "down":
        pressed_pins.add(pin)

        if clear_pin is not None and pin == clear_pin:
            storage.log_press(pin, None, "clear_down")
            _reset_history()
            if event_loop:
                asyncio.run_coroutine_threadsafe(ws_broadcast({"type": "history_cleared"}), event_loop)
        else:
            course = _course_for_pin(pin)
            # FIXED: Check if course is not None before accessing course_id
            course_id = course.course_id if course else None
            storage.log_press(pin, course_id, "button_down")
            if course:
                history_course_ids.append(course.course_id)
                if event_loop:
                    asyncio.run_coroutine_threadsafe(
                        ws_broadcast({"type": "course_added", "course": course.model_dump()}),
                        event_loop,
                    )

        if event_loop:
            asyncio.run_coroutine_threadsafe(
                ws_broadcast({"type": "pressed_update", "pressed_pins": sorted(list(pressed_pins))}),
                event_loop,
            )

    elif kind == "up":
        pressed_pins.discard(pin)
        storage.log_press(pin, None, "button_up")
        if event_loop:
            asyncio.run_coroutine_threadsafe(
                ws_broadcast({"type": "pressed_update", "pressed_pins": sorted(list(pressed_pins))}),
                event_loop,  # FIXED: Added missing second argument
            )

@app.on_event("startup")
async def startup() -> None:
    # FIXED: Removed arduino = None from here and moved it to global scope
    global course_by_pin, clear_pin, course_pins, event_loop, gpio, arduino

    event_loop = asyncio.get_running_loop()

    gpio_map = storage.load_gpio_map()
    clear_pin = gpio_map.clear_pin
    course_pins = set(gpio_map.course_pins)

    course_by_pin = storage.get_courses_by_pin()

    gpio = GPIOManager(course_pins=course_pins, clear_pin=clear_pin, on_event=on_gpio_event)
    gpio.start()

@app.on_event("shutdown")
async def shutdown() -> None:
    global gpio
    if gpio:
        gpio.stop()
        gpio = None

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