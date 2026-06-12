import os
import tempfile

from langchain_community.document_loaders import PyPDFLoader
from langchain_experimental.text_splitter import SemanticChunker
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma

from app.config import settings

#Embedding model
embeddings = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-001",
    api_key=settings.GEMINI_API_KEY
)

#Fetching the vector_store
def get_vector_store(document_id: str) -> Chroma:
    return Chroma(
        collection_name=document_id,
        embedding_function=embeddings,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )

#Function to fetch text from the document, convert to embedding and store it in Chroma
async def process_document(document_id: str, file_bytes: bytes, file_name: str) -> int:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        loader = PyPDFLoader(tmp_path)
        pages = loader.load()
    finally:
        os.unlink(tmp_path)

    splitter = SemanticChunker(
        embeddings=embeddings,
        breakpoint_threshold_type="percentile"
    )

    chunks = splitter.split_documents(pages)
    
    for chunk in chunks:
        chunk.metadata["document_id"] = document_id
        chunk.metadata["file_name"] = file_name
    
    vector_store = get_vector_store(document_id)
    vector_store.add_documents(chunks)

    return len(chunks)