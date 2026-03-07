from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


@dataclass
class CommandResult:
    ok: bool
    stdout: str
    stderr: str


class DockerCli:
    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def run(self, *args: str) -> CommandResult:
        try:
            proc = subprocess.run(
                ["docker", *args],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return CommandResult(ok=False, stdout="", stderr=str(exc))
        return CommandResult(ok=proc.returncode == 0, stdout=proc.stdout, stderr=proc.stderr)

    def list_containers(self) -> list[dict]:
        result = self.run("ps", "-a", "--format", "{{json .}}")
        if not result.ok:
            return []
        rows = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows

    def inspect_container(self, container_id: str) -> dict | None:
        result = self.run("inspect", container_id)
        if not result.ok:
            return None
        parsed = json.loads(result.stdout)
        return parsed[0] if parsed else None

    def list_networks(self) -> list[dict]:
        result = self.run("network", "ls", "--format", "{{json .}}")
        if not result.ok:
            return []
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

    def list_volumes(self) -> list[dict]:
        result = self.run("volume", "ls", "--format", "{{json .}}")
        if not result.ok:
            return []
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

    def service_action(self, container_name: str, action: str) -> CommandResult:
        return self.run(action, container_name)
