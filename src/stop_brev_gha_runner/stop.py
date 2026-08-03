import json
import subprocess
import time
from dataclasses import dataclass

from gha_runner.clouddeployment import StopCloudInstance


def parse_instance_mapping(value: str | dict) -> dict[str, str]:
    """Parse and validate the start action's instance mapping."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("instance_mapping must be valid JSON") from error

    if not isinstance(value, dict) or not value:
        raise ValueError("instance_mapping must be a non-empty JSON object")
    if not all(
        isinstance(name, str)
        and name.strip()
        and isinstance(label, str)
        and label.strip()
        for name, label in value.items()
    ):
        raise ValueError(
            "instance_mapping keys and values must be non-empty strings"
        )
    return value


@dataclass
class StopBrev(StopCloudInstance):
    """Delete ephemeral GitHub Actions runner instances from Brev."""

    instance_mapping: dict[str, str]

    def remove_instances(self, ids: list[str]):
        subprocess.run(["brev", "delete", *ids], check=True)

    def wait_until_removed(self, ids: list[str], **kwargs):
        timeout = kwargs.get("timeout", 600)
        interval = kwargs.get("interval", 5)
        deadline = time.monotonic() + timeout
        pending = set(ids)

        while pending:
            result = subprocess.run(
                ["brev", "ls", "--json"],
                check=True,
                capture_output=True,
                text=True,
            )
            data = json.loads(result.stdout)
            if isinstance(data, dict):
                if "workspaces" not in data:
                    raise ValueError("brev ls JSON has no workspaces field")
                workspaces = data["workspaces"] or []
            else:
                workspaces = data
            if not isinstance(workspaces, list):
                raise ValueError("brev ls returned malformed JSON")
            pending &= {
                workspace["name"]
                for workspace in workspaces
                if isinstance(workspace, dict) and "name" in workspace
            }
            if not pending:
                return
            if time.monotonic() >= deadline:
                names = ", ".join(sorted(pending))
                raise TimeoutError(f"Brev instances were not deleted: {names}")
            time.sleep(interval)

    def get_instance_mapping(self) -> dict[str, str]:
        return parse_instance_mapping(self.instance_mapping)
