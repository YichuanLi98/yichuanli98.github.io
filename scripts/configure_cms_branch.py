#!/usr/bin/env python3
"""Point a built Decap CMS config at the branch behind its preview."""

from __future__ import annotations

import argparse
import pathlib
import re


BACKEND_BRANCH = re.compile(
    r"(?m)^(backend:\s*\n(?:[ \t]+[^\n]*\n)*?[ \t]+branch:\s*)[^\n]+$"
)
VALID_BRANCH = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._/-]*[A-Za-z0-9])?")


def configure_branch(config_path: pathlib.Path, branch: str) -> None:
    if (
        VALID_BRANCH.fullmatch(branch) is None
        or ".." in branch
        or "//" in branch
        or "@{" in branch
    ):
        raise ValueError(f"invalid branch: {branch!r}")

    source = config_path.read_text(encoding="utf-8")
    updated, replacements = BACKEND_BRANCH.subn(rf"\g<1>{branch}", source, count=1)
    if replacements != 1:
        raise ValueError("expected exactly one backend branch in the CMS config")
    config_path.write_text(updated, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=pathlib.Path)
    parser.add_argument("--branch", required=True)
    arguments = parser.parse_args()
    configure_branch(arguments.config, arguments.branch)


if __name__ == "__main__":
    main()
