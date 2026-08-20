import asyncio
import base64
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect, status
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
from .models import Course, ArduinoConfig, SimulatedPress, Project
from .storage import JSONStorage
from .input_manager import InputManager, InputEvent  # NEW

app = FastAPI(title=APP_TITLE)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

UPLOADS_DIR = Path("static") / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

storage = JSONStorage(COURSES_PATH, GPIO_MAP_PATH, PRESSES_LOG_PATH)

ws_clients: Set[WebSocket] = set()
ws_lock = asyncio.Lock()

pressed_pins: Set[int] = set()
history_course_ids: List[str] = []
confirmed: bool = False
project_sequence: List[str] = []
project_index: int = 0

course_by_pin: Dict[int, Course] = {}
clear_pin: Optional[int] = None
course_pins: Set[int] = set()

input_manager: Optional[InputManager] = None  # NEW: Replace gpio/arduino managers

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
    global confirmed, project_sequence, project_index
    history_course_ids.clear()
    confirmed = False
    project_sequence = []
    project_index = 0

def _matching_project_ids() -> List[str]:
    """Projects sharing >=1 skill with the current selection, best match first."""
    selected = set(history_course_ids)
    projects = storage.load_projects()
    scored = [
        (project, len(set(project.skill_ids) & selected))
        for project in projects
    ]
    scored = [(project, score) for project, score in scored if score > 0]
    scored.sort(key=lambda item: item[1], reverse=True)
    return [project.project_id for project, _ in scored]

def _state_payload() -> Dict[str, Any]:
    courses = storage.load_courses()
    projects = storage.load_projects()

    # Get backend info if available
    backend_info = {}
    if input_manager:
        backend_info = input_manager.get_backend_info()

    return {
        "type": "state",
        "pressed_pins": sorted(list(pressed_pins)),
        "history_course_ids": list(history_course_ids),
        "courses": [c.model_dump() for c in courses],
        "projects": [p.model_dump() for p in projects],
        "clear_pin": clear_pin,
        "confirmed": confirmed,
        "project_sequence": list(project_sequence),
        "project_index": project_index,
        "backend": backend_info  # NEW: Include backend info
    }

def on_input_event(event: InputEvent) -> None:  # UPDATED: Changed from on_gpio_event
    global pressed_pins, clear_pin, confirmed, project_sequence, project_index

    pin = event.pin
    kind = event.kind

    print(f"Input event: pin={pin}, kind={kind}, source={event.source}")

    if kind == "down":
        pressed_pins.add(pin)

        if clear_pin is not None and pin == clear_pin:
            if not confirmed and len(history_course_ids) >= 1:
                # Confirm: move from skill selection to the projects step.
                confirmed = True
                project_sequence = _matching_project_ids()
                project_index = 0
                shown_project_id = project_sequence[0] if project_sequence else None
                suffix = f":{shown_project_id}" if shown_project_id else ""
                storage.log_press(pin, None, f"confirm_down_{event.source}{suffix}")
                asyncio.create_task(ws_broadcast({
                    "type": "confirmed",
                    "project_sequence": list(project_sequence),
                    "project_index": project_index,
                }))
            elif confirmed and project_index < len(project_sequence) - 1:
                # Not on the last project yet: advance instead of exiting.
                project_index += 1
                shown_project_id = project_sequence[project_index]
                storage.log_press(pin, None, f"project_advance_{event.source}:{shown_project_id}")
                asyncio.create_task(ws_broadcast({
                    "type": "project_advanced",
                    "project_index": project_index,
                }))
            else:
                # Either exiting from the last project, or clearing an empty selection.
                storage.log_press(pin, None, f"clear_down_{event.source}")
                _reset_history()
                asyncio.create_task(ws_broadcast({"type": "history_cleared"}))
        elif not confirmed:
            course = _course_for_pin(pin)
            course_id = course.course_id if course else None
            storage.log_press(pin, course_id, f"button_down_{event.source}")
            if course:
                if course.course_id in history_course_ids:
                    history_course_ids.remove(course.course_id)
                    asyncio.create_task(ws_broadcast({
                        "type": "course_removed",
                        "course_id": course.course_id
                    }))
                else:
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

def on_raw_input_event(input_id: int, kind: str) -> None:
    """Diagnostic-only: fires for every raw Arduino input, mapped or not.
    Used by the admin hardware test panel; doesn't touch app state."""
    asyncio.create_task(ws_broadcast({
        "type": "raw_input",
        "input_id": input_id,
        "kind": kind,
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

    # An admin may have switched backends via /api/admin/change-backend since
    # the last restart - that choice is persisted to backend_config.json and
    # takes priority over the .env/config.py default.
    active_backend = DEFAULT_BACKEND
    override = storage.load_backend_override()
    if override:
        try:
            active_backend = InputBackend(override)
        except ValueError:
            print(f"Ignoring invalid persisted backend override: {override!r}")

    # Load Arduino config if needed
    arduino_config = None
    if active_backend == InputBackend.ARDUINO:
        try:
            arduino_config = storage.load_arduino_config()
        except Exception as e:
            print(f"Could not load Arduino config, using defaults: {e}")
            arduino_config = ArduinoConfig()

    # Create and start input manager
    input_manager = InputManager(
        backend=active_backend,
        course_pins=course_pins,
        clear_pin=clear_pin,
        on_event=on_input_event,
        arduino_config=arduino_config,
        on_raw_event=on_raw_input_event
    )

    await input_manager.start()
    print(f"Input manager started with backend: {active_backend.value}")

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

@app.get("/attract", response_class=HTMLResponse)
async def attract_page(request: Request):
    return templates.TemplateResponse(
        "attract.html",
        {"request": request, "title": APP_TITLE},
    )

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, ok: bool = Depends(require_admin)):
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "title": f"{APP_TITLE} Admin"},
    )

@app.get("/admin/insights", response_class=HTMLResponse)
async def admin_insights_page(request: Request, ok: bool = Depends(require_admin)):
    return templates.TemplateResponse(
        "admin_insights.html",
        {"request": request, "title": f"{APP_TITLE} Insights"},
    )

@app.get("/admin/hardware", response_class=HTMLResponse)
async def admin_hardware_page(request: Request, ok: bool = Depends(require_admin)):
    return templates.TemplateResponse(
        "admin_hardware.html",
        {"request": request, "title": f"{APP_TITLE} Hardware"},
    )

@app.get("/admin/projects", response_class=HTMLResponse)
async def admin_projects_page(request: Request, ok: bool = Depends(require_admin)):
    return templates.TemplateResponse(
        "admin_projects.html",
        {"request": request, "title": f"{APP_TITLE} Projects"},
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

@app.post("/api/admin/upload-image")
async def upload_image(file: UploadFile = File(...), ok: bool = Depends(require_admin)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type {ext!r}. Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}",
        )

    contents = await file.read()
    max_bytes = 8 * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(status_code=400, detail="Image too large (max 8MB)")

    filename = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOADS_DIR / filename
    dest.write_bytes(contents)

    return {"ok": True, "path": f"/static/uploads/{filename}"}

@app.get("/api/projects")
async def list_projects():
    projects = storage.load_projects()
    return [p.model_dump() for p in projects]

@app.post("/api/admin/projects")
async def create_project(project: Project, ok: bool = Depends(require_admin)):
    storage.upsert_project(project)
    await ws_broadcast({"type": "projects_updated"})
    return {"ok": True}

@app.put("/api/admin/projects/{project_id}")
async def update_project(project_id: str, project: Project, ok: bool = Depends(require_admin)):
    if project.project_id != project_id:
        raise HTTPException(status_code=400, detail="project_id in path and body must match")
    storage.upsert_project(project)
    await ws_broadcast({"type": "projects_updated"})
    return {"ok": True}

@app.delete("/api/admin/projects/{project_id}")
async def delete_project(project_id: str, ok: bool = Depends(require_admin)):
    deleted = storage.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    await ws_broadcast({"type": "projects_updated"})
    return {"ok": True}

@app.post("/api/clear")
async def clear_history():
    _reset_history()
    storage.log_press(clear_pin if clear_pin is not None else -1, None, "reset_via_api")
    await ws_broadcast({"type": "history_cleared"})
    return {"ok": True}

@app.post("/api/debug/press")
async def simulate_press(body: SimulatedPress):
    if body.kind not in ("down", "up"):
        raise HTTPException(status_code=400, detail="kind must be 'down' or 'up'")
    on_input_event(InputEvent(
        pin=body.pin,
        kind=body.kind,
        source="keyboard",
        timestamp=asyncio.get_event_loop().time(),
    ))
    return {"ok": True}

def _reload_courses_cache() -> None:
    global course_by_pin
    course_by_pin = storage.get_courses_by_pin()

def _compute_insights() -> Dict[str, Any]:
    """Aggregate stats from logs/presses.log: top skills, top projects, funnel counts."""
    log = storage.load_presses_log()
    course_titles = {c.course_id: c.title for c in storage.load_courses()}
    project_titles = {p.project_id: p.title for p in storage.load_projects()}

    skill_press_counts: Dict[str, int] = {}
    project_view_counts: Dict[str, int] = {}
    sessions_confirmed = 0
    sessions_finished = 0
    sessions_abandoned_mid_selection = 0
    project_advances = 0

    in_session = False
    had_selection_before_reset = False

    for entry in log:
        event_type = entry.get("event_type", "")
        course_id = entry.get("course_id")

        if event_type.startswith("button_down_") and course_id:
            skill_press_counts[course_id] = skill_press_counts.get(course_id, 0) + 1
            had_selection_before_reset = True
        elif event_type.startswith("confirm_down_") or event_type.startswith("project_advance_"):
            # The project actually shown is appended as "...:<project_id>" (see on_input_event).
            if ":" in event_type:
                shown_project_id = event_type.rsplit(":", 1)[1]
                project_view_counts[shown_project_id] = project_view_counts.get(shown_project_id, 0) + 1
            if event_type.startswith("confirm_down_"):
                sessions_confirmed += 1
                in_session = True
            else:
                project_advances += 1
        elif event_type.startswith("clear_down_") or event_type == "reset_via_api":
            if in_session:
                sessions_finished += 1
            elif had_selection_before_reset:
                sessions_abandoned_mid_selection += 1
            in_session = False
            had_selection_before_reset = False

    top_skills = sorted(
        (
            {"course_id": cid, "title": course_titles.get(cid, cid), "presses": count}
            for cid, count in skill_press_counts.items()
        ),
        key=lambda x: x["presses"],
        reverse=True,
    )

    top_projects = sorted(
        (
            {"project_id": pid, "title": project_titles.get(pid, pid), "views": count}
            for pid, count in project_view_counts.items()
        ),
        key=lambda x: x["views"],
        reverse=True,
    )

    avg_projects_viewed = None
    if sessions_confirmed:
        avg_projects_viewed = round((project_advances + sessions_confirmed) / sessions_confirmed, 2)

    return {
        "total_button_presses": sum(skill_press_counts.values()),
        "top_skills": top_skills,
        "top_projects": top_projects,
        "sessions_confirmed": sessions_confirmed,
        "sessions_finished": sessions_finished,
        "sessions_abandoned_mid_selection": sessions_abandoned_mid_selection,
        "avg_projects_viewed_per_session": avg_projects_viewed,
        "log_entries_analyzed": len(log),
    }

@app.get("/api/admin/insights")
async def get_insights(ok: bool = Depends(require_admin)):
    return _compute_insights()

@app.get("/api/admin/press-log")
async def get_press_log(ok: bool = Depends(require_admin)):
    return storage.load_presses_log()

@app.delete("/api/admin/press-log")
async def clear_press_log(ok: bool = Depends(require_admin)):
    storage.clear_presses_log()
    return {"ok": True}

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

@app.get("/api/admin/serial-ports")
async def list_serial_ports(ok: bool = Depends(require_admin)):
    try:
        import serial.tools.list_ports as list_ports
        return [
            {"device": p.device, "description": p.description}
            for p in list_ports.comports()
        ]
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to list serial ports: {str(e)}"}
        )

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
            arduino_config=arduino_config,
            on_raw_event=on_raw_input_event
        )

        await input_manager.start()

        # Persist so this choice survives a server restart.
        storage.save_backend_override(backend.value)

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