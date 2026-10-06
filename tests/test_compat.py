"""CLI regression tests; no container service or third-party modules required."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.calls_path = self.directory / "calls.jsonl"
        self.backend = self.directory / "container"
        self.backend.write_text(
            "#!" + sys.executable + "\n"
            "import json, os, sys\n"
            "args = sys.argv[1:]\n"
            "with open(os.environ['SHIM_TEST_CALLS'], 'a') as f:\n"
            "    f.write(json.dumps(args) + '\\n')\n"
            "if args and args[0] == 'start' and '__fail__' in args:\n"
            "    sys.exit(7)\n"
            "print('[]' if args and args[0] == 'list' else json.dumps(args))\n"
        )
        self.backend.chmod(0o755)
        self.env = dict(os.environ, DOCKER_SHIM_CONTAINER_BIN=str(self.backend),
                        SHIM_TEST_CALLS=str(self.calls_path),
                        DOCKER_SHIM_DEBUG="0", DOCKER_SHIM_STRICT="1",
                        DOCKER_SHIM_REGISTRY_SCHEME="")

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "bin/docker"), *args],
                              env=self.env, capture_output=True, text=True)

    def calls(self):
        if not self.calls_path.exists():
            return []
        return [json.loads(line) for line in self.calls_path.read_text().splitlines()]

    def compose(self, config, *args):
        path = self.directory / "compose.yaml"
        path.write_text(json.dumps({"name": "shim-test", "services": {
            "app": {"image": "redis:7-alpine", **config}}}))
        return self.cli("compose", "-f", str(path), *args)

    def last_run(self):
        return [call for call in self.calls() if call[0] in ("run", "create")][-1]

    def test_start_multiple_containers_separately(self):
        result = self.cli("start", "first", "second")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [["start", "first"], ["start", "second"]])

    def test_start_continues_after_failure_and_keeps_failure_code(self):
        result = self.cli("container", "start", "__fail__", "second")
        self.assertEqual(result.returncode, 7)
        self.assertEqual(self.calls(), [["start", "__fail__"], ["start", "second"]])

    def test_start_multiple_keeps_global_debug(self):
        result = self.cli("--debug", "start", "first", "second")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [["--debug", "start", "first"],
                                       ["--debug", "start", "second"]])

    def test_start_multiple_rejects_attached_modes_before_starting(self):
        for option in ("--attach", "--interactive", "-ai"):
            with self.subTest(option=option):
                result = self.cli("start", option, "first", "second")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.calls(), [])

    def test_start_requires_a_container(self):
        result = self.cli("start")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_start_help_does_not_require_a_container(self):
        result = self.cli("start", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [["start", "--help"]])

    def test_single_start_preserves_attach(self):
        result = self.cli("start", "-ai", "first")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [["start", "--attach", "--interactive", "first"]])

    def test_run_and_create_clear_entrypoint_without_a_shell(self):
        for command in ("run", "create"):
            with self.subTest(command=command):
                result = self.cli(command, "--entrypoint", "", "redis:7-alpine",
                                  "echo", "hello world", "$(literal)", "--flag")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.last_run(), [command, "--entrypoint", "echo",
                    "redis:7-alpine", "hello world", "$(literal)", "--flag"])

    def test_empty_entrypoint_requires_explicit_command(self):
        for command in ("run", "create"):
            with self.subTest(command=command):
                result = self.cli(command, "--entrypoint=", "redis:7-alpine")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("explicit command", result.stderr)
                self.assertEqual(self.calls(), [])

    def test_empty_executable_is_rejected(self):
        result = self.cli("run", "--entrypoint=", "redis:7-alpine", "")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_argument_separator_still_clears_entrypoint(self):
        result = self.cli("run", "--entrypoint=", "--", "redis:7-alpine", "echo", "ok")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.last_run(), ["run", "--entrypoint", "echo",
                                          "redis:7-alpine", "ok"])

    def test_help_named_flag_value_does_not_skip_command_validation(self):
        result = self.cli("run", "--workdir", "--help", "--entrypoint=", "redis:7-alpine")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("explicit command", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_run_help_can_clear_entrypoint_without_command(self):
        result = self.cli("run", "--help", "--entrypoint=", "redis:7-alpine")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_nonempty_entrypoint_and_argv_are_unchanged(self):
        result = self.cli("run", "--entrypoint", "echo", "redis:7-alpine", "hello world")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.last_run(), ["run", "--entrypoint", "echo",
                                          "redis:7-alpine", "hello world"])

    def test_empty_entrypoint_preserves_flag_values_named_entrypoint(self):
        result = self.cli("run", "--workdir", "--entrypoint", "--entrypoint=",
                          "redis:7-alpine", "echo", "ok")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.last_run(), ["run", "--workdir", "--entrypoint",
                                          "--entrypoint", "echo", "redis:7-alpine", "ok"])

    def test_compose_up_clears_entrypoint(self):
        for entrypoint in ([], ""):
            with self.subTest(entrypoint=entrypoint):
                result = self.compose({"entrypoint": entrypoint,
                                       "command": ["echo", "hello world"]}, "up", "-d")
                self.assertEqual(result.returncode, 0, result.stderr)
                call = self.last_run()
                self.assertEqual(call[call.index("--entrypoint") + 1], "echo")
                self.assertEqual(call[-2:], ["redis:7-alpine", "hello world"])

    def test_compose_oneoff_command_override_clears_entrypoint(self):
        for mode in ([], ["-d"]):
            with self.subTest(mode=mode):
                result = self.compose({"entrypoint": [], "command": ["old", "arg"]},
                                      "run", *mode, "app", "echo", "new argument")
                self.assertEqual(result.returncode, 0, result.stderr)
                call = self.last_run()
                self.assertEqual(call[call.index("--entrypoint") + 1], "echo")
                self.assertEqual(call[-2:], ["redis:7-alpine", "new argument"])
                self.assertNotIn("old", call)

    def test_compose_cli_entrypoint_override_wins(self):
        result = self.compose({"entrypoint": ["old"], "command": ["old argument"]},
                              "run", "--entrypoint", "", "app", "echo", "ok")
        self.assertEqual(result.returncode, 0, result.stderr)
        call = self.last_run()
        self.assertEqual(call.count("--entrypoint"), 1)
        self.assertEqual(call[call.index("--entrypoint") + 1], "echo")
        self.assertEqual(call[-2:], ["redis:7-alpine", "ok"])

    def test_compose_empty_entrypoint_without_command_fails(self):
        result = self.compose({"entrypoint": []}, "run", "app")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("explicit command", result.stderr)
        self.assertEqual([c for c in self.calls() if c[0] == "run"], [])

    def test_compose_entrypoint_override_discards_old_entrypoint_arguments(self):
        for mode in ([], ["-d"]):
            with self.subTest(mode=mode):
                result = self.compose({"entrypoint": ["old", "old-entrypoint-argument"],
                                       "command": ["echo", "ok"]},
                                      "run", *mode, "--entrypoint", "", "app")
                self.assertEqual(result.returncode, 0, result.stderr)
                call = self.last_run()
                self.assertEqual(call[call.index("--entrypoint") + 1], "echo")
                self.assertEqual(call[-2:], ["redis:7-alpine", "ok"])
                self.assertNotIn("old-entrypoint-argument", call)

    def test_compose_old_entrypoint_arguments_are_not_an_explicit_command(self):
        for mode in ([], ["-d"]):
            with self.subTest(mode=mode):
                result = self.compose({"entrypoint": ["old", "old-entrypoint-argument"]},
                                      "run", *mode, "--entrypoint", "", "app")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("explicit command", result.stderr)
                self.assertEqual([c for c in self.calls() if c[0] == "run"], [])

    def test_compose_command_override_keeps_entrypoint_arguments(self):
        result = self.compose({"entrypoint": ["sh", "-c"], "command": ["old"]},
                              "run", "app", "echo ok")
        self.assertEqual(result.returncode, 0, result.stderr)
        call = self.last_run()
        self.assertEqual(call[call.index("--entrypoint") + 1], "sh")
        self.assertEqual(call[-3:], ["redis:7-alpine", "-c", "echo ok"])

    def test_compose_cli_entrypoint_is_a_single_executable_value(self):
        for mode in ([], ["-d"]):
            with self.subTest(mode=mode):
                result = self.compose({"entrypoint": ["old", "old argument"]},
                                      "run", *mode, "--entrypoint",
                                      "/path with spaces/tool", "app", "argument")
                self.assertEqual(result.returncode, 0, result.stderr)
                call = self.last_run()
                self.assertEqual(call[call.index("--entrypoint") + 1], "/path with spaces/tool")
                self.assertEqual(call[-2:], ["redis:7-alpine", "argument"])
                self.assertNotIn("with", call)
                self.assertNotIn("spaces/tool", call)


if __name__ == "__main__":
    unittest.main()
