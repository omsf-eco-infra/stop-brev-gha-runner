import json
import subprocess
import unittest
from unittest.mock import call, patch

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
            "BREV_TOKEN": "brev-token",
            "GH_PAT": "gh-token",
            "GITHUB_REPOSITORY": "owner/repo",
            "INPUT_INSTANCE_MAPPING": '{"brev-name": "runner-label"}',
        }

    @patch("stop_brev_gha_runner.__main__.TeardownInstance")
    @patch("stop_brev_gha_runner.__main__.GitHubInstance")
    @patch("stop_brev_gha_runner.__main__.subprocess.run")
    def test_authenticates_and_tears_down(self, run, github, teardown):
        with patch.dict("os.environ", self.env, clear=True):
            main()

        run.assert_called_once_with(
            ["brev", "login", "--token", "brev-token"], check=True
        )
        github.assert_called_once_with(token="gh-token", repo="owner/repo")
        teardown.assert_called_once_with(
            provider_type=StopBrev,
            cloud_params={"instance_mapping": {"brev-name": "runner-label"}},
            gh=github.return_value,
        )
        teardown.return_value.stop_runner_instances.assert_called_once_with()

    @patch("stop_brev_gha_runner.__main__.TeardownInstance")
    @patch("stop_brev_gha_runner.__main__.GitHubInstance")
    @patch("stop_brev_gha_runner.__main__.subprocess.run")
    def test_selects_optional_organization(self, run, _github, _teardown):
        env = {**self.env, "INPUT_BREV_ORG": "my-team"}
        with patch.dict("os.environ", env, clear=True):
            main()

        self.assertEqual(
            run.call_args_list,
            [
                call(["brev", "login", "--token", "brev-token"], check=True),
                call(["brev", "set", "my-team"], check=True),
            ],
        )

    @patch("stop_brev_gha_runner.__main__.subprocess.run")
    def test_rejects_missing_credentials(self, run):
        env = {**self.env, "BREV_TOKEN": ""}
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaisesRegex(ValueError, "BREV_TOKEN"):
                main()
        run.assert_not_called()

    @patch("stop_brev_gha_runner.__main__.subprocess.run")
    def test_rejects_malformed_mapping_before_login(self, run):
        env = {**self.env, "INPUT_INSTANCE_MAPPING": "not json"}
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaisesRegex(ValueError, "valid JSON"):
                main()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
