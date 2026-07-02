"""Arg substitution, quoting, and execution behavior."""

from qwen_assistant.collector import _execute, _substitute, resolve
from qwen_assistant.profiles import Profile


def test_substitute_quotes_user_input():
    out = _substitute("docker logs {container}", {"container": "x; rm -rf /"}, quote=True)
    assert out == "docker logs 'x; rm -rf /'"


def test_substitute_leaves_docker_format_untouched():
    cmd = 'docker ps --format "table {{.Names}}\t{{.Status}}"'
    assert _substitute(cmd, {"container": "web"}, quote=True) == cmd


def test_when_gating():
    profile = Profile(
        name="t",
        safety={"read_only": True},
        args=[{"name": "svc", "required": False}],
        commands=[
            {"run": "echo always"},
            {"run": "echo {svc}", "when": "svc"},
        ],
        prompt="p",
    )
    assert len(resolve(profile, {"svc": ""})) == 1
    assert len(resolve(profile, {"svc": "nginx"})) == 2


def test_execute_captures_output_and_failure():
    ok = _execute("echo hello", timeout=5)
    assert ok.output == "hello" and not ok.failed
    bad = _execute("false", timeout=5)
    assert bad.failed and bad.returncode == 1
    missing = _execute("definitely-not-a-command-xyz", timeout=5)
    assert missing.failed


def test_execute_pipeline_uses_shell():
    result = _execute("printf 'b\\na\\n' | sort", timeout=5)
    assert result.output.splitlines() == ["a", "b"]
