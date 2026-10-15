"""
Runtime configuration, read from the environment (and a `.env` file in the working directory).

Nothing about the model endpoint or its credentials is baked into the code: set
`LLM_BASE_URL`, `LLM_MODEL` and one of `LLM_API_KEY` / `LLM_API_KEY_FILE`. They are
validated when the model is built (`llm.get_model`), so tests and tooling that never
call the model need none of them.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

AGENT_NAME = "sandbox_agent"  # also the agent id the frontend connects to


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Sandbox MCP server and the identity this service attaches to its connection.
    mcp_url: str = Field("http://mcp.sandbox.localhost/mcp", validation_alias="SANDBOX_MCP_URL")
    user_id: str = Field("local-user", validation_alias="SANDBOX_USER_ID")
    session_id: str = Field("agent-service", validation_alias="SANDBOX_SESSION_ID")

    # Where the agent's conversation state (threads, session sandbox, published apps) is kept.
    data_dir: Path = Field(Path("data"), validation_alias="SANDBOX_AGENT_DATA_DIR")

    # Hand sandbox-changing work to subagents (see agent/subagents.py).
    delegate: bool = Field(False, validation_alias="AGENT_DELEGATE")

    # Any OpenAI-compatible chat endpoint, e.g. a Databricks AI Gateway / serving endpoint.
    llm_base_url: str | None = Field(None, validation_alias="LLM_BASE_URL")
    llm_model: str | None = Field(None, validation_alias="LLM_MODEL")
    llm_api_key: SecretStr | None = Field(None, validation_alias=AliasChoices("LLM_API_KEY"))
    llm_api_key_file: Path | None = Field(None, validation_alias="LLM_API_KEY_FILE")

    @property
    def checkpoint_db(self) -> Path:
        return self.data_dir / "threads.sqlite"

    def api_key(self) -> str | None:
        """The key from LLM_API_KEY, else the contents of LLM_API_KEY_FILE."""
        if self.llm_api_key and self.llm_api_key.get_secret_value().strip():
            return self.llm_api_key.get_secret_value().strip()
        if self.llm_api_key_file and self.llm_api_key_file.expanduser().is_file():
            return self.llm_api_key_file.expanduser().read_text().strip() or None
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
