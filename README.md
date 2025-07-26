# Android Screenshot Annotation Tool

Collect and label Android UI screenshots with a tiny PyQt5 GUI.

This utility lets you:

* capture a live screenshot from a connected Android device (via **ADB**)  
* draw a **square** by clicking four points on the image  
* add a free-form **text description**  
* automatically save the screenshot together with the annotated points + description to `~/Desktop/Images/annotations.json`

It is intended as a quick data-collection helper for computer-vision or mobile-UI research projects.

---

## Prerequisites

1. **Python** ≥ 3.10 
2. **ADB** (Android platform-tools) available in your `$PATH` and a device with USB-debugging enabled or an emulator running.  
3. **uv** – the ultra-fast Python package manager by Astral. Install once globally:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Quick start

Clone the repository and move into it:

```bash
git clone https://github.com/johnmalek312/android_ui_collector data_collector
cd data_collector
```

### 1. Create a virtual environment

```bash
uv init        # creates .venv and pyproject.toml if missing
```

### 2. Activate the environment (Linux)

```bash
source .venv/bin/activate
```

> On macOS it is the same path. On Windows use `.venv\Scripts\activate`.

### 3. Install dependencies

```bash
uv sync        # reads pyproject.toml + uv.lock and installs everything
```

Dependencies are cached and compiled by **uv**. Current requirements (see `pyproject.toml`):

* `PyQt5` – GUI toolkit
* `adbutils` – lightweight ADB wrapper used in `adb.py`

### 4. Run the tool

```bash
python gui.py
```

The main window will open. Press **“Take Screenshot”** to grab the current screen of the first connected Android device. Then:

1. Click **four** times to place the square corners (dots + connecting lines are shown).
2. Fill in a textual description.
3. Click **Save** – the image is written to `~/Desktop/Images/` with a timestamped filename (e.g. `screenshot_1689850092.png`) and the annotation appended to `annotations.json` in that same folder.

Undo/redo and zoom shortcuts are provided in the toolbar.

---

## Data output format

Each entry in `annotations.json` looks like:

```json
{
  "screenshot": "screenshot_1689850092.png",
  "timestamp": 1689850092,
  "points": [
    {"x": 0.123, "y": 0.456},
    {"x": 0.789, "y": 0.456},
    {"x": 0.789, "y": 0.789},
    {"x": 0.123, "y": 0.789}
  ],
  "description": "Submit button on login screen"
}
```

Coordinates are **normalised** (0 – 1) relative to the displayed image.

---

## Troubleshooting

* **No devices found** – verify `adb devices` shows your phone/emulator and that USB-debugging is enabled.
* **Permission errors writing images** – the tool saves to `~/Desktop/Images/`. Make sure this directory exists and is writable.
* **Screenshots appear black** – some devices block screen-capture when DRM-protected content is shown.

---

## License

[MIT](LICENSE) – free to use, modify, and distribute.
