#!/usr/bin/env python3
"""Upload Debian artifacts and create a GitLab release with package links."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]


def die(message: str) -> None:
    print(f"ci-publish-gitlab-release: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        die(f"missing required env: {key}")
    return value


def curl(*args: str, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["curl", *args],
        check=not capture_output,
        cwd=REPO_ROOT,
        text=True,
        capture_output=capture_output,
    )


def find_artifacts(root: Path) -> list[Path]:
    files = sorted(path for path in root.glob("*.deb") if path.is_file())
    if not files:
        die(f"no .deb files under {root}")
    return files


def release_description_for_tag(tag: str, package_name: str) -> str:
    note_tag = tag if tag.startswith("v") else f"v{tag}"
    release_note = REPO_ROOT / "docs" / "release-notes" / f"{note_tag}.md"
    if release_note.is_file():
        return release_note.read_text(encoding="utf-8")
    return f"{package_name} package artifacts for {tag}."


def main() -> int:
    api_v4_url = require_env("CI_API_V4_URL").rstrip("/")
    project_id = quote(require_env("CI_PROJECT_ID"), safe="")
    job_token = require_env("CI_JOB_TOKEN")
    tag = require_env("CI_COMMIT_TAG")
    # Match scripts/ci-build, including its explicit Debian version override.
    package_version = quote(os.environ.get("DEB_VERSION") or tag.removeprefix("v"), safe="")
    with (REPO_ROOT / "packaging.toml").open("rb") as stream:
        package_name = tomllib.load(stream)["package"]["name"]

    artifacts = find_artifacts(REPO_ROOT / "dist")
    links: list[dict[str, str]] = []
    for file in artifacts:
        upload_url = (
            f"{api_v4_url}/projects/{project_id}/packages/generic/"
            f"{quote(package_name, safe='')}/{package_version}/{quote(file.name, safe='')}"
        )
        print(f"uploading {file.name}", flush=True)
        curl(
            "--fail",
            "--silent",
            "--show-error",
            "--header",
            f"JOB-TOKEN: {job_token}",
            "--upload-file",
            str(file),
            "--output",
            os.devnull,
            upload_url,
        )
        links.append({"name": file.name, "url": upload_url, "link_type": "package"})

    payload = {
        "name": f"{package_name} {tag}",
        "tag_name": tag,
        "description": release_description_for_tag(tag, package_name),
        "assets": {"links": links},
    }
    release_url = f"{api_v4_url}/projects/{project_id}/releases"
    with (
        tempfile.NamedTemporaryFile("w", encoding="utf-8") as payload_file,
        tempfile.NamedTemporaryFile("w+", encoding="utf-8") as response_file,
    ):
        json.dump(payload, payload_file, sort_keys=True)
        payload_file.flush()
        result = curl(
            "--silent",
            "--show-error",
            "--write-out",
            "%{http_code}",
            "--request",
            "POST",
            "--header",
            f"JOB-TOKEN: {job_token}",
            "--header",
            "Content-Type: application/json",
            "--data",
            f"@{payload_file.name}",
            "--output",
            response_file.name,
            release_url,
            capture_output=True,
        )
        response_file.seek(0)
        response_body = response_file.read()

    if result.returncode != 0 or result.stdout.strip() != "201":
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        if response_body:
            print(response_body, file=sys.stderr, end="")
        die(f"GitLab release create failed with HTTP {result.stdout.strip() or 'unknown'}")

    print(f"created GitLab release for {tag}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
