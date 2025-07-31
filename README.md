# Android Screenshot Annotation Tool

A comprehensive tool for collecting and annotating Android UI screenshots with a PyQt5 GUI and FastAPI upload server.

## Features

### 📱 Screenshot Capture & Annotation
* Capture live screenshots from connected Android devices via **ADB**
* Create **cube annotations** by clicking four corner points on the image
* Add **center point annotations** with automatic calculation and manual adjustment
* Zoom in/out with mouse wheel or keyboard shortcuts (Ctrl +/-)
* Undo/redo functionality for point placement
* Drag points to adjust positions after placement
* Real-time coordinate display with normalized values (0.0-1.0)

### 💾 Data Management
* Automatic timestamped screenshot saving to `~/Desktop/Images/`
* Individual annotation files (`annotations.json`, `Points_Positions.json`)
* Structured cumulative data files for batch processing
* Incremental updates to preserve annotation history

### 🌐 Server Upload Integration
* Built-in FastAPI server for receiving annotation data
* Automatic upload after completing both cube and center point annotations
* RESTful API with health checks and documentation
* Timestamp-based file organization on server

### 🎯 Use Cases
Perfect for computer vision research, mobile UI analysis, dataset creation, and automated testing data collection.

---

## Prerequisites

1. **Python** ≥ 3.10 
2. **ADB** (Android platform-tools) available in your `$PATH` with USB-debugging enabled device or running emulator
3. **uv** – the ultra-fast Python package manager by Astral. Install globally:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Quick Start

Clone the repository and navigate to the project directory:

```bash
git clone https://github.com/johnmalek312/android_ui_collector data_collector
cd data_collector
```

### 1. Set Up Environment

```bash
uv init        # creates .venv and pyproject.toml if missing
```

### 2. Activate Virtual Environment

**Linux/macOS:**
```bash
source .venv/bin/activate
```

**Windows:**
```bash
.venv\Scripts\activate
```

### 3. Install Dependencies

```bash
uv sync        # reads pyproject.toml + uv.lock and installs everything
```

**Core Dependencies:**
* `PyQt5` – GUI framework for the annotation interface
* `adbutils` – Android Debug Bridge wrapper for device communication
* `requests` – HTTP client for server uploads
* `fastapi` – Modern web framework for the upload server
* `uvicorn` – ASGI server for running FastAPI
* `python-multipart` – File upload support for FastAPI

### 4. Start the Upload Server (Optional)

In a separate terminal, start the FastAPI server to receive uploads:

```bash
python start_server.py
```

The server will be available at `http://localhost:8000` with:
- API documentation at `/docs`
- Health check at `/health`

### 5. Run the Annotation Tool

```bash
python gui.py
```

## 🎯 Usage Workflow

### Creating Cube Annotations

1. **Take Screenshot**: Click "Take Screenshot" to capture the current Android screen
2. **Place Corner Points**: Click four times to define the corners of a rectangular region
   - Points are connected with lines to show the shape
   - Use Ctrl+Z/Ctrl+Y for undo/redo
   - Drag points to adjust positions
3. **Add Description**: Enter a descriptive label for the annotated region
4. **Save**: Click "Save" to store the cube annotation

### New Streamlined Workflow

1. **Take Screenshot** → Image saved locally
2. **Set 4 points** → Cube annotation created  
3. **Add description** → Cube annotation saved to `cube_annotations.json`
4. **Center point appears** → Automatically calculated
5. **Move center point** → Click anywhere or edit coordinates manually
6. **Add description** → Center point saved to `center_points.json`
7. **Upload to server** → Both updated JSON files + screenshot sent automatically
8. **Reset app state** → Ready for next annotation

### Key Benefits

- **Only 2 JSON files** maintained locally (no file proliferation)
- **Cumulative updates** preserve all annotation history
- **Automatic upload** after each complete annotation pair
- **Server receives complete datasets** for easy processing

### Navigation & Controls

- **Zoom**: Use Ctrl +/- or zoom buttons
- **Undo/Redo**: Ctrl+Z / Ctrl+Y or toolbar buttons
- **Cancel**: Discard current annotation and start over

---

## 📁 Data Output Format

The tool maintains only 2 cumulative JSON files that are continuously updated:

### Cumulative Annotation Files

**`cube_annotations.json`** - All cube annotations in chronological order:
```json
[
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
  },
  {
    "screenshot": "screenshot_1689850095.png",
    "timestamp": 1689850095,
    "points": [...],
    "description": "Cancel button on dialog"
  }
]
```

**`center_points.json`** - All center point annotations in chronological order:
```json
[
  {
    "screenshot": "screenshot_1689850092.png",
    "timestamp": 1689850092,
    "center_point": {"x": 0.456, "y": 0.622},
    "description": "Center of submit button"
  },
  {
    "screenshot": "screenshot_1689850095.png", 
    "timestamp": 1689850095,
    "center_point": {"x": 0.345, "y": 0.789},
    "description": "Center of cancel button"
  }
]
```

### Server Storage

After each complete annotation (cube + center point), files are uploaded with timestamp prefixes:
```
uploads/
├── 20240801_143022_123_screenshot.png
├── 20240801_143022_123_annotations.json      # Complete cube annotations
├── 20240801_143022_123_center_points.json    # Complete center points
├── 20240801_143025_456_screenshot.png        # Next annotation
├── 20240801_143025_456_annotations.json      # Updated with new data
├── 20240801_143025_456_center_points.json    # Updated with new data
└── ...
```

**Key Benefits:**
- Only 2 JSON files maintained locally (no individual files per annotation)
- Each server upload contains the complete updated datasets
- Cumulative structure preserves all annotation history
- Easy to process for batch analysis or machine learning

**Coordinates are normalized** (0.0 - 1.0) relative to the image dimensions.

---

## 🔧 Server API

The FastAPI server provides several endpoints:

- **`GET /`** - Welcome message and server status
- **`GET /health`** - Health check endpoint
- **`POST /upload/`** - Upload screenshot and annotation files
- **`GET /docs`** - Interactive API documentation (Swagger UI)

### Upload Endpoint

Accepts three files:
- `image`: Screenshot image (PNG, JPG, JPEG)
- `annotations`: Structured annotations JSON file
- `center_points`: Structured center points JSON file

Returns timestamped file paths and upload confirmation.

---

## 🛠️ Troubleshooting

### Common Issues

* **No devices found**: 
  - Verify `adb devices` shows your phone/emulator
  - Ensure USB debugging is enabled
  - Try restarting ADB: `adb kill-server && adb start-server`

* **Permission errors**: 
  - The tool saves to `~/Desktop/Images/`
  - Ensure this directory exists and is writable
  - Check file permissions if on Linux/macOS

* **Black screenshots**: 
  - Some devices block screen capture with DRM-protected content
  - Try different apps or disable DRM protection in developer options

* **Server connection failed**:
  - Ensure the FastAPI server is running on `http://localhost:8000`
  - Check firewall settings
  - Verify server dependencies are installed

* **GUI issues**:
  - Ensure PyQt5 is properly installed
  - Try running with `python -m gui` if direct execution fails
  - Check display settings if annotations appear misaligned

### Performance Tips

- Use zoom for precise point placement on high-resolution screens
- Save annotations frequently to avoid data loss
- Monitor the `uploads/` directory size if running the server continuously

---

## 🗂️ Project Structure

```
data_collector/
├── gui.py                          # Main annotation interface
├── adb.py                          # Android device communication
├── server.py                       # FastAPI upload server
├── start_server.py                 # Server startup script
├── pyproject.toml                  # Project dependencies
├── server_requirements.txt         # Server-specific requirements
├── README.md                       # This file
├── SERVER_README.md                # Detailed server documentation
└── uploads/                        # Server upload directory (created at runtime)
```

---

## 🚀 Advanced Usage

### Batch Processing

The structured JSON files are designed for batch processing:

```python
import json

# Load all annotations
with open("structured_annotations.json", "r") as f:
    all_annotations = json.load(f)

# Process annotations
for annotation in all_annotations:
    # Your processing logic here
    pass
```

### Custom Server Configuration

Modify server settings in `start_server.py`:

```python
uvicorn.run(
    app, 
    host="0.0.0.0",  # Change host
    port=8000,       # Change port
    reload=True
)
```

### Integration with Other Tools

The normalized coordinate format makes it easy to integrate with:
- Computer vision frameworks (OpenCV, PIL)
- Machine learning pipelines
- Automated testing tools
- Data analysis workflows

---

## 📦 Installation Verification

After installation, verify everything works:

```bash
# Check if the annotation tool launches
python gui.py

# Check if the server starts (in another terminal)
python start_server.py

# Or use the entry points (after pip install)
android-annotator
annotation-server
```

## 🔄 Development Setup

For development with additional tools:

```bash
# Install with development dependencies
uv sync --extra dev

# Install only server dependencies
uv sync --extra server

# Run formatting and linting
black .
flake8 .
mypy .
```

---

## License

[MIT](LICENSE) – free to use, modify, and distribute.
