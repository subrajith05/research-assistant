from typing import Annotated, TypedDict
from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.retriever import retrieve_chunks

llm = init_chat_model(
    model="gemini-3.1-flash-lite",
    model_provider="google_genai",
    api_key=settings.GEMINI_API_KEY
)

#State
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


#---Agents---
async def query_analyzer(state: AgentState) -> AgentState:
    response = await llm.ainvoke([
        SystemMessage(content=(
            "You are a query intent analyzer. "
            "Classify the user query into one of: summarization, comparison, factual, technical, general. "
            "Respond with only the intent word, nothing else."
        )),
        HumanMessage(content=state["query"]),
    ])
    state["intent"] = response.content[0]["text"].strip().lower()
    state["refined_query"] = state["query"]
    return state

async def retrieval_agent(state: AgentState, db: AsyncSession) -> AgentState:
    chunks = await retrieve_chunks(
        query=state["refined_query"],
        user_id=state["user_id"],
        db=db
    )
    state["chunks"] = chunks
    return state

async def summarization_agent(state: AgentState) -> AgentState:
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
    state["summary"] = response.content[0]["text"].strip()
    return state

async def validation_agent(state: AgentState) -> AgentState:
    if not state["summary"] and not state["chunks"]:
        state["is_valid"] = False
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

    state["is_valid"] = response.content[0]["text"].strip().lower() == "yes"
    return state

async def query_refiner(state: AgentState) -> AgentState:
    response = await llm.ainvoke([
        SystemMessage(content=(
            "You are a query refinement agent. "
            "The original query did not retrieve relevant results. "
            "Rephrase the query to be more specific and likely to find relevant information. "
            "Respond with only the rephrased query, nothing else."
        )),
        HumanMessage(content=state["query"]),
    ])
    state["refined_query"] = response.content[0]["text"].strip()
    state["retry_count"] = state.get("retry_count", 0) + 1
    return state

async def final_response_agent(state: AgentState) -> AgentState:
    if not state["is_valid"]:
        state["answer"] = "I could not find enough relevant information in your documents to answer your query"
        return state
    
    context = state["summary"] or "\n\n".join(state["chunks"])
    response = await llm.ainvoke([
        SystemMessage(content=(
            "You are a helpful research assistant. "
            "Generate a clear, well-structured, and user-friendly answer based on the provided context. "
            "Do not make up information beyond what is in the context."
        )),
        HumanMessage(content=f"Query: {state['query']}\nIntent: {state['intent']}\n\nContext:\n{context}"),
    ])
    state["answer"] = response.content[0]["text"].strip()
    return state


#--- Routing ---

def route_after_query_analyzer(state: AgentState) -> str:
    if state["intent"] in ["factual", "general"]:
        return "skip_summarization"
    return "summarization"

def route_after_validation(state: AgentState) -> str:
    if not state["is_valid"] and state.get("retry_count", 0) < 1:
        return "retry"
    return "final"


#--- Graph ---

def build_pipeline(db: AsyncSession):
    graph = StateGraph(AgentState)

    async def retrieval_agent_node(state: AgentState) -> AgentState:
        return await retrieval_agent(state, db)
    
    graph.add_node("query_analyzer", query_analyzer)
    graph.add_node("retrieval_agent", retrieval_agent_node)
    graph.add_node("summarization_agent", summarization_agent)
    graph.add_node("validation_agent", validation_agent)
    graph.add_node("query_refiner", query_refiner)
    graph.add_node("final_response_agent", final_response_agent)

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

async def run_pipeline(query: str, user_id: str, db: AsyncSession) -> str:
    pipeline = build_pipeline(db)
    initial_state = AgentState(
        query=query,
        refined_query=query,
        intent="",
        chunks=[],
        summary="",
        is_valid=False,
        retry_count=0,
        answer="",
        user_id=user_id
    )
    final_state = await pipeline.ainvoke(initial_state)
    return final_state["answer"]