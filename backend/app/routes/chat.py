import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import User, ChatSession, ChatLog
from app.utils import get_current_user
from app.schemas import ChatRequest, ChatResponse, ChatHistoryItem
from app.pipeline import run_pipeline
from app.memory import add_exchange

router = APIRouter(prefix="/chat", tags=["chat"])

#Endpoint for sending the user query to the LLM
@router.post("/", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(ChatSession).where(ChatSession.id == request.session_id))
    session = result.scalar_one_or_none()

    if not session:
        session = ChatSession(
            id = request.session_id,
            user_id = current_user.id
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)

    answer = await run_pipeline(
        query=request.query,
        user_id=str(current_user.id),
        session_id=str(session.id),
        db=db
    )

    log = ChatLog(
        id = uuid.uuid4(),
        session_id = session.id,
        question = request.query,
        answer = answer
    )

    db.add(log)
    await db.commit()
    await db.refresh(log)

    await add_exchange(str(session.id), request.query, answer)

    return ChatResponse(session_id=str(session.id), answer=answer)

#Endpoint to fetch the chat history
@router.get("/history/{session_id}", response_model=list[ChatHistoryItem])
async def get_history(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(ChatLog).where(ChatLog.session_id == session_id).order_by(ChatLog.created_at))
    logs = result.scalars().all()

    return logs