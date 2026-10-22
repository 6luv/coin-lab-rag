"""LangGraph RAG: retrieve → generate 두 노드 (F2007 · F2008).

mode
- ask: 사용자 질문에 답한다
- brief: 리스크 브리핑 (F2010)
- factcheck: 주장 사실 여부 판정 (F2010)
"""
from __future__ import annotations

import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from src.data_prep import catalog, prompts
from src.rag import llm
from src.rag.retrieve import retrieve as search

CITE = re.compile(r"[\[［]\s*근거\s*([\d,\s~\-–]+)[\]］]")


class RagState(TypedDict, total=False):
    coin_id: str
    mode: str
    question: str
    contexts: list[dict]
    answer: str
    sources: list[dict]
    cited: bool


def _query(state: RagState) -> str:
    if state["mode"] == "brief":
        return prompts.BRIEF_QUERY
    return state.get("question", "")


def retrieve_node(state: RagState) -> RagState:
    return {"contexts": search(state["coin_id"], _query(state))}


def _task(state: RagState) -> str:
    if state["mode"] == "brief":
        return prompts.BRIEF_TASK
    if state["mode"] == "factcheck":
        return prompts.FACTCHECK_TASK.format(claim=state["question"])
    return prompts.ASK_TASK.format(question=state["question"])


def cited_numbers(answer: str) -> set[int]:
    nums = set()
    for group in CITE.findall(answer or ""):
        for part in group.split(","):
            bounds = [int(n) for n in re.findall(r"\d+", part)]
            if len(bounds) == 2 and bounds[0] <= bounds[1] <= bounds[0] + 50:  # [근거 1-3]
                nums.update(range(bounds[0], bounds[1] + 1))
            else:
                nums.update(bounds)
    return nums


def _label(ctx: dict) -> str:
    """출처 종류 라벨. PDF 근거는 쪽 번호를 붙인다 (F2016)."""
    return f"{ctx['source_label']} p.{ctx['page']}" if ctx.get("page") else ctx["source_label"]


def generate_node(state: RagState) -> RagState:
    coin = catalog.get(state["coin_id"])
    contexts = state["contexts"]
    block = "\n\n".join(f"[근거 {c['index']}] ({_label(c)}) {c['title']}\n{c['text']}" for c in contexts)
    answer = llm.ask(
        prompts.ANSWER_SYSTEM,
        prompts.ANSWER_USER.format(label=coin["label"], contexts=block, task=_task(state)),
    )
    used = cited_numbers(answer)
    sources = [
        {k: c.get(k) for k in ("index", "title", "url", "source_type", "source_label", "page")}
        for c in contexts
        if c["index"] in used
    ]
    return {"answer": answer, "sources": sources, "cited": bool(sources)}


def build_graph():
    g = StateGraph(RagState)
    g.add_node("retrieve", retrieve_node)
    g.add_node("generate", generate_node)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", END)
    return g.compile()


_graph = None


def run(coin_id: str, question: str, mode: str = "ask") -> dict:
    global _graph
    if catalog.get(coin_id) is None:
        raise KeyError(coin_id)
    if _graph is None:
        _graph = build_graph()
    out = _graph.invoke({"coin_id": coin_id, "question": question, "mode": mode})
    return {"answer": out["answer"], "sources": out["sources"], "cited": out["cited"]}
