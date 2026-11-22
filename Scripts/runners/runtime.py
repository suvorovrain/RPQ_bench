"""Shared process management, answer validation and result storage."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
from datetime import datetime, timezone

from .config import ROOT


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


class Benchmark:
    def __init__(self, selection, data, graph, manifest, folder, args, runtime, lock):
        self.engine = selection.engine
        self.options = selection.options
        self.queries = selection.queries
        self.data = data
        self.graph = graph
        self.manifest = manifest
        self.folder = folder
        self.query_dir = folder / "queries"
        self.args = args
        self.runtime = runtime
        self.lock = lock
        self.threads = args.threads
        self.container = None
        self.log = (folder / "run.log").open("w")
        self.result = {
            "engine": self.engine, "started": now(), "runs": args.runs,
            "warmups": args.warmups, "query_ids": [q["id"] for q in self.queries],
            "options": self.options, "commands": [], "checks": [], "measurements": {},
        }

    def run(self, args, timeout=None, input=None, cwd=ROOT):
        command = list(map(str, args))
        self.result["commands"].append({"argv": command, "cwd": str(cwd)})
        print("$", shlex.join(command), file=self.log, flush=True)
        env = {**os.environ, "OMP_NUM_THREADS": str(self.threads),
               "OMP_DYNAMIC": "FALSE", "OMP_PROC_BIND": "FALSE"}
        completed = subprocess.run(command, cwd=cwd, env=env, input=input,
                                   text=True, capture_output=True, timeout=timeout or self.args.timeout_s)
        self.log.write(completed.stdout + completed.stderr)
        self.log.flush()
        if completed.returncode:
            raise RuntimeError(f"{command[0]} exited with {completed.returncode}: {completed.stderr[-600:]}")
        return completed.stdout

    def docker(self, image, extra=(), command=()):
        name = f"rpq-bench-{self.engine}-{secrets.token_hex(4)}"
        image = self.lock["images"][image]
        self.run(["docker", "run", "-d", "--name", name, "--label", "rpq-bench.run=true",
                  *self.docker_limits(), "-v", f"{self.data}:/input:ro", *extra, image, *command])
        self.container = name
        self.result["image"] = image

    def docker_limits(self):
        limits = []
        if not self.args.all_cpus:
            limits += ["--cpus", str(self.threads)]
        if self.args.docker_memory:
            limits += ["--memory", self.args.docker_memory]
        return limits

    def add(self, q, samples, scope, verification="count_only", extra=None, *, phases=None):
        for name, series in {scope: samples, **(phases or {})}.items():
            require(len(series) == self.args.runs and all(0 <= x < float("inf") for x in series),
                    f"Invalid {name} timings for {self.engine}/{q['id']}")
        require(q["id"] not in self.result["measurements"], f"Duplicate measurements for {q['id']}")
        self.result["measurements"][q["id"]] = {
            "id": q["id"], "pattern": q["pattern"], "expected_count": q["count"],
            "samples_ms": samples, "scope": scope, "verification": verification,
            "phase_samples_ms": phases or {},
            "count_metric": q.get("count_metric", "reachable_targets"),
            "status": "pass", **(extra or {}),
        }

    def check(self, q, targets=None, count=None, note=None):
        correct = set(targets) == set(q["targets"]) if targets is not None else count == q["count"]
        self.result["checks"].append({"id": q["id"], "status": "pass" if correct else "mismatch", "note": note})
        require(correct, f"Wrong answer for {self.engine}/{q['id']}")

    def skip(self, q, reason):
        self.result["checks"].append({"id": q["id"], "status": "unsupported", "note": reason})

    def finish(self):
        if self.container:
            for command in (["docker", "logs", self.container], ["docker", "stop", "-t", "5", self.container],
                            ["docker", "rm", self.container]):
                try:
                    subprocess.run(command, stdout=self.log, stderr=self.log, timeout=30, check=False)
                except (OSError, subprocess.TimeoutExpired) as error:
                    print(error, file=self.log)
        self.result["executables_sha256"] = {}
        for command in self.result["commands"]:
            binary = Path(command["argv"][0])
            if binary.is_absolute() and binary.is_file() and str(binary) not in self.result["executables_sha256"]:
                with binary.open("rb") as stream:
                    self.result["executables_sha256"][str(binary)] = hashlib.file_digest(stream, "sha256").hexdigest()
        self.result["finished"] = now()
        self.log.close()
        (self.folder / "result.json").write_text(json.dumps(self.result, indent=2) + "\n")


def java_command(s, command, timeout=None, input=None):
    return s.run(["docker", "run", "--rm", "-i", *s.docker_limits(),
                  "-v", f"{ROOT}:/work", "-v", f"{s.runtime}/tools:/tools:ro",
                  "-v", f"{s.data}:/input:ro", "-v", f"{s.graph}:/graph:ro",
                  "-w", "/work", s.lock["images"]["eclipse-temurin:21-jdk"], *command],
                 timeout=timeout, input=input)
