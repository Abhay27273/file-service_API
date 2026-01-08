import os
import shutil
import uuid
from datetime import datetime
from typing import List

# Import HTTPException to stop bad requests
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="Deep File Service API")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
file_db = []

# --- NEW: Magic Bytes Dictionary ---
# We define what the FIRST few bytes of valid files look like.
SUPPORTED_FILE_TYPES = {
    'image/png': b'\x89PNG\r\n\x1a\n',
    'image/jpeg': b'\xff\xd8\xff',
    'application/pdf': b'%PDF-'
}

class FileMetadata(BaseModel):
    id: str
    filename: str
    size: int
    content_type: str
    created_at: datetime

@app.post("/files/upload", response_model=FileMetadata)
async def upload_file(file: UploadFile = File(...)):
    """
    Uploads a file with Magic Byte Validation.
    """
    
    # 1. READ HEADER (The Deep Validation)
    # Read the first 10 bytes to check the signature
    header = await file.read(10)
    
    # Check if the header matches any of our supported types
    file_type = None
    for content_type, magic_bytes in SUPPORTED_FILE_TYPES.items():
        # We startswith because JPEG headers can vary slightly after the first 3 bytes
        if header.startswith(magic_bytes):
            file_type = content_type
            break
            
    if not file_type:
        # Rejection! The file is lying or not supported.
        raise HTTPException(
            status_code=400, 
            detail="Invalid file format. Only PNG, JPEG, and PDF are allowed."
        )

    # 2. RESET CURSOR (Crucial Step!)
    # We read 10 bytes, so the "cursor" is now at byte 10. 
    # If we save now, the file will be missing its header and be corrupt.
    # We must rewind to the start.
    await file.seek(0) 

    # --- Standard Saving Logic (Same as before) ---
    file_id = str(uuid.uuid4())
    # Force the extension based on the DETECTED type, not the user's extension
    extension = ".png" if file_type == "image/png" else ".jpg" if file_type == "image/jpeg" else ".pdf"
    
    secure_filename = f"{file_id}{extension}"
    file_path = os.path.join(UPLOAD_DIR, secure_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_size = os.path.getsize(file_path)

    metadata = {
        "id": file_id,
        "filename": file.filename, # We keep original name for display
        "path": file_path,
        "size": file_size,
        "content_type": file_type, # We trust our detection, not the user
        "created_at": datetime.now()
    }
    file_db.append(metadata)

    return metadata

# --- GET and DELETE endpoints (same as before) ---

@app.get("/files", response_model=List[FileMetadata])
def list_files():
    """List all uploaded files."""
    return file_db

@app.get("/files/{file_id}/download")
def download_file(file_id: str):
    """
    Stream the file back to the client.
    """
    # Find metadata
    file_record = next((f for f in file_db if f["id"] == file_id), None)
    
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Return file stream
    return FileResponse(
        path=file_record["path"],
        filename=file_record["filename"],
        media_type=file_record["content_type"]
    )

@app.delete("/files/{file_id}")
def delete_file(file_id: str):
    """Delete file from Disk and DB."""
    # Find metadata
    file_record = next((f for f in file_db if f["id"] == file_id), None)
    
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    # 1. Delete from Disk
    if os.path.exists(file_record["path"]):
        os.remove(file_record["path"])
    
    # 2. Delete from DB
    file_db.remove(file_record)
    
    return {"message": "File deleted successfully"}