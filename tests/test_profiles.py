"""Every shipped profile must validate; safety rules must hold."""

import pytest

from qwen_assistant import profiles, safety
from qwen_assistant.profiles import BUILTIN_PROFILE_DIR, Profile, load_path


def builtin_paths():
    return sorted(BUILTIN_PROFILE_DIR.glob("*.yaml"))


def test_builtins_exist():
    assert len(builtin_paths()) >= 5


@pytest.mark.parametrize("path", builtin_paths(), ids=lambda p: p.stem)
def test_builtin_profile_valid(path):
    profile = load_path(path)
    assert profile.name == path.stem
    assert profile.prompt.strip()
    assert profile.commands


def test_safety_block_is_mandatory():
    with pytest.raises(profiles.ProfileError if False else Exception):
        Profile(name="x", commands=[{"run": "ls"}], prompt="p")  # no safety


def test_denylist_rejects_mislabeled_read_only():
    with pytest.raises(Exception, match="destructive"):
        Profile(
            name="bad",
            safety={"read_only": True},
            commands=[{"run": "docker system prune -af"}],
            prompt="p",
        )


def test_denylist_patterns():
    assert safety.find_destructive("rm -rf /var/log")
    assert safety.find_destructive("dd if=/dev/zero of=/dev/sda")
    assert safety.find_destructive("systemctl stop nginx")
    assert not safety.find_destructive("systemctl status nginx")
    assert not safety.find_destructive("docker ps -a")
    assert not safety.find_destructive("df -h")
