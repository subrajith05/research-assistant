import uuid
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
 
from app.database import get_db
from app.models import User, Document
from app.utils import get_current_user
from app.schemas import UploadResponse
from app.document_processor import process_document
 
router = APIRouter(prefix="/documents", tags=["documents"])

#Endpoint to upload the document and add it to database
@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pdf files are accepteed"
        )
    
    document = Document(
        id = uuid.uuid4(),
        user_id = current_user.id,
        file_name = file.filename
    )

    db.add(document)
    await db.commit()
    await db.refresh(document)

    contents = await file.read()
    chunk_count = await process_document(str(document.id), contents, file.filename)

    return UploadResponse(
        document_id=str(document.id),
        file_name=document.file_name,
        chunk_count=chunk_count,
        message="Document uploaded successfully."
    )