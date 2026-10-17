"""Offline fail-closed launch and correlated-receipt regressions."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docker_codex_cli as cell


class Safeguards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "runtime"
        self.output.mkdir()
        args = cell.launch_args(cell.PYTHON, self.output, cell.OWNER)
        self.info = {
            "Image": cell.PYTHON,
            "Config": {"Labels": {cell.LABEL: cell.OWNER}, "User": "65532:65532",
                       "Entrypoint": ["/usr/bin/env"], "Cmd": args[args.index(cell.PYTHON) + 1:]},
            "Mounts": [{"Type": "bind", "Destination": "/out"}],
            "HostConfig": {
                "NetworkMode": "none", "ReadonlyRootfs": True, "Privileged": False,
                "CapAdd": None, "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges"],
                "PidsLimit": 128, "Memory": 1073741824, "MemorySwap": 1073741824,
                "NanoCpus": 2000000000, "PidMode": "", "IpcMode": "private",
                "Tmpfs": {"/tmp": "rw,nosuid,nodev,size=512m,mode=1777"},
                "Mounts": [{"Type": "bind", "Source": str(self.output.resolve()), "Target": "/out"}],
            },
        }

    def test_safe_launch(self):
        self.assertTrue(all(cell.validate_container(self.info, cell.PYTHON, self.output).values()))

    def test_weakened_boundaries_rejected(self):
        mutations = {
            "NetworkMode": "host", "ReadonlyRootfs": False, "Privileged": True,
            "CapAdd": ["SYS_ADMIN"], "CapDrop": [], "SecurityOpt": [],
            "PidsLimit": 0, "Memory": 0, "MemorySwap": -1, "NanoCpus": 0,
            "PidMode": "host", "IpcMode": "host", "Devices": [{"PathOnHost": "/dev/x"}],
            "DeviceRequests": [{}], "Binds": ["/home:/home"], "VolumesFrom": ["other"],
            "Tmpfs": {"/": "rw"}, "Mounts": [], "PortBindings": {"80/tcp": [{}]},
        }
        for key, value in mutations.items():
            with self.subTest(key=key):
                info = copy.deepcopy(self.info)
                info["HostConfig"][key] = value
                with self.assertRaises(ValueError):
                    cell.validate_container(info, cell.PYTHON, self.output)

    def test_host_profile_socket_or_extra_volume_rejected(self):
        for target in ("/home", "/root", "/var/run/docker.sock", "/out"):
            info = copy.deepcopy(self.info)
            info["HostConfig"]["Mounts"].append(
                {"Type": "bind", "Source": "C:\\Users\\real", "Target": target})
            with self.assertRaises(ValueError):
                cell.validate_container(info, cell.PYTHON, self.output)
        self.info["Mounts"].append({"Type": "volume", "Destination": "/hidden"})
        with self.assertRaises(ValueError):
            cell.validate_container(self.info, cell.PYTHON, self.output)

    def test_root_or_changed_command_rejected(self):
        for field, value in (("User", "0"), ("Labels", {}), ("Cmd", ["sh"]),
                             ("Entrypoint", ["/bin/sh"])):
            info = copy.deepcopy(self.info)
            info["Config"][field] = value
            with self.assertRaises(ValueError):
                cell.validate_container(info, cell.PYTHON, self.output)

    def test_mutable_image_rejected(self):
        for image in ("python:3.12-slim", cell.PYTHON[:20], ""):
            with self.assertRaises(ValueError):
                cell.launch_args(image, self.output, cell.OWNER)
        self.info["Image"] = cell.NODE
        with self.assertRaises(ValueError):
            cell.validate_container(self.info, cell.PYTHON, self.output)

    def test_output_escape_rejected(self):
        repo = Path(self.temp.name)
        self.assertEqual(cell.owned_output(repo / "evidence" / cell.OWNER, repo),
                         repo.resolve() / "evidence" / cell.OWNER)
        for path in (repo, repo / "other", repo / "evidence" / cell.OWNER / ".."):
            with self.assertRaises(ValueError):
                cell.owned_output(path, repo)

    def test_no_credential_or_proxy_inheritance(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "private", "GH_TOKEN": "private",
                                     "HTTP_PROXY": "private", "DOCKER_AUTH_CONFIG": "private",
                                     "DOCKER_HOST": "private", "NODE_OPTIONS": "private"}):
            env = cell.docker_environment(self.output)
        self.assertNotIn("private", env.values())
        self.assertEqual(set(env) - {"PATH", "SystemRoot", "WINDIR", "COMSPEC"},
                         {"DOCKER_CONFIG", "DOCKER_BUILDKIT"})

    def test_build_only_declared_pinned_sources(self):
        text = cell.dockerfile("local-python")
        self.assertIn(f"Codex CLI {cell.VERSION}", text)
        self.assertTrue(text.splitlines()[1].startswith(f"LABEL {cell.LABEL}="))
        self.assertIn("--no-deps --only-binary=:all:", text)
        self.assertNotIn("apt", text)
        self.assertNotIn("curl", text)
        self.assertNotIn("latest", text)
        self.assertNotIn("npm", text)

    def test_unverified_archive_is_not_extracted(self):
        archive = Path(self.temp.name) / "bad.tar.gz"
        archive.write_bytes(b"not the official archive")
        with self.assertRaises(ValueError):
            cell.extract_codex(archive, self.output / "codex")
        self.assertFalse((self.output / "codex").exists())

    def test_cleanup_refuses_unlabelled_tagged_or_changed_image(self):
        info = {"Id": cell.PYTHON, "Config": {"Labels": {cell.LABEL: cell.OWNER}},
                "RepoTags": []}
        cell.owned_image(info, cell.PYTHON)
        for field, value in (("Id", cell.NODE), ("Config", {"Labels": {}}),
                             ("Config", {"Labels": None}),
                             ("RepoTags", ["unrelated:latest"])):
            broken = copy.deepcopy(info)
            broken[field] = value
            with self.assertRaises(ValueError):
                cell.owned_image(broken, cell.PYTHON)

    def test_correlated_exact_recovery_not_matching_schema_or_wrong_call(self):
        action = {"name": "brainspace_retrieve", "arguments": {"ref": "abc"}, "call_id": "c1"}
        responses = [{"events": [["response.completed", {"response": {"output": [
            {"type": "function_call", **action, "arguments": json.dumps(action["arguments"])}]}}]]}]
        page = {"ok": True, "complete": True, "content": "original"}
        result = {"type": "function_call_output", "call_id": "c1", "output": json.dumps(page)}
        requests = [{"body": {}}, {"body": {"input": [result]}}]
        self.assertTrue(cell.correlate(requests, responses, [action], "original"))
        self.assertFalse(cell.correlate(requests, responses, [action], "wrong"))
        for field, value in (("call_id", "other"), ("type", "message"), ("output", "{}")):
            broken = copy.deepcopy(requests)
            broken[1]["body"]["input"][0][field] = value
            self.assertFalse(cell.correlate(broken, responses, [action], "original"))
        self.assertFalse(cell.correlate(list(reversed(requests)), responses, [action], "original"))
        self.assertFalse(cell.correlate(requests, [], [action], "original"))
        self.assertFalse(cell.correlate(requests, responses, [action, action], "original"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
