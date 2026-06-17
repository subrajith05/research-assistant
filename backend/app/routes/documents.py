import uuid
import logging
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
 
from app.database import get_db
from app.models import User, Document
from app.utils import get_current_user
from app.schemas import UploadResponse, DocumentItem, DeleteResponse
from app.document_processor import process_document, DocumentProcessingError, get_vector_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  #20MB

#Endpoint to upload the document and add it to database
@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepteed"
        )
    
    contents = await file.read()

    if not contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty"
        )
    
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum file size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB."
        )
    
    document = Document(
        id = uuid.uuid4(),
        user_id = current_user.id,
        file_name = file.filename
    )
    try:
        db.add(document)
        await db.commit()
        await db.refresh(document)
    except Exception as e:
        logger.error(f"Failed to save document metadata : {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save document. Please try again."
        )
    
    try:
        chunk_count = await process_document(str(document.id), contents, file.filename)
    except DocumentProcessingError as e:
        await db.delete(document)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error processing document '{file.filename}' : {e}")
        await db.delete(document)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing your document. Please try again.",
        )

    return UploadResponse(
        document_id=str(document.id),
        file_name=document.file_name,
        chunk_count=chunk_count,
        message="Document uploaded successfully."
    )

#Endpoint to list all documents uploaded by the current user
@router.get("/", response_model=list[DocumentItem])
async def get_documents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Document).where(Document.user_id == current_user.id).order_by(Document.uploaded_at.desc()))
    documents = result.scalars().all()
    return documents

#Endpoint to delete a document from both postgres and chromaDB
@router.delete("/{document_id}", response_model=DeleteResponse)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Document)
        .where(Document.user_id == current_user.id, Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found."
        )
    
    try:
        vector_store = get_vector_store(str(document_id))
        vector_store.delete_collection()

    except Exception as e:
        logger.warning(f"Failed to delete ChromaDB collection for document {document_id}: {e}")
    

    try:
        await db.delete(document)
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to delete document metadata for {document_id}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document. Please try again.",
        )
 
    return DeleteResponse(message="Document deleted successfully.")