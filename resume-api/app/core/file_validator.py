import os 
import uuid
import io
from fastapi import UploadFile, HTTPException
from app.core.s3_client import USE_S3, upload_file_to_s3

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"application/pdf"}
ALLOWED_EXTENSIONS = {".pdf"}

def validate_resume_file(file: UploadFile) -> None:
    if not file:
        raise HTTPException(
            status_code=400,
            detail="No file provided"
        )

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="File has no name"
        )

    _, extension = os.path.splitext(file.filename.lower())
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{extension}'. Only PDF files are allowed."
        )

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid content type '{file.content_type}'. Must be application/pdf."
        )
    
async def read_and_validate_size(file: UploadFile) -> bytes:
    content = await file.read()

    if len(content) == 0:
        raise HTTPException(
            status_code=400,
            detail="File is empty"
        )

    if len(content) > MAX_FILE_SIZE_BYTES:
        size_mb = len(content) / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({size_mb:.1f}MB). Maximum size is 5MB."
        )
    return content

def generate_safe_filename(original_filename: str) -> str:
    _, extension = os.path.splitext(original_filename.lower())
    return f"{uuid.uuid4()}{extension}"

def get_upload_path(stored_filename: str, upload_dir: str = "uploads") -> str:
    os.makedirs(upload_dir, exist_ok=True)
    return os.path.join(upload_dir, stored_filename)

def save_resume_file(content: bytes, stored_filename: str) -> str:
    if USE_S3:
        key = f"resumes/{stored_filename}"
        upload_file_to_s3(content, key)
        return key
    else:
        path = get_upload_path(stored_filename)
        with open(path, "wb") as f:
            f.write(content)
        return path