from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import os
import shutil
from datetime import datetime
from pathlib import Path
import uvicorn

app = FastAPI(title="Screenshot Annotation Upload Server", version="1.0.0")

# Create uploads directory if it doesn't exist
UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)

@app.get("/")
async def root():
    """Root endpoint to check if server is running."""
    return {"message": "Screenshot Annotation Upload Server is running"}

@app.post("/upload/")
async def upload_files(
    image: UploadFile = File(...), 
    annotations: UploadFile = File(...),
    center_points: UploadFile = File(...)
):
    """
    Upload screenshot image and annotation JSON files.
    
    Args:
        image: Screenshot image file
        annotations: Structured annotations JSON file
        center_points: Structured center points JSON file
    
    Returns:
        JSON response with upload status and file paths
    """
    try:
        # Generate timestamp for unique filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Include milliseconds
        
        # Validate file types
        if not image.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            raise HTTPException(status_code=400, detail="Image file must be PNG, JPG, or JPEG")
        
        if not annotations.filename.lower().endswith('.json'):
            raise HTTPException(status_code=400, detail="Annotations file must be JSON")
            
        if not center_points.filename.lower().endswith('.json'):
            raise HTTPException(status_code=400, detail="Center points file must be JSON")
        
        # Create unique filenames with timestamp
        image_ext = Path(image.filename).suffix
        annotations_ext = Path(annotations.filename).suffix
        center_points_ext = Path(center_points.filename).suffix
        
        image_filename = f"{timestamp}_screenshot{image_ext}"
        annotations_filename = f"{timestamp}_annotations{annotations_ext}"
        center_points_filename = f"{timestamp}_center_points{center_points_ext}"
        
        # Save image file
        image_path = UPLOADS_DIR / image_filename
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        
        # Save annotations JSON file
        annotations_path = UPLOADS_DIR / annotations_filename
        with open(annotations_path, "wb") as buffer:
            shutil.copyfileobj(annotations.file, buffer)
            
        # Save center points JSON file
        center_points_path = UPLOADS_DIR / center_points_filename
        with open(center_points_path, "wb") as buffer:
            shutil.copyfileobj(center_points.file, buffer)
        
        # Return success response
        return JSONResponse(
            status_code=200,
            content={
                "message": "Files uploaded successfully",
                "timestamp": timestamp,
                "files": {
                    "image": str(image_path),
                    "annotations": str(annotations_path),
                    "center_points": str(center_points_path)
                }
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "uploads_dir": str(UPLOADS_DIR)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 