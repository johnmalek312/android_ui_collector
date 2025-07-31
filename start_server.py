#!/usr/bin/env python3
"""
Start script for the Screenshot Annotation Upload Server
"""
import uvicorn
from server import app

def main():
    """Main entry point for the annotation server."""
    print("🚀 Starting Screenshot Annotation Upload Server...")
    print("📍 Server will be available at: http://localhost:8000")
    print("📁 Uploads will be saved in: ./uploads/")
    print("📖 API documentation at: http://localhost:8000/docs")
    print("🔍 Health check at: http://localhost:8000/health")
    print("\nPress Ctrl+C to stop the server\n")
    
    uvicorn.run(
        "server:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True,  # Auto-reload on code changes
        log_level="info"
    )

if __name__ == "__main__":
    main() 
  