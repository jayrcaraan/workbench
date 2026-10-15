import pytest

from sandbox_agent.llm import get_model
from sandbox_agent.settings import Settings


def settings(**env):
    # _env_file=None: ignore any developer .env while testing.
    return Settings(_env_file=None, **env)


def test_nothing_about_the_model_is_hardcoded():
    s = settings()
    assert s.llm_base_url is None and s.llm_model is None and s.api_key() is None


def test_get_model_names_every_missing_setting():
    with pytest.raises(RuntimeError) as e:
        get_model(settings())
    msg = str(e.value)
    assert "LLM_BASE_URL" in msg and "LLM_MODEL" in msg and "LLM_API_KEY" in msg


def test_key_from_env_or_file(tmp_path):
    assert settings(LLM_API_KEY=" abc ").api_key() == "abc"
    key_file = tmp_path / "key"
    key_file.write_text("from-file\n")
    assert settings(LLM_API_KEY_FILE=str(key_file)).api_key() == "from-file"
    assert settings(LLM_API_KEY_FILE=str(tmp_path / "missing")).api_key() is None


def test_get_model_uses_configured_endpoint():
    m = get_model(settings(LLM_BASE_URL="https://llm.example/v1", LLM_MODEL="m1", LLM_API_KEY="k"))
    assert m.model_name == "m1" and str(m.openai_api_base) == "https://llm.example/v1"
