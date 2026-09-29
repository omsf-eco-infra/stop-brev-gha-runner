import json
import subprocess
import unittest
from unittest.mock import call, patch

from gha_runner.gh import MissingRunnerLabel
from stop_brev_gha_runner.__main__ import main
from stop_brev_gha_runner.stop import StopBrev, parse_instance_mapping


class StopBrevTests(unittest.TestCase):
    def setUp(self):
        self.mapping = {
            "runner-one": "runner-one",
            "runner-two": "runner-two",
        }
        self.brev = StopBrev(instance_mapping=self.mapping)

    def test_parses_start_mapping(self):
        self.assertEqual(
            parse_instance_mapping(json.dumps(self.mapping)), self.mapping
        )
        self.assertEqual(self.brev.get_instance_mapping(), self.mapping)

    def test_rejects_malformed_or_empty_mapping(self):
        invalid = [
            "not json",
            "{}",
            "[]",
            '{"": "runner"}',
            '{"instance": ""}',
            '{"instance": null}',
        ]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "instance_mapping"):
                    parse_instance_mapping(value)

    @patch("stop_brev_gha_runner.stop.subprocess.run")
    def test_permanently_deletes_instances(self, run):
        self.brev.remove_instances(["runner-one", "runner-two"])

        run.assert_called_once_with(
            ["brev", "delete", "runner-one", "runner-two"], check=True
        )
        self.assertNotIn("stop", run.call_args.args[0])

    @patch("stop_brev_gha_runner.stop.subprocess.run")
    def test_waits_until_instances_are_absent(self, run):
        run.return_value = subprocess.CompletedProcess(
            ["brev", "ls", "--json"],
            0,
            stdout='{"workspaces": null}',
        )

        self.brev.wait_until_removed(["runner-one"], timeout=0)

        run.assert_called_once_with(
            ["brev", "ls", "--json"],
            check=True,
            capture_output=True,
            text=True,
        )


class MainTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "BREV_API_KEY": "brev-api-key",
            "GH_PAT": "gh-token",
            "GITHUB_REPOSITORY": "owner/repo",
            "INPUT_BREV_ORG": "",
            "INPUT_INSTANCE_MAPPING": '{"brev-name": "runner-label"}',
        }

    @patch("stop_brev_gha_runner.__main__.TeardownInstance")
    @patch("stop_brev_gha_runner.__main__.GitHubInstance")
    @patch("stop_brev_gha_runner.__main__.subprocess.run")
    def test_authenticates_and_tears_down(self, run, github, teardown):
        with patch.dict("os.environ", self.env, clear=True):
            main()

        run.assert_called_once_with(
            ["brev", "login", "--api-key", "brev-api-key"], check=True
        )
        github.assert_called_once_with(token="gh-token", repo="owner/repo")
        teardown.assert_called_once_with(
            provider_type=StopBrev,
            cloud_params={"instance_mapping": {"brev-name": "runner-label"}},
            gh=github.return_value,
        )
        teardown.return_value.stop_runner_instances.assert_called_once_with()

    @patch("stop_brev_gha_runner.__main__.subprocess.run")
    def test_rejects_legacy_organization_before_login(self, run):
        env = {**self.env, "INPUT_BREV_ORG": "my-team"}
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaisesRegex(
                ValueError, "brev_org is no longer supported.*BREV_API_KEY"
            ):
                main()
        run.assert_not_called()

    @patch("stop_brev_gha_runner.__main__.subprocess.run")
    def test_rejects_missing_credentials(self, run):
        env = {**self.env, "BREV_API_KEY": ""}
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaisesRegex(ValueError, "BREV_API_KEY"):
                main()
        run.assert_not_called()

    @patch("stop_brev_gha_runner.__main__.GitHubInstance")
    @patch("stop_brev_gha_runner.__main__.subprocess.run")
    def test_deletes_instance_when_runner_registration_is_missing(
        self, run, github
    ):
        github.return_value.remove_runner.side_effect = MissingRunnerLabel(
            "runner-label"
        )
        run.return_value = subprocess.CompletedProcess(
            ["brev", "ls", "--json"], 0, stdout='{"workspaces": []}'
        )

        with patch.dict("os.environ", self.env, clear=True):
            main()

        github.return_value.remove_runner.assert_called_once_with("runner-label")
        self.assertEqual(
            run.call_args_list,
            [
                call(["brev", "login", "--api-key", "brev-api-key"], check=True),
                call(["brev", "delete", "brev-name"], check=True),
                call(
                    ["brev", "ls", "--json"],
                    check=True,
                    capture_output=True,
                    text=True,
                ),
            ],
        )

    @patch("stop_brev_gha_runner.__main__.subprocess.run")
    def test_rejects_malformed_mapping_before_login(self, run):
        env = {**self.env, "INPUT_INSTANCE_MAPPING": "not json"}
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaisesRegex(ValueError, "valid JSON"):
                main()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
