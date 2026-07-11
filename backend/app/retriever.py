import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.config import settings
from app.models import Document
from app.document_processor import get_chroma_client

logger = logging.getLogger(__name__)

embedding_model = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-001",
    google_api_key=settings.GEMINI_API_KEY,
)


async def retrieve_chunks(query: str, user_id: str, db: AsyncSession, k: int = 5) -> list[str]:
    result = await db.execute(
        select(Document.id).where(Document.user_id == user_id)
    )
    document_ids = [str(row) for row in result.scalars().all()]

    if not document_ids:
        return []

    try:
        query_embedding = embedding_model.embed_query(query)
    except Exception as e:
        logger.error(f"Failed to embed query: {e}")
        return []

    client = get_chroma_client()
    all_chunks = []

    for document_id in document_ids:
        try:
            collection = client.get_collection(name=f"doc_{document_id}")
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                include=["documents"],
            )
            docs = results.get("documents", [[]])[0]
            all_chunks.extend(docs)
        except Exception as e:
            logger.warning(f"Failed to retrieve from collection doc_{document_id}: {e}")
            continue

    return all_chunks