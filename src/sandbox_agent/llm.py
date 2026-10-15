"""Chat model for the agent: an OpenAI-compatible endpoint (e.g. Databricks) serving gpt-oss."""

from typing import Any

from langchain_openai import ChatOpenAI

from .settings import Settings, get_settings


def _text_of(block: Any) -> str:
    """Text of a plain-string or text block; "" for reasoning, images and anything else."""
    if isinstance(block, str):
        return block
    if isinstance(block, dict) and block.get("type") in ("text", "output_text"):
        return block.get("text", "")
    return ""


class DatabricksChatModel(ChatOpenAI):
    """
    Chat-completions model for gpt-oss behind the Databricks gateway.

    Responses are left untouched: `content` is a list of typed blocks (reasoning, text), which
    ag-ui-langgraph turns into REASONING_* events for the UI. The gateway, however, only accepts
    string content in *requests*, so replayed assistant/tool messages are flattened to their text.
    """

    def _get_request_payload(self, input_: Any, *, stop: list[str] | None = None, **kwargs: Any) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        for message in payload.get("messages", []):
            content = message.get("content")
            if isinstance(content, list):
                message["content"] = "".join(_text_of(b) for b in content)
        return payload


def get_model(settings: Settings | None = None, temperature: float = 0.1) -> DatabricksChatModel:
    s = settings or get_settings()
    api_key = s.api_key()
    missing = [
        name for name, value in (
            ("LLM_BASE_URL", s.llm_base_url),
            ("LLM_MODEL", s.llm_model),
            ("LLM_API_KEY or LLM_API_KEY_FILE", api_key),
        ) if not value
    ]
    if missing:
        raise RuntimeError(
            f"Model is not configured: set {', '.join(missing)} in the environment or .env "
            "(see .env.example)."
        )
    return DatabricksChatModel(
        base_url=s.llm_base_url, api_key=api_key, model=s.llm_model, temperature=temperature,
        # The gateway rate-limits input tokens per minute (429); a long agent run hits that. Back off
        # and retry (the client honours Retry-After) instead of failing the whole run.
        max_retries=8, timeout=180,
    )
