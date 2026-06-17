import json
import redis.asyncio as redis

from app.config import settings

redis_client = redis.from_url(url=settings.REDIS_URL, decode_responses=True)

MAX_HISTORY = 5     #Max number of exchanges to store per session
TTL_SECONDS = 60*60*24  #Expiration set to 24hrs

def _key(session_id: str) -> str:
    return f"chat_memory:{session_id}"

async def get_history(session_id: str) -> list[dict]:
    raw = await redis_client.get(_key(session_id))
    if not raw:
        return []
    return json.loads(raw)

async def add_exchange(session_id: str, question: str, answer: str) -> None:
    history = await get_history(session_id)
    history.append({"question": question, "answer": answer})
    history = history[-MAX_HISTORY:]

    await redis_client.set(
        _key(session_id),
        json.dumps(history),
        ex=TTL_SECONDS
    )

def format_history_for_prompt(history: list[dict]) -> str:
    if not history:
        return ""
    formatted = []
    for item in history:
        formatted.append(f"User: {item["question"]}\nAssistant: {item["answer"]}")
    return "\n\n".join(formatted)