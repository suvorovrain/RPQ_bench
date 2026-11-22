from ..http import iri_ids
from ..runtime import require
import csv
import io
import re
import subprocess
import time
import urllib.request

QUERY_LOG = re.compile(
    r"^Query\(worker (\d+), cancel ([\w-]+)\)\n(.*?)\n\nWorker \1 results: (\d+)\n"
    r"Parser\s*: (\S+) ms\nOptimizer\s*: (\S+) ms\nExecution\s*: (\S+) ms$",
    re.MULTILINE | re.DOTALL,
)


def collect_timings(s, path, requests):
    log = path.read_text()
    entries = list(QUERY_LOG.findall(log))
    require(len(entries) == len(requests) + 1 and entries[0][2] == "ASK {}",
            "MillenniumDB log does not match readiness and query requests")
    require(len({entry[1] for entry in entries}) == len(entries), "Duplicate MillenniumDB cancellation token")
    times = {q["id"]: {"parser": [], "optimizer": [], "execution": []} for q in s.queries}
    for request, entry in zip(requests, entries[1:]):
        q, iteration, row_count = request
        _, _, query, count, parser, optimizer, execution = entry
        require(query == q["sparql"].rstrip("\n") and int(count) == row_count,
                f"MillenniumDB query log mismatch for {q['id']} at iteration {iteration}")
        if iteration >= 0:
            for phase, value in zip(("parser", "optimizer", "execution"), (parser, optimizer, execution)):
                times[q["id"]][phase].append(float(value))
    for q in s.queries:
        phases = times[q["id"]]
        s.add(q, phases["execution"], "millenniumdb_execution", "endpoint_set_every_run",
              phases={name: phases[name] for name in ("parser", "optimizer")})


def run(s):
    exe = s.runtime / "build/millenniumdb/bin/mdb"
    state = s.folder / f"millenniumdb-db-{time.time_ns()}"
    s.result["version"] = s.run([exe, "--help"]).splitlines()[0]
    s.run([exe, "import", s.data / "rdf/graph.nt", state, "--buffer-strings", "256MB", "--buffer-tensors", "256MB"])
    log_path = s.folder / "server.log"
    log = log_path.open("w")
    requests = []
    args = list(map(str, [exe, "server", state, "--port", "12345", "--browser", "false", "--threads", s.threads,
                         "--strings-dynamic", "64MB", "--strings-static", "64MB", "--tensors-dynamic", "64MB",
                         "--tensors-static", "64MB", "--private-buffer", "64MB", "--versioned-buffer", "64MB"]))
    s.result["commands"].append({"argv": args, "cwd": str(s.folder)})
    process = subprocess.Popen(args, cwd=s.folder, stdout=log, stderr=log)
    try:
        url = "http://127.0.0.1:12345/sparql"
        for attempt in range(40):
            try:
                request = urllib.request.Request(url, data=b"ASK {}", headers={"Content-Type":"application/sparql-query", "Accept":"text/csv"})
                with urllib.request.urlopen(request, timeout=3) as response:
                    response.read()
                break
            except Exception:
                if attempt == 39:
                    raise
                time.sleep(1)
        ids = iri_ids(s)
        for q in s.queries:
            request = urllib.request.Request(url, data=q["sparql"].encode(), headers={"Content-Type":"application/sparql-query", "Accept":"text/csv"})
            for iteration in range(-s.args.warmups, s.args.runs):
                with urllib.request.urlopen(request, timeout=60) as response:
                    output = response.read().decode()
                rows = list(csv.reader(io.StringIO(output)))
                require(rows and rows[0] in (["t"], ["?t"]), f"Unexpected MillenniumDB CSV header for {q['id']}")
                values = [ids[row[0].strip("<>")] for row in rows[1:] if row]
                s.check(q, values)
                requests.append((q, iteration, len(values)))
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        finally:
            log.close()
    collect_timings(s, log_path, requests)


if __name__ == "__main__":
    from ..workflow import main

    main(default_engine='millenniumdb')
