"""채팅 모델 생성과 LLM 출력 파싱 도우미."""
from __future__ import annotations

import json
import re

from src.config import chat_model, gms_key, llm_provider, openai_base_url, settings
from src.vectorstore.store import MissingKeyError

_llm = None


def get_llm():
    """GMS(OpenAI 호환) 채팅 모델. 한 번 만들어 재사용한다."""
    global _llm
    if _llm is None:
        if llm_provider() == "fake":
            from langchain_core.language_models.fake_chat_models import FakeListChatModel

            _llm = FakeListChatModel(responses=["[]"])
        else:
            key = gms_key()
            if not key:
                raise MissingKeyError("GMS_KEY가 설정되지 않았습니다. .env 를 확인하세요.")
            from langchain_openai import ChatOpenAI

            _llm = ChatOpenAI(
                model=chat_model(),
                api_key=key,
                base_url=openai_base_url(),
                temperature=settings()["models"]["temperature"],
                use_responses_api=settings()["models"]["use_responses_api"],  # GMS 안내: /v1/responses
                timeout=60,
                max_retries=2,
            )
    return _llm


def set_llm(llm) -> None:
    """테스트에서 가짜 모델을 끼워 넣을 때 쓴다."""
    global _llm
    _llm = llm


def ask(system: str, user: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    result = get_llm().invoke([SystemMessage(content=system), HumanMessage(content=user)])
    return result.text.strip()  # Responses API 는 content 가 블록 목록이라 .text 로 꺼낸다


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.M)


def parse_json(text: str, expect: type):
    """LLM 응답에서 JSON 배열/객체를 꺼낸다. 실패하면 None."""
    cleaned = _FENCE.sub("", text or "").strip()
    start, end = ("[", "]") if expect is list else ("{", "}")
    i, j = cleaned.find(start), cleaned.rfind(end)
    if i < 0 or j <= i:
        return None
    try:
        value = json.loads(cleaned[i : j + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, expect) else None
