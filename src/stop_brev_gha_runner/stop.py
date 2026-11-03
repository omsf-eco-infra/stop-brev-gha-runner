import json
import subprocess
import time
from dataclasses import dataclass

from gha_runner.clouddeployment import StopCloudInstance

DEFAULT_TIMEOUT = 600
DEFAULT_INTERVAL = 5


def parse_timeout(value: str | None) -> int:
    """Parse and validate the deletion wait timeout in seconds."""
    if value is None or not value.strip():
        return DEFAULT_TIMEOUT

    timeout = value.strip()
    if not timeout.isdecimal() or int(timeout) <= 0:
        raise ValueError(
            f"timeout must be a positive integer number of seconds, got "
            f"{value!r}"
        )
    return int(timeout)


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
    """Delete ephemeral GitHub Actions runner instances from Brev.

    Parameters
    ----------
    instance_mapping : dict[str, str]
        Mapping of Brev instance names to GitHub runner labels.
    timeout : int
        Seconds to wait for deleted instances to disappear. Individual
        calls to ``wait_until_removed`` can override it with a keyword
        argument.

    """

    instance_mapping: dict[str, str]
    timeout: int = DEFAULT_TIMEOUT

    def remove_instances(self, ids: list[str]):
        subprocess.run(["brev", "delete", *ids], check=True)

    def wait_until_removed(self, ids: list[str], **kwargs):
        timeout = kwargs.get("timeout", self.timeout)
        interval = kwargs.get("interval", DEFAULT_INTERVAL)
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
