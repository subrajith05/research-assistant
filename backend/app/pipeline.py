import uuid
import logging
from typing import TypedDict
from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings
from app.retriever import retrieve_chunks
from app.memory import get_history, format_history_for_prompt
from app.models import AgentLog

logger = logging .getLogger(__name__)

llm = init_chat_model(
    model="gemini-3.1-flash-lite",
    model_provider="google_genai",
    api_key=settings.GEMINI_API_KEY
)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True
)
async def safe_llm_invoke(messages: list) -> str:
    """
    Calls the LLM with retry on transient failures (rate limits, timeouts, etc).
    Returns the extracted text content, handling both string and list content formats.
    """
    response = await llm.ainvoke(messages)
    content = response.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list) and content:
        return content[0].get("text", "").strip()
    return ""

# --- State ---

class AgentState(TypedDict):
    query: str
    refined_query: str
    intent: str
    chunks: list[str]
    summary: str
    is_valid: bool
    retry_count: int
    answer: str
    user_id: str
    session_id: str
    history: str


# --- Logging helper ---

async def log_agent(
    db: AsyncSession,
    session_id: str,
    agent_name: str,
    input: str,
    output: str,
    metadata: dict = None,
):
    try:
        log = AgentLog(
            id=uuid.uuid4(),
            session_id=uuid.UUID(session_id),
            agent_name=agent_name,
            input=input,
            output=output,
            agent_metadata=metadata or {},
        )
        db.add(log)
        await db.commit()
    except Exception as e:
        # Logging failures should never break the pipeline
        logger.error(f"Failed to write agent log for {agent_name}: {e}")
        await db.rollback()


# --- Agents ---

async def query_analyzer(state: AgentState, db: AsyncSession) -> AgentState:
    history_context = f"\n\nPrevious conversation:\n{state['history']}" if state["history"] else ""

    try:
        intent = await safe_llm_invoke([
            SystemMessage(content=(
                "You are a query intent analyzer. "
                "Classify the user query into one of: summarization, comparison, factual, technical, general. "
                "Use the previous conversation only as context to understand the current query better. "
                "Respond with only the intent word, nothing else."
            )),
            HumanMessage(content=f"{state['query']}{history_context}"),
        ])
        intent = intent.lower() if intent else "general"
    except Exception as e:
        logger.error(f"query_analyzer failed to classify intent : {e}")
        intent = "general"
    state["intent"] = intent

    if state["history"]:
        try:
            refined = await safe_llm_invoke([
                SystemMessage(content=(
                    "You rewrite follow-up questions into fully self-contained queries. "
                    "Use the previous conversation to resolve pronouns (he, him, it, that, etc.) "
                    "and ambiguous references into explicit names or subjects. "
                    "If the query is already self-contained, return it unchanged. "
                    "Respond with only the rewritten query, nothing else."
                )),
                HumanMessage(content=f"Previous conversation:\n{state['history']}\n\nFollow-up query: {state['query']}"),
            ])
            state["refined_query"] = refined or state["query"]
        except Exception as e:
            logger.error(f"query_analyzer query rewrite failed : {e}")
            state["refined_query"] = state["query"]
    else:
        state["refined_query"] = state["query"]


    await log_agent(db, state["session_id"], "query_analyzer",
                    input=state["query"], output=f"intent={intent}, refined_query={state['refined_query']}")
    return state


async def retrieval_agent(state: AgentState, db: AsyncSession) -> AgentState:
    try:
        chunks = await retrieve_chunks(
            query=state["refined_query"],
            user_id=state["user_id"],
            db=db
        )
    except Exception as e:
        logger.error(f"retrieval_agent failed : {e}")
        chunks = []
    state["chunks"] = chunks

    await log_agent(db, state["session_id"], "retrieval_agent",
                    input=state["refined_query"],
                    output=f"{len(chunks)} chunks retrieved",
                    metadata={"chunk_count": len(chunks)})
    return state


async def summarization_agent(state: AgentState, db: AsyncSession) -> AgentState:
    if not state["chunks"]:
        state["summary"] = ""
        return state

    context = "\n\n".join(state["chunks"])
    try:
        summary = await safe_llm_invoke([
            SystemMessage(content=(
                "You are a summarization agent. "
                "Given a user query and retrieved context, summarize the context concisely, "
                "keeping only information relevant to the query."
            )),
            HumanMessage(content=f"Query: {state['refined_query']}\n\nContext:\n{context}"),
        ])
    except Exception as e:
        logger.error(f"Summarization agent failed : {e}")
        summary = ""    
    state["summary"] = summary

    await log_agent(db, state["session_id"], "summarization_agent",
                    input=state["refined_query"], output=summary)
    return state


async def validation_agent(state: AgentState, db: AsyncSession) -> AgentState:
    if not state["summary"] and not state["chunks"]:
        state["is_valid"] = False
        await log_agent(db, state["session_id"], "validation_agent",
                        input=state["refined_query"], output="no",
                        metadata={"reason": "no context available"})
        return state

    context = state["summary"] or "\n\n".join(state["chunks"])
    try:
        result = await safe_llm_invoke([
            SystemMessage(content=(
                "You are a validation agent. "
                "Determine if the provided context contains enough relevant information to answer the query. "
                "Respond with only 'yes' or 'no'."
            )),
            HumanMessage(content=f"Query: {state['refined_query']}\n\nContext:\n{context}"),
        ])
        state["is_valid"] = result == "yes"
    except Exception as e:
        logger.error(f"validation_agent failed : {e}")
        state["is_valid"] = True
        result = "yes (fallback after error)"

    await log_agent(db, state["session_id"], "validation_agent",
                    input=state["refined_query"], output=result)
    return state


async def query_refiner(state: AgentState, db: AsyncSession) -> AgentState:
    try:
        refined = await safe_llm_invoke([
            SystemMessage(content=(
                "You are a query refinement agent. "
                "The original query did not retrieve relevant results. "
                "Rephrase the query to be more specific and likely to find relevant information. "
                "Respond with only the rephrased query, nothing else."
            )),
            HumanMessage(content=state["query"]),
        ])
        state["refined_query"] = refined or state["query"]
    except Exception as e:
        logger.error(f"query_refiner failed : {e}")
        state["refined_query"] = state["query"]
    
    state["retry_count"] = state.get("retry_count", 0) + 1

    await log_agent(db, state["session_id"], "query_refiner",
                    input=state["query"], output=state["refined_query"],
                    metadata={"retry_count": state["retry_count"]})
    return state


async def final_response_agent(state: AgentState, db: AsyncSession) -> AgentState:
    if not state["is_valid"]:
        state["answer"] = "I could not find enough relevant information in your documents to answer your query."
        await log_agent(db, state["session_id"], "final_response_agent",
                        input=state["query"], output=state["answer"],
                        metadata={"is_valid": False})
        return state

    context = state["summary"] or "\n\n".join(state["chunks"])
    history_context = f"\n\nPrevious conversation:\n{state['history']}" if state["history"] else ""
    
    try:
        answer = await safe_llm_invoke([
            SystemMessage(content=(
                "You are a helpful research assistant. "
                "Generate a clear, well-structured, and user-friendly answer based on the provided context. "
                "Use the previous conversation only to maintain continuity, not as a source of facts. "
                "Do not make up information beyond what is in the context."
            )),
            HumanMessage(content=f"Query: {state['query']}\nIntent: {state['intent']}{history_context}\n\nContext:\n{context}"),
        ])
        if not answer:
            answer = "I encountered an issue generating a response. Please try rephrasing your question."
    except Exception as e:
        logger.error(f"final_response_agent failed : {e}")
        answer = "I'm having trouble generating a response right now. Please try again in a moment."    
 
    state["answer"] = answer

    await log_agent(db, state["session_id"], "final_response_agent",
                    input=state["query"], output=answer,
                    metadata={"is_valid": True})
    return state


# --- Routing ---

def route_after_query_analyzer(state: AgentState) -> str:
    if state["intent"] in ["factual", "general"]:
        return "skip_summarization"
    return "summarization"


def route_after_validation(state: AgentState) -> str:
    if not state["is_valid"] and state.get("retry_count", 0) < 1:
        return "retry"
    return "final"


# --- Graph ---

def build_pipeline(db: AsyncSession):
    graph = StateGraph(AgentState)

    async def query_analyzer_node(state: AgentState) -> AgentState:
        return await query_analyzer(state, db)

    async def retrieval_agent_node(state: AgentState) -> AgentState:
        return await retrieval_agent(state, db)

    async def summarization_agent_node(state: AgentState) -> AgentState:
        return await summarization_agent(state, db)

    async def validation_agent_node(state: AgentState) -> AgentState:
        return await validation_agent(state, db)

    async def query_refiner_node(state: AgentState) -> AgentState:
        return await query_refiner(state, db)

    async def final_response_agent_node(state: AgentState) -> AgentState:
        return await final_response_agent(state, db)

    graph.add_node("query_analyzer", query_analyzer_node)
    graph.add_node("retrieval_agent", retrieval_agent_node)
    graph.add_node("summarization_agent", summarization_agent_node)
    graph.add_node("validation_agent", validation_agent_node)
    graph.add_node("query_refiner", query_refiner_node)
    graph.add_node("final_response_agent", final_response_agent_node)

    graph.set_entry_point("query_analyzer")

    graph.add_conditional_edges(
        "query_analyzer",
        route_after_query_analyzer,
        {
            "summarization": "retrieval_agent",
            "skip_summarization": "retrieval_agent"
        }
    )

    graph.add_conditional_edges(
        "retrieval_agent",
        lambda state: "skip" if state["intent"] in ["factual", "general"] else "summarize",
        {
            "skip": "validation_agent",
            "summarize": "summarization_agent",
        }
    )

    graph.add_edge("summarization_agent", "validation_agent")

    graph.add_conditional_edges(
        "validation_agent",
        route_after_validation,
        {
            "retry": "query_refiner",
            "final": "final_response_agent"
        }
    )

    graph.add_edge("query_refiner", "retrieval_agent")
    graph.add_edge("final_response_agent", END)

    return graph.compile()


async def run_pipeline(query: str, user_id: str, session_id: str, db: AsyncSession) -> str:
    try:
        pipeline = build_pipeline(db)
        past_history = await get_history(session_id)
        history_text = format_history_for_prompt(past_history)

        initial_state = AgentState(
            query=query,
            refined_query=query,
            intent="",
            chunks=[],
            summary="",
            is_valid=False,
            retry_count=0,
            answer="",
            user_id=user_id,
            session_id=session_id,
            history=history_text,
        )
        final_state = await pipeline.ainvoke(initial_state)
        return final_state["answer"]
    except Exception as e:
        logger.error(f"Pipieline execution failed entirely : {e}")
        return "Something went wrong while processing your request. Please try again shortly."
    