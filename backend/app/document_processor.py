import os
import uuid
import tempfile
import logging

import chromadb
from langchain_community.document_loaders import PyPDFLoader
from langchain_experimental.text_splitter import SemanticChunker
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)


class DocumentProcessingError(Exception):
    """Raised when a document cannot be processed into ChromaDB."""
    pass


def get_chroma_client() -> chromadb.CloudClient:
    return chromadb.CloudClient(
        tenant=settings.CHROMA_TENANT,
        database=settings.CHROMA_DATABASE,
        api_key=settings.CHROMA_API_KEY,
    )


embedding_model = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-001",
    google_api_key=settings.GEMINI_API_KEY,
)


def get_collection(document_id: str):
    client = get_chroma_client()
    return client.get_or_create_collection(name=f"doc_{document_id}")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _add_documents_with_retry(collection, ids, embeddings, documents, metadatas) -> None:
    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )


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
            logger.error(f"Failed to load PDF '{file_name}': {e}")
            raise DocumentProcessingError(
                "Could not read the PDF. It may be corrupted or password-protected."
            ) from e

        if not pages:
            raise DocumentProcessingError("No pages found in the PDF.")

        non_empty_pages = [p for p in pages if p.page_content and p.page_content.strip()]
        if not non_empty_pages:
            raise DocumentProcessingError(
                "No extractable text found in the PDF. It may be a scanned/image-only document."
            )

        try:
            splitter = SemanticChunker(
                embeddings=embedding_model,
                breakpoint_threshold_type="percentile"
            )
            chunks = splitter.split_documents(non_empty_pages)
        except Exception as e:
            logger.error(f"Semantic chunking failed for '{file_name}': {e}")
            raise DocumentProcessingError("Failed to split document into chunks.") from e

        if not chunks:
            raise DocumentProcessingError("Document produced no usable chunks.")

        texts = [chunk.page_content for chunk in chunks]

        try:
            embeddings = embedding_model.embed_documents(texts)
        except Exception as e:
            logger.error(f"Embedding generation failed for '{file_name}': {e}")
            raise DocumentProcessingError("Failed to generate embeddings. Please try again.") from e

        ids = [str(uuid.uuid4()) for _ in chunks]
        metadatas = [
            {"document_id": document_id, "file_name": file_name, **chunk.metadata}
            for chunk in chunks
        ]

        try:
            collection = get_collection(document_id)
            _add_documents_with_retry(collection, ids, embeddings, texts, metadatas)
        except Exception as e:
            logger.error(f"Failed to store embeddings for '{file_name}': {e}")
            raise DocumentProcessingError("Failed to store embeddings. Please try again.") from e

        return len(chunks)

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def delete_document_collection(document_id: str) -> None:
    try:
        client = get_chroma_client()
        client.delete_collection(name=f"doc_{document_id}")
    except Exception as e:
        logger.warning(f"Failed to delete ChromaDB collection for document {document_id}: {e}")