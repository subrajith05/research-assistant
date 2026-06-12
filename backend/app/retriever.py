from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models import Document

embeddings = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-001",
    api_key=settings.GEMINI_API_KEY
)

async def retrieve_chunks(query: str, user_id: str, db: AsyncSession, k: int = 5) -> list[str]:
    result = await db.execute(select(Document.id).where(Document.user_id == user_id))
    document_ids = [str(row) for row in result.scalars().all()]

    if not document_ids:
        return []
    
    all_chunks = []

    for document_id in document_ids:
        vector_store = Chroma(
            collection_name=document_id,
            embedding_function=embeddings,
            persist_directory=settings.CHROMA_PERSIST_DIR
        )
        retriever = vector_store.as_retriever(search_kwargs={"k":k})
        docs = await retriever.ainvoke(query)
        all_chunks.extend([doc.page_content for doc in docs])

    return all_chunks