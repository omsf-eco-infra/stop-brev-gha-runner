import os
import subprocess

from gha_runner.clouddeployment import TeardownInstance
from gha_runner.gh import GitHubInstance
from gha_runner.helper.input import check_required

from .stop import StopBrev, parse_instance_mapping


def main():
    env = dict(os.environ)
    if env.get("INPUT_BREV_ORG"):
        raise ValueError(
            "brev_org is no longer supported. Create a BREV_API_KEY in the "
            "organization that owns the runners and remove brev_org."
        )
    check_required(env, ["GH_PAT", "BREV_API_KEY", "INPUT_INSTANCE_MAPPING"])

    repo = env.get("INPUT_REPO") or env.get("GITHUB_REPOSITORY")
    if not repo:
        raise ValueError("Missing required repository input")
    instance_mapping = parse_instance_mapping(env["INPUT_INSTANCE_MAPPING"])

    subprocess.run(
        ["brev", "login", "--api-key", env["BREV_API_KEY"]], check=True
    )

    deployment = TeardownInstance(
        provider_type=StopBrev,
        cloud_params={"instance_mapping": instance_mapping},
        gh=GitHubInstance(token=env["GH_PAT"], repo=repo),
    )
    deployment.stop_runner_instances()


if __name__ == "__main__":
    main()
