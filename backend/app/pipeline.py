import uuid
from typing import TypedDict
from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.retriever import retrieve_chunks
from app.memory import get_history, format_history_for_prompt
from app.models import AgentLog

llm = init_chat_model(
    model="gemini-3.1-flash-lite",
    model_provider="google_genai",
    api_key=settings.GEMINI_API_KEY
)


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


# --- Agents ---

async def query_analyzer(state: AgentState, db: AsyncSession) -> AgentState:
    history_context = f"\n\nPrevious conversation:\n{state['history']}" if state["history"] else ""

    intent_response = await llm.ainvoke([
        SystemMessage(content=(
            "You are a query intent analyzer. "
            "Classify the user query into one of: summarization, comparison, factual, technical, general. "
            "Use the previous conversation only as context to understand the current query better. "
            "Respond with only the intent word, nothing else."
        )),
        HumanMessage(content=f"{state['query']}{history_context}"),
    ])
    intent = intent_response.content[0]["text"].strip().lower()
    state["intent"] = intent

    if state["history"]:
        rewrite_response = await llm.ainvoke([
            SystemMessage(content=(
                "You rewrite follow-up questions into fully self-contained queries. "
                "Use the previous conversation to resolve pronouns (he, him, it, that, etc.) "
                "and ambiguous references into explicit names or subjects. "
                "If the query is already self-contained, return it unchanged. "
                "Respond with only the rewritten query, nothing else."
            )),
            HumanMessage(content=f"Previous conversation:\n{state['history']}\n\nFollow-up query: {state['query']}"),
        ])
        state["refined_query"] = rewrite_response.content[0]["text"].strip()
    else:
        state["refined_query"] = state["query"]

    await log_agent(db, state["session_id"], "query_analyzer",
                    input=state["query"], output=f"intent={intent}, refined_query={state['refined_query']}")
    return state


async def retrieval_agent(state: AgentState, db: AsyncSession) -> AgentState:
    chunks = await retrieve_chunks(
        query=state["refined_query"],
        user_id=state["user_id"],
        db=db
    )
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
    response = await llm.ainvoke([
        SystemMessage(content=(
            "You are a summarization agent. "
            "Given a user query and retrieved context, summarize the context concisely, "
            "keeping only information relevant to the query."
        )),
        HumanMessage(content=f"Query: {state['refined_query']}\n\nContext:\n{context}"),
    ])
    summary = response.content[0]["text"].strip()
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
    response = await llm.ainvoke([
        SystemMessage(content=(
            "You are a validation agent. "
            "Determine if the provided context contains enough relevant information to answer the query. "
            "Respond with only 'yes' or 'no'."
        )),
        HumanMessage(content=f"Query: {state['refined_query']}\n\nContext:\n{context}"),
    ])
    result = response.content[0]["text"].strip().lower()
    state["is_valid"] = result == "yes"

    await log_agent(db, state["session_id"], "validation_agent",
                    input=state["refined_query"], output=result)
    return state


async def query_refiner(state: AgentState, db: AsyncSession) -> AgentState:
    response = await llm.ainvoke([
        SystemMessage(content=(
            "You are a query refinement agent. "
            "The original query did not retrieve relevant results. "
            "Rephrase the query to be more specific and likely to find relevant information. "
            "Respond with only the rephrased query, nothing else."
        )),
        HumanMessage(content=state["query"]),
    ])
    refined = response.content[0]["text"].strip()
    state["refined_query"] = refined
    state["retry_count"] = state.get("retry_count", 0) + 1

    await log_agent(db, state["session_id"], "query_refiner",
                    input=state["query"], output=refined,
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
    response = await llm.ainvoke([
        SystemMessage(content=(
            "You are a helpful research assistant. "
            "Generate a clear, well-structured, and user-friendly answer based on the provided context. "
            "Use the previous conversation only to maintain continuity, not as a source of facts. "
            "Do not make up information beyond what is in the context."
        )),
        HumanMessage(content=f"Query: {state['query']}\nIntent: {state['intent']}{history_context}\n\nContext:\n{context}"),
    ])
    answer = response.content[0]["text"].strip()
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