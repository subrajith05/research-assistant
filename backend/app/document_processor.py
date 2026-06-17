import os
import tempfile
import logging

from langchain_community.document_loaders import PyPDFLoader
from langchain_experimental.text_splitter import SemanticChunker
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma
from tenacity import retry, stop_after_attempt, wait_exponential


from app.config import settings

logger = logging.getLogger(__name__)

#Embedding model
embeddings = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-001",
    api_key=settings.GEMINI_API_KEY
)

class DocumentProcessingError(Exception):
    """Raised when a document cannot be processed into ChromaDB"""
    pass

#Fetching the vector_store
def get_vector_store(document_id: str) -> Chroma:
    return Chroma(
        collection_name=document_id,
        embedding_function=embeddings,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _add_documents_with_retry(vector_store: Chroma, chunks: list) -> None:
    vector_store.add_documents(chunks)

#Function to fetch text from the document, convert to embedding and store it in Chroma
async def process_document(document_id: str, file_bytes: bytes, file_name: str) -> int:
    if not file_bytes:
        raise DocumentProcessingError("Uploaded file is empty.")
    
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            loader = PyPDFLoader(tmp_path)
            pages = loader.load()
        except Exception as e:
            logger.error(f"Failed to load PDF {file_name} : {e}")
            raise DocumentProcessingError(
                "Could not read PDF. It may be corrupted or password-protected"
            ) from e
        
        if not pages:
            raise DocumentProcessingError("No pages found in PDF.")
        non_empty_pages = [p for p in pages if p.page_content and p.page_content.strip()]
        if not non_empty_pages:
            raise DocumentProcessingError(
                "No extractable text found in the PDF. It may be a scanned/image-only document."
            )
        
        try:
            splitter = SemanticChunker(
                embeddings=embeddings,
                breakpoint_threshold_type="percentile"
            )
            chunks = splitter.split_documents(non_empty_pages)
        except Exception as e:
            logger.error(f"Semantic chunking failed for '{file_name}': {e}")
            raise DocumentProcessingError("Failed to split document into chunks.") from e
 
        if not chunks:
            raise DocumentProcessingError("Document produced no usable chunks.")
 
        for chunk in chunks:
            chunk.metadata["document_id"] = document_id
            chunk.metadata["file_name"] = file_name
 
        try:
            vector_store = get_vector_store(document_id)
            _add_documents_with_retry(vector_store, chunks)
        except Exception as e:
            logger.error(f"Failed to store embeddings for '{file_name}': {e}")
            raise DocumentProcessingError(
                "Failed to generate embeddings or store them. Please try again."
            ) from e
 
        return len(chunks)
    
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)