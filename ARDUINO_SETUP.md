# Arduino Setup

This app can read physical button presses from an Arduino over USB serial
instead of (or in addition to) Raspberry Pi GPIO. This is handled by
`app/arduino_manager.py`.

## Enabling the Arduino backend

Set the input backend before starting the server:

```
INPUT_BACKEND=arduino uvicorn app.main:app
```

Serial port and baud rate come from `data/arduino_config.json`
(editable via `GET`/`POST /api/admin/arduino-config`, HTTP Basic auth
required):

```json
{
  "serial_port": "/dev/ttyACM0",
  "baud_rate": 9600,
  "course_inputs": [0, 1, 2, 3, 4, 5, 6, 7, 8],
  "clear_input": 9,
  "input_count": 10
}
```

`course_inputs` are Arduino-side input numbers (0-9), mapped in order to
the sorted GPIO pins in `data/gpio_map.json`'s `course_pins` list.
`clear_input` maps to `clear_pin`. Whatever physical pin/button the
Arduino sketch calls "input 0" becomes whichever course pin sorts first,
and so on.

## Serial protocol

The Arduino sketch should write ASCII lines (newline-terminated) to serial
in one of two formats:

**Per-button events** — sent whenever a button changes state:

```
BTN:<input_id>:DOWN
BTN:<input_id>:UP
```

`<input_id>` is `0`-`9`. Example: pressing input 3 down, then releasing it:

```
BTN:3:DOWN
BTN:3:UP
```

**Full state (bitmask)** — an alternative that sends the state of all 10
inputs at once, `1` = pressed, `0` = released, left-to-right = input 0-9:

```
STATE:0001000000
```

Only inputs whose bit actually *changed* since the last `STATE:` line
generate a down/up event — sending the same `STATE:` line twice is a
no-op.

You can mix both formats; `arduino_manager.py` handles either line by
line. Malformed lines are logged and ignored, not fatal.

## Wiring

Buttons should be wired as momentary switches to digital input pins on
the Arduino, debounced in the sketch (or in hardware) before being
reported over serial — this app does not currently debounce Arduino
input on the Python side (unlike the GPIO backend, which debounces via
`gpiozero`'s `bounce_time`).

## Testing without hardware

Use `INPUT_BACKEND=simulation` and the keyboard-simulated presses
(`POST /api/debug/press`, wired to number keys 1-9 and 0 in
`static/js/app.js`) to exercise the full app without any Arduino or
Raspberry Pi attached.
