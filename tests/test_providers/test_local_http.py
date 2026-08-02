"""Tests for local HTTP helper utilities."""

from sat.providers.local_http import extract_json_text, normalize_host, schema_for_ollama_format


def test_normalize_host_strips_v1_suffix():
    assert normalize_host("http://127.0.0.1:11434/v1/") == "http://127.0.0.1:11434"
    assert normalize_host("http://localhost:1234/api/v1") == "http://localhost:1234"


def test_extract_json_text_from_fence():
    text = 'Here:\n```json\n{"a": 1}\n```\n'
    assert extract_json_text(text) == '{"a": 1}'


def test_schema_for_ollama_format_strips_title():
    schema = {"title": "X", "type": "object", "properties": {"a": {"type": "string", "title": "A"}}}
    cleaned = schema_for_ollama_format(schema)
    assert "title" not in cleaned
    assert "title" not in cleaned["properties"]["a"]
