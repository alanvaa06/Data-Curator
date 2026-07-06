import pathlib
import re

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DOCKERFILE = REPO_ROOT / "Dockerfile"


@pytest.fixture
def dockerfile_lines():
    text = DOCKERFILE.read_text(encoding="utf-8")
    # Reduce to directive-level lines: drop blanks and comment-only lines.
    lines = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


def test_dockerfile_exists():
    assert DOCKERFILE.is_file()


def test_dockerfile_declares_non_root_user(dockerfile_lines):
    user_directives = [
        line for line in dockerfile_lines
        if re.match(r"^USER\s+", line, re.IGNORECASE)
    ]
    assert user_directives, "Dockerfile must declare a USER directive (container must not run as root)"


def test_dockerfile_user_is_not_root(dockerfile_lines):
    user_directives = [
        line for line in dockerfile_lines
        if re.match(r"^USER\s+", line, re.IGNORECASE)
    ]
    assert user_directives
    last_user = user_directives[-1].split(None, 1)[1].strip()
    # Reject root by name or by uid 0 (optionally with a group, e.g. "0:0").
    assert last_user.lower() != "root"
    assert last_user.split(":", 1)[0] != "0"


def test_user_directive_precedes_final_cmd(dockerfile_lines):
    cmd_indices = [
        i for i, line in enumerate(dockerfile_lines)
        if re.match(r"^CMD\s", line, re.IGNORECASE)
    ]
    assert cmd_indices, "Dockerfile must define a CMD"
    final_cmd_index = cmd_indices[-1]
    user_indices = [
        i for i, line in enumerate(dockerfile_lines)
        if re.match(r"^USER\s+", line, re.IGNORECASE)
    ]
    assert user_indices, "Dockerfile must declare a USER before the final CMD"
    assert min(user_indices) < final_cmd_index
