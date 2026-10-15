from sandbox_agent.sandbox import redact


def test_redacts_token_fields_and_urls_in_nested_tool_output():
    raw = [{"type": "text", "text": '{"sandbox_id": "sbx-1", "url": "http://a.b?token=abc123", "token": "abc123"}'}]
    out = redact((raw, None))
    text = out[0][0]["text"]
    assert "abc123" not in text and "sbx-1" in text
    assert redact("plain") == "plain"


def test_redacts_token_key_in_structured_content():
    assert redact({"structuredContent": {"token": "abc123", "sandbox_id": "s"}}) == {
        "structuredContent": {"token": "[redacted]", "sandbox_id": "s"}}
