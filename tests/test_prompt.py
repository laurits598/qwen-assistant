"""Truncation and prompt rendering."""

from qwen_assistant.collector import CommandResult
from qwen_assistant.config import Settings
from qwen_assistant.profiles import Profile
from qwen_assistant.prompt import build, clean, truncate


def test_truncate_keeps_head_and_tail():
    text = "\n".join(f"line{i}" for i in range(1000))
    out = truncate(text, max_lines=100, max_bytes=100_000)
    lines = out.splitlines()
    assert lines[0] == "line0"
    assert lines[-1] == "line999"
    assert any("omitted" in l for l in lines)
    assert len(lines) <= 101


def test_clean_strips_ansi():
    assert clean("\x1b[31mred\x1b[0m") == "red"


def test_build_renders_context_and_outputs():
    profile = Profile(
        name="t", safety={"read_only": True},
        commands=[{"run": "echo hi"}], prompt="Analyze this.", focus=["errors"],
    )
    results = [CommandResult(command="echo hi", label="Test", output="hi")]
    ctx = {"hostname": "box", "os_release": "TestOS", "kernel": "6.1",
           "uptime": "1d 0h 0m", "timestamp": "2026-07-02T12:00:00"}
    system, user = build(ctx, profile, results, Settings())
    assert "Status:" in system
    assert "box" in user and "echo hi" in user and "Analyze this." in user
    assert "Prioritize: errors" in user
