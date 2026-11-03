import json
import subprocess
import unittest
from unittest.mock import Mock, call, patch

from gha_runner.clouddeployment import TeardownInstance
from gha_runner.gh import MissingRunnerLabel
from stop_brev_gha_runner.__main__ import main
from stop_brev_gha_runner.stop import (
    StopBrev,
    parse_instance_mapping,
    parse_timeout,
)


class FakeClock:
    """Deterministic stand-in for the ``time`` module used by the waiter."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


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


class TimeoutTests(unittest.TestCase):
    def setUp(self):
        self.mapping = {"runner-one": "runner-one"}
        self.brev = StopBrev(instance_mapping=self.mapping)
        self.workspaces = json.dumps({"workspaces": [{"name": "runner-one"}]})

    def test_absent_or_empty_input_uses_ten_minutes(self):
        self.assertEqual(self.brev.timeout, 600)
        for value in [None, "", "   "]:
            with self.subTest(value=value):
                self.assertEqual(parse_timeout(value), 600)

    def test_parses_positive_integer_input(self):
        self.assertEqual(parse_timeout("900"), 900)
        self.assertEqual(parse_timeout(" 45 "), 45)

    def test_rejects_non_positive_or_non_integer_input(self):
        invalid = ["0", "-1", "abc", "600.0", "6 0", "1e3", "null", "²"]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "positive integer"):
                    parse_timeout(value)

    @patch("stop_brev_gha_runner.stop.subprocess.run")
    def test_default_timeout_is_honored(self, run):
        clock = FakeClock()
        run.return_value = subprocess.CompletedProcess(
            ["brev", "ls", "--json"], 0, stdout=self.workspaces
        )

        with patch("stop_brev_gha_runner.stop.time", clock):
            with self.assertRaisesRegex(TimeoutError, "runner-one"):
                self.brev.wait_until_removed(["runner-one"])

        # 600 seconds of waiting, polling every 5 seconds by default.
        self.assertEqual(clock.sleeps, [5] * 120)
        self.assertEqual(clock.now, 600)

    @patch("stop_brev_gha_runner.stop.subprocess.run")
    def test_configured_timeout_is_honored(self, run):
        clock = FakeClock()
        run.return_value = subprocess.CompletedProcess(
            ["brev", "ls", "--json"], 0, stdout=self.workspaces
        )
        brev = StopBrev(instance_mapping=self.mapping, timeout=20)

        with patch("stop_brev_gha_runner.stop.time", clock):
            with self.assertRaisesRegex(TimeoutError, "runner-one"):
                brev.wait_until_removed(["runner-one"])

        self.assertEqual(clock.sleeps, [5] * 4)
        self.assertEqual(clock.now, 20)

    @patch("stop_brev_gha_runner.stop.subprocess.run")
    def test_kwargs_override_configured_timeout(self, run):
        clock = FakeClock()
        run.return_value = subprocess.CompletedProcess(
            ["brev", "ls", "--json"], 0, stdout=self.workspaces
        )
        brev = StopBrev(instance_mapping=self.mapping, timeout=600)

        with patch("stop_brev_gha_runner.stop.time", clock):
            with self.assertRaisesRegex(TimeoutError, "runner-one"):
                brev.wait_until_removed(["runner-one"], timeout=10, interval=2)

        self.assertEqual(clock.sleeps, [2] * 5)
        self.assertEqual(clock.now, 10)

    @patch("stop_brev_gha_runner.stop.subprocess.run")
    def test_returns_early_when_instance_disappears(self, run):
        clock = FakeClock()
        run.return_value = subprocess.CompletedProcess(
            ["brev", "ls", "--json"], 0, stdout='{"workspaces": []}'
        )
        brev = StopBrev(instance_mapping=self.mapping, timeout=600)

        with patch("stop_brev_gha_runner.stop.time", clock):
            brev.wait_until_removed(["runner-one"])

        self.assertEqual(clock.sleeps, [])

    @patch("stop_brev_gha_runner.stop.subprocess.run")
    def test_teardown_lifecycle_honors_configured_timeout(self, run):
        run.return_value = subprocess.CompletedProcess(
            ["brev", "ls", "--json"], 0, stdout=self.workspaces
        )
        clock = FakeClock()
        deployment = TeardownInstance(
            provider_type=StopBrev,
            cloud_params={"instance_mapping": self.mapping, "timeout": 20},
            gh=Mock(),
        )

        with patch("stop_brev_gha_runner.stop.time", clock):
            with self.assertRaises(SystemExit):
                deployment.stop_runner_instances()

        # The provider timeout reached gha_runner's kwargs-free call.
        self.assertEqual(clock.sleeps, [5] * 4)
        self.assertEqual(clock.now, 20)
        self.assertEqual(
            run.call_args_list,
            [call(["brev", "delete", "runner-one"], check=True)]
            + [
                call(
                    ["brev", "ls", "--json"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            ]
            * 5,
        )


class MainTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "BREV_API_KEY": "brev-api-key",
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
            ["brev", "login", "--api-key", "brev-api-key"], check=True
        )
        github.assert_called_once_with(token="gh-token", repo="owner/repo")
        teardown.assert_called_once_with(
            provider_type=StopBrev,
            cloud_params={
                "instance_mapping": {"brev-name": "runner-label"},
                "timeout": 600,
            },
            gh=github.return_value,
        )
        teardown.return_value.stop_runner_instances.assert_called_once_with()

    @patch("stop_brev_gha_runner.__main__.TeardownInstance")
    @patch("stop_brev_gha_runner.__main__.GitHubInstance")
    @patch("stop_brev_gha_runner.__main__.subprocess.run")
    def test_passes_configured_timeout_to_provider(self, run, github, teardown):
        env = {**self.env, "INPUT_TIMEOUT": "900"}
        with patch.dict("os.environ", env, clear=True):
            main()

        self.assertEqual(
            teardown.call_args.kwargs["cloud_params"]["timeout"], 900
        )

    @patch("stop_brev_gha_runner.__main__.TeardownInstance")
    @patch("stop_brev_gha_runner.__main__.GitHubInstance")
    @patch("stop_brev_gha_runner.__main__.subprocess.run")
    def test_empty_timeout_falls_back_to_default(self, run, github, teardown):
        env = {**self.env, "INPUT_TIMEOUT": ""}
        with patch.dict("os.environ", env, clear=True):
            main()

        self.assertEqual(
            teardown.call_args.kwargs["cloud_params"]["timeout"], 600
        )

    @patch("stop_brev_gha_runner.__main__.subprocess.run")
    def test_rejects_invalid_timeout_before_login(self, run):
        for value in ["abc", "0", "-30", "10.5"]:
            with self.subTest(value=value):
                env = {**self.env, "INPUT_TIMEOUT": value}
                with patch.dict("os.environ", env, clear=True):
                    with self.assertRaisesRegex(ValueError, "positive integer"):
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

        github.return_value.remove_runner.assert_called_once_with(
            "runner-label"
        )
        self.assertEqual(
            run.call_args_list,
            [
                call(
                    ["brev", "login", "--api-key", "brev-api-key"], check=True
                ),
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
