# Screenshot Annotation Upload Server

This FastAPI server receives screenshot images and structured annotation JSON files from the Android Screenshot Annotation Tool.

## Setup Instructions

### 1. Install Server Dependencies

```bash
pip install -r server_requirements.txt
```

### 2. Start the Server

```bash
python start_server.py
```

Or directly:
```bash
python server.py
```

The server will start on `http://localhost:8000`

### 3. Verify Server is Running

- Visit `http://localhost:8000` - Should show welcome message
- Visit `http://localhost:8000/health` - Should show health status
- Visit `http://localhost:8000/docs` - Interactive API documentation

### 4. Test Upload Endpoint

The server exposes a POST endpoint at `/upload/` that accepts:
- `image`: Screenshot image file (PNG, JPG, JPEG)
- `annotations`: Structured annotations JSON file
- `center_points`: Structured center points JSON file

## Integration with Annotation Tool

The annotation tool (`gui.py`) now automatically updates structured JSON files and uploads them to the server after completing both cube and center point annotations.

### New Workflow

1. **Take Screenshot** → Image saved locally
2. **Set 4 points** → Cube annotation created
3. **Add description** → Cube annotation saved to `annotations.json`
4. **Update structured file** → `structured_annotations.json` updated incrementally
5. **Center point appears** → Automatically calculated
6. **Move center point** → Click anywhere or edit coordinates
7. **Add description** → Center point saved to `Points_Positions.json`
8. **Update structured file** → `structured_center_points.json` updated incrementally
9. **Upload to server** → All files sent to server automatically
10. **Reset app state** → Ready for next annotation

### File Structure

**Local Files (Desktop/Images/):**
```
cube_annotations.json          # Cumulative cube annotations (updated incrementally)
center_points.json             # Cumulative center point annotations (updated incrementally)
screenshot_1234567890.png      # Screenshot images
```

**Server Files (uploads/):**
```
20231201_143022_123_screenshot.png
20231201_143022_123_annotations.json
20231201_143022_123_center_points.json
20231201_143025_456_screenshot.png
20231201_143025_456_annotations.json
20231201_143025_456_center_points.json
```

### Structured JSON Files

The app now maintains only two JSON files that are updated incrementally:

1. **`cube_annotations.json`** - Contains all cube annotations in chronological order
2. **`center_points.json`** - Contains all center point annotations in chronological order

These files preserve all previously stored data while adding new entries incrementally.

### Upload Process

After completing both cube and center point annotations:
1. Both JSON files are updated with new data
2. Screenshot image and both JSON files are uploaded to server
3. Server saves files with timestamp prefix
4. Console shows upload status
5. App resets for next annotation

### Error Handling

The upload function handles various errors:
- Connection errors (server not running)
- Timeout errors (server too slow)
- File not found errors
- Server errors (invalid files, etc.)

## API Endpoints

- `GET /` - Welcome message
- `GET /health` - Health check
- `POST /upload/` - Upload screenshot and annotation files
- `GET /docs` - Interactive API documentation (Swagger UI)

## Configuration

You can modify the server URL in your annotation tool by changing the `server_url` parameter in the `upload_to_server` function call. 