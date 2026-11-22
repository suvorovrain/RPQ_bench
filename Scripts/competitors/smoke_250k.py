#!/usr/bin/env python3
"""Import the prepared graph and check smoke endpoints; not a timing benchmark."""
import argparse
import csv
import io
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "Datasets/rpqbench_250k/prepared"
OUT = ROOT / "Results/competitors_250k"
MANIFEST = {}
QUERIES = []
QUERY_DIR = DATA / "queries"
SUFFIX = ""
PATHREX_OPTIMIZERS = ("none", "pang-hybrid")


def load_inputs():
    """Read prepared data after CLI parsing, so --help works on a fresh clone."""
    global MANIFEST, QUERIES
    path = DATA / "manifest.json"
    if not path.is_file():
        raise ValueError(f"Missing {path}; run prepare_250k.py --bootstrap-mm first")
    MANIFEST = json.loads(path.read_text())
    QUERIES = MANIFEST["queries"]


def validate_checks(engine, checks):
    expected = {(q["id"], f"optimizer={opt}") for q in QUERIES for opt in PATHREX_OPTIMIZERS} if engine == "pathrex" else {(q["id"], None) for q in QUERIES}
    actual = [(c["id"], c.get("note") if engine == "pathrex" else None) for c in checks]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError(f"Incomplete/duplicate query records: expected {sorted(expected)}, got {actual}")


class Smoke:
    def __init__(self, engine, report_dir=OUT):
        self.engine = engine
        self.report_dir = report_dir
        self.result = dict(engine=engine, started=time.strftime("%Y-%m-%dT%H:%M:%S%z"), checks=[], commands=[])
        self.container = None
        (report_dir / "logs").mkdir(parents=True, exist_ok=True)
        self.log = (report_dir / "logs" / f"{engine}{SUFFIX}-smoke.log").open("w")

    def query(self, query, execute):
        """One execution; the benchmark runner overrides this with repetitions."""
        return execute()

    def run(self, args, timeout=120, input=None, cwd=ROOT):
        args = list(map(str, args))
        self.result["commands"].append(args)
        self.log.write("$ " + repr(args) + "\n")
        self.log.flush()
        r = subprocess.run(args, input=input, text=True, capture_output=True, cwd=cwd,
                           timeout=timeout, env={**os.environ, "OMP_NUM_THREADS": "2"})
        self.log.write(r.stdout + r.stderr)
        self.log.flush()
        if r.returncode:
            raise RuntimeError(f"exit {r.returncode}: {args[:4]}: {r.stderr[-1000:]}")
        return r.stdout

    def check(self, query, targets=None, count=None, note=None):
        expected = query["targets"]
        actual = sorted(set(targets)) if targets is not None else None
        ok = actual == expected if actual is not None else count == len(expected)
        self.result["checks"].append(dict(id=query["id"], expected=len(expected),
                                         actual=len(actual) if actual is not None else count,
                                         verification="endpoint_set" if actual is not None else "count_only",
                                         status="pass" if ok else "mismatch", note=note))
        if actual is not None and not ok:
            self.result["checks"][-1]["missing"] = sorted(set(expected)-set(actual))[:20]
            self.result["checks"][-1]["extra"] = sorted(set(actual)-set(expected))[:20]

    def skip(self, query, why, status="no_translation"):
        self.result["checks"].append(dict(id=query["id"], status=status, note=why))

    def docker(self, image, extra=(), command=()):
        name = f"rpq-bench-250k-{self.engine}"
        lock = ROOT / "Databases/guides/runtime-lock.json"
        if lock.exists():
            image = json.loads(lock.read_text())["images"].get(image, image)
        existing = subprocess.run(["docker", "inspect", name], capture_output=True, text=True)
        if existing.returncode == 0:
            info = json.loads(existing.stdout)[0]
            if info["Config"].get("Labels", {}).get("rpq-bench.smoke") != "250k" or info["State"]["Running"]:
                raise RuntimeError(f"Container {name} exists and is not our stopped smoke container")
            # Only our stopped test container; keep any volumes and host data.
            self.run(["docker", "rm", name])
        self.run(["docker", "run", "-d", "--name", name, "--label", "rpq-bench.smoke=250k",
                  "--memory", "2g", "--cpus", "2", "-v", f"{DATA}:/input:ro", *extra, image, *command])
        self.container = name
        self.result["image"] = json.loads(self.run(["docker", "image", "inspect", image]))[0]["RepoDigests"]
        return name

    def finish(self):
        if self.container:
            state = subprocess.run(["docker", "inspect", self.container], capture_output=True, text=True)
            if state.returncode == 0:
                self.result["container_state_before_stop"] = json.loads(state.stdout)[0]["State"]
            subprocess.run(["docker", "logs", self.container], stdout=self.log, stderr=self.log)
            subprocess.run(["docker", "stop", "-t", "5", self.container], stdout=self.log, stderr=self.log)
        self.log.close()
        (self.report_dir / f"{self.engine}{SUFFIX}.json").write_text(json.dumps(self.result, indent=2)+"\n")
        print(self.engine, self.result.get("status"), self.result.get("error", ""), flush=True)


def duckdb(s):
    import duckdb
    s.result["version"] = duckdb.__version__
    con = duckdb.connect(str(OUT / "duckdb.duckdb"))
    con.execute("SET threads=2")
    con.execute(f"CREATE OR REPLACE TABLE edges AS SELECT * FROM read_csv('{DATA}/csv/edges.csv')")
    if con.execute("SELECT count(*) FROM edges").fetchone()[0] != MANIFEST["edges"]:
        raise ValueError("DuckDB imported edge count differs from manifest")
    for q in QUERIES:
        text = (QUERY_DIR / f'q{q["id"]}.sql').read_text()
        s.check(q, s.query(q, lambda: [r[0] for r in con.execute(text).fetchall()]))
    con.close()


def postgres(s):
    import psycopg
    image = "postgres:18"
    port = 15542
    extra = ["-p", f"127.0.0.1:{port}:5432"]
    extra += ["-e", "POSTGRES_PASSWORD=rpq-smoke-local", "-e", "POSTGRES_DB=rpq"]
    name = s.docker(image, extra)
    con = None
    for _ in range(50):
        try:
            con = psycopg.connect(host="127.0.0.1", port=port, user="postgres",
                                 password="rpq-smoke-local",
                                 dbname="rpq", connect_timeout=2, autocommit=True)
            break
        except Exception:
            time.sleep(1)
    if con is None:
        raise RuntimeError("PostgreSQL wire endpoint did not become ready")
    with con:
        s.result["version"] = con.execute("SELECT version()").fetchone()[0]
        con.execute("CREATE TABLE edges(src BIGINT, pid INTEGER, dst BIGINT)")
        # Server-side COPY reads the mounted CSV file.
        con.execute("COPY edges FROM '/input/csv/edges.csv' WITH (FORMAT CSV, HEADER TRUE)")
        con.execute("CREATE INDEX edges_src_pid ON edges(src,pid)")
        con.execute("CREATE INDEX edges_dst_pid ON edges(dst,pid)")
        con.execute("ANALYZE edges")
        if con.execute("SELECT count(*) FROM edges").fetchone()[0] != MANIFEST["edges"]:
            raise ValueError("PostgreSQL imported edge count differs from manifest")
        for q in QUERIES:
            text = (QUERY_DIR / f'q{q["id"]}.sql').read_text()
            s.check(q, s.query(q, lambda: [r[0] for r in con.execute(text).fetchall()]))


def native(s):
    if s.engine == "pathrex":
        exe = ROOT / "Databases/pathrex/target/release/pathrex"
        s.result["source_sha"] = s.run(["git", "-C", ROOT / "Databases/pathrex", "rev-parse", "HEAD"]).strip()
        for optimizer in PATHREX_OPTIMIZERS:
            output = s.report_dir / f"pathrex-{optimizer}{SUFFIX}.json"
            s.run([exe, "query", "-g", DATA.parent / "pathrex", "-q", QUERY_DIR / "pathrex.txt",
                   "--base-iri", "http://example.org/", "-a", "rpqmatrix", "-p", optimizer, "-o", output])
            parsed = json.loads(output.read_text())
            s.result.setdefault("outputs", {})[optimizer] = parsed
            for entry in parsed["results"]:
                q = next(q for q in QUERIES if q["id"] == entry["query_id"])
                answer = entry["algorithms"]["rpqmatrix"]
                if answer["status"] != "ok":
                    error = answer.get("error", "unknown engine error")
                    status = "unsupported" if "not supported" in error else "query_error"
                    s.result["checks"].append(dict(id=q["id"], status=status, expected=q["count"],
                                                 note=f"optimizer={optimizer}", error=error))
                else:
                    s.check(q, count=answer.get("result_count"), note=f"optimizer={optimizer}")
        return
    gb = s.engine == "rpqmatrixGB"
    dataset = DATA / ("matrix-gb/graph.dat" if gb else "matrix/graph.dat")
    if gb:
        s.run([os.sys.executable, ROOT / "Scripts/converters/mm_to_rpq_GB.py", DATA.parent / "pathrex",
               "--output-base", dataset, "--copy"])
    else:
        pairs = OUT / "pairs"
        pairs.mkdir(exist_ok=True)
        s.run([ROOT / "Databases/rpq-matrix/build/create_pairs", dataset, len(MANIFEST["labels"]), MANIFEST["edges"]], cwd=pairs)
        index = Path(str(dataset)+".baseline-64")
        index.mkdir(exist_ok=True)
        s.run([ROOT / "Databases/rpq-matrix/build/baseline_build", str(pairs)+"/", index, MANIFEST["vertices"]])
    exe = ROOT / ("Databases/rpq-matrix_GB/build/baselineGB_query" if gb else "Databases/rpq-matrix/build/baseline_query")
    output = s.run([exe, dataset, QUERY_DIR / "matrix.tsv", len(MANIFEST["labels"]), MANIFEST["edges"], 1, 0])
    for line in output.splitlines():
        parts = line.split(";")
        if len(parts) == 3 and parts[0].isdigit():
            q = next(q for q in QUERIES if q["id"] == parts[0])
            s.check(q, count=int(parts[1]))


def cypher(q, mode="default"):
    source = q["source"]
    pattern = {"1": "[:creator]", "2": "[:references]->()-[:cite]->()-[:creator]",
               "3": "[:coauthor*0..]", "5": "[:editor|creator]", "6": "[:coauthor*0..1]"}.get(q["id"])
    if pattern is None:
        return None
    if mode == "memgraph" and q["id"] == "3":
        # BFS does not yield the zero-length source even with lower bound 0.
        return (f"MATCH (s:Node {{id:{source}}})-[:coauthor*BFS]->(t:Node) RETURN DISTINCT t.id AS id "
                f"UNION MATCH (s:Node {{id:{source}}}) RETURN s.id AS id")
    return f"MATCH (s:Node {{id:{source}}})-{pattern}->(t:Node) RETURN DISTINCT t.id AS id"


def kuzu(s):
    import kuzu
    s.result["version"] = kuzu.__version__
    db = kuzu.Database(str(OUT / f"kuzu-{time.time_ns()}"), buffer_pool_size=512*1024**2, max_num_threads=2)
    con = kuzu.Connection(db)
    con.execute("CREATE NODE TABLE Node(id INT64, name STRING, iri STRING, PRIMARY KEY(id))")
    con.execute(f"COPY Node FROM '{DATA}/csv/nodes.csv' (HEADER=true)")
    for label in MANIFEST["labels"].values():
        con.execute(f"CREATE REL TABLE {label}(FROM Node TO Node)")
        con.execute(f"COPY {label} FROM '{DATA}/csv/edges_{label}.csv' (HEADER=true)")
    for q in QUERIES:
        query = cypher(q)
        if query is None:
            s.skip(q, "Compound closure has no verified direct translation")
            continue
        try:
            def execute():
                r = con.execute(query)
                values = []
                while r.has_next():
                    values.append(r.get_next()[0])
                return values
            values = s.query(q, execute)
            s.check(q, values, note="Native pattern subset; default recursion cap applies")
        except Exception as e:
            s.result["checks"].append(dict(id=q["id"], status="query_error", error=str(e)))
    con.close()
    db.close()


def bolt(s):
    from neo4j import GraphDatabase
    memgraph = s.engine == "memgraph"
    image = "memgraph/memgraph:latest" if memgraph else "neo4j:5.26-community"
    port = 17688 if memgraph else 17687
    extra = ["-p", f"127.0.0.1:{port}:7687"]
    if not memgraph:
        extra += ["-e", "NEO4J_AUTH=none", "-e", "NEO4J_server_memory_heap_initial__size=256m",
                  "-e", "NEO4J_server_memory_heap_max__size=512m", "-e", "NEO4J_server_memory_pagecache_size=256m",
                  "-e", "NEO4J_server_directories_import=/input/csv"]
    s.docker(image, extra)
    driver = GraphDatabase.driver(f"bolt://127.0.0.1:{port}", auth=None, connection_timeout=3)
    for attempt in range(50):
        try:
            driver.verify_connectivity()
            break
        except Exception:
            if attempt == 49:
                raise
            time.sleep(1)
    with driver.session() as session:
        if not memgraph:
            s.result["version"] = [dict(r) for r in session.run("CALL dbms.components()")]
            session.run("CREATE CONSTRAINT node_id IF NOT EXISTS FOR (n:Node) REQUIRE n.id IS UNIQUE").consume()
        else:
            s.result["version"] = [dict(r) for r in session.run("SHOW VERSION")]
            session.run("CREATE INDEX ON :Node(id)").consume()
        with (DATA / "csv/nodes.csv").open() as f:
            rows = [dict(id=int(r["id"]), name=r["name"]) for r in csv.DictReader(f)]
        for start in range(0, len(rows), 1000):
            session.run("UNWIND $rows AS r CREATE (:Node {id:r.id, name:r.name})", rows=rows[start:start+1000]).consume()
        for label in MANIFEST["labels"].values():
            with (DATA / f"csv/edges_{label}.csv").open() as f:
                rows = [dict(src=int(r["src"]), dst=int(r["dst"])) for r in csv.DictReader(f)]
            for start in range(0, len(rows), 1000):
                session.run(f"UNWIND $rows AS r MATCH (s:Node {{id:r.src}}), (t:Node {{id:r.dst}}) CREATE (s)-[:{label}]->(t)", rows=rows[start:start+1000]).consume()
        s.result["loaded_edges"] = session.run("MATCH ()-[r]->() RETURN count(r) AS n").single()["n"]
        for q in QUERIES:
            query = cypher(q, s.engine)
            if query is None:
                s.skip(q, "Compound closure has no verified direct translation")
                continue
            (DATA / f'queries/q{q["id"]}.{s.engine}.cypher').write_text(query+";\n")
            try:
                s.check(q, s.query(q, lambda: [r["id"] for r in session.run(query)]), note="Native pattern subset, not general WALK RPQ")
            except Exception as e:
                s.result["checks"].append(dict(id=q["id"], status="query_error", error=str(e)))
    driver.close()


def falkordb(s):
    import redis
    s.docker("falkordb/falkordb:latest", ["-p", "127.0.0.1:16389:6379"])
    client = redis.Redis(host="127.0.0.1", port=16389, socket_timeout=60)
    for _ in range(40):
        try:
            client.ping()
            break
        except Exception:
            time.sleep(1)
    s.result["version"] = str(client.execute_command("MODULE", "LIST"))
    def query(text):
        return client.execute_command("GRAPH.QUERY", "rpq250k", text, "--compact")
    query("CREATE INDEX FOR (n:Node) ON (n.id)")
    with (DATA / "csv/nodes.csv").open() as f:
        rows = list(csv.DictReader(f))
    for start in range(0, len(rows), 500):
        query("CREATE " + ",".join(f'(:Node {{id:{r["id"]},name:{json.dumps(r["name"])}}})' for r in rows[start:start+500]))
    for label in MANIFEST["labels"].values():
        with (DATA / f"csv/edges_{label}.csv").open() as f:
            rows = list(csv.DictReader(f))
        for start in range(0, len(rows), 500):
            values = ",".join(f'[{r["src"]},{r["dst"]}]' for r in rows[start:start+500])
            query(f"UNWIND [{values}] AS r MATCH (s:Node {{id:r[0]}}), (t:Node {{id:r[1]}}) CREATE (s)-[:{label}]->(t)")
    s.result["loaded_edges"] = query("MATCH ()-[r]->() RETURN count(r)")[1][0][0][1]
    for q in QUERIES:
        text = cypher(q)
        if text is None:
            s.skip(q, "Compound closure has no verified direct translation")
            continue
        (DATA / f'queries/q{q["id"]}.falkordb.cypher').write_text(text+";\n")
        try:
            s.check(q, s.query(q, lambda: [row[0][1] for row in query(text)[1]]), note="Native pattern subset")
        except Exception as e:
            s.result["checks"].append(dict(id=q["id"], status="query_error", error=str(e)))


def java_command(s, command, timeout=120, input=None):
    lock = ROOT / "Databases/guides/runtime-lock.json"
    image = "eclipse-temurin:21-jdk"
    if lock.exists():
        image = json.loads(lock.read_text())["images"].get(image, image)
    return s.run(["docker", "run", "--rm", "-i", "--memory", "2g", "--cpus", "2",
                  "-v", f"{ROOT}:/work", "-v", f"{OUT}/tools:/tools:ro", "-v", f"{DATA}:/input:ro", "-w", "/work",
                  image, *command], timeout=timeout, input=input)


def jena(s):
    s.result["version"] = "Apache Jena 6.2.0 official binary distribution; Java 21"
    db = f"/work/Results/competitors_250k/jena-db-{time.time_ns()}"
    java_command(s, ["/tools/apache-jena-6.2.0/bin/tdb2.tdbloader", "--loc", db,
                     "/work/Datasets/rpqbench_250k/prepared/rdf/graph.nt"])
    # Keys are normalized IRIs, not original source IRIs.
    ids = {MANIFEST["base_iri"]+line.rsplit(maxsplit=1)[0].strip("<>"): int(line.rsplit(maxsplit=1)[1])
           for line in (DATA.parent / "pathrex/vertices.txt").read_text().splitlines()}
    for q in QUERIES:
        output = java_command(s, ["/tools/apache-jena-6.2.0/bin/tdb2.tdbquery", "--loc", db,
                                  "--query", f'/work/{QUERY_DIR.relative_to(ROOT)}/q{q["id"]}.rq',
                                  "--results", "CSV"])
        rows = list(csv.DictReader(io.StringIO(output)))
        s.check(q, [ids[next(iter(row.values()))] for row in rows])


def sparql_http(url, query):
    request = urllib.request.Request(url, data=urllib.parse.urlencode({"query":query}).encode(),
                                    headers={"Accept":"application/sparql-results+json"})
    return json.load(urllib.request.urlopen(request, timeout=60))


def rdf_checks(s, url):
    ids = {MANIFEST["base_iri"]+line.rsplit(maxsplit=1)[0].strip("<>"): int(line.rsplit(maxsplit=1)[1])
           for line in (DATA.parent / "pathrex/vertices.txt").read_text().splitlines()}
    for q in QUERIES:
        try:
            s.check(q, s.query(q, lambda: [ids[next(iter(row.values()))["value"]]
                    for row in sparql_http(url, q["sparql"])["results"]["bindings"]]))
        except Exception as e:
            s.result["checks"].append(dict(id=q["id"], status="query_error", error=str(e)))


def blazegraph(s):
    state = OUT / f"blazegraph-state-{time.time_ns()}"
    state.mkdir()
    (state / "blazegraph.properties").write_text('''com.bigdata.journal.AbstractJournal.file=/state/blazegraph.jnl
com.bigdata.journal.AbstractJournal.bufferMode=DiskRW
com.bigdata.rdf.sail.truthMaintenance=false
com.bigdata.rdf.store.AbstractTripleStore.quads=false
com.bigdata.rdf.store.AbstractTripleStore.statementIdentifiers=false
com.bigdata.rdf.store.AbstractTripleStore.axiomsClass=com.bigdata.rdf.axioms.NoAxioms
''')
    s.result["version"] = "Blazegraph BLAZEGRAPH_2_1_6_RC official release JAR"
    s.docker("eclipse-temurin:21-jdk", ["-p", "127.0.0.1:19999:9999", "-v", f"{OUT}/tools:/tools:ro", "-v", f"{state}:/state"],
             ["java", "-Xmx768m", "-Djetty.home=jar:file:/tools/blazegraph.jar!/war",
              "-Djetty.resourceBase=jar:file:/tools/blazegraph.jar!/war",
              "-cp", "/tools/blazegraph.jar", "com.bigdata.rdf.sail.webapp.NanoSparqlServer",
              "9999", "kb", "/state/blazegraph.properties"])
    url = "http://127.0.0.1:19999/blazegraph/namespace/kb/sparql"
    for attempt in range(40):
        try:
            sparql_http(url, "ASK {}")
            break
        except Exception:
            if attempt == 39:
                raise
            time.sleep(1)
    request = urllib.request.Request(url, data=(DATA / "rdf/graph.nt").read_bytes(),
                                    headers={"Content-Type":"application/n-triples"})
    s.result["import_response"] = urllib.request.urlopen(request, timeout=120).read().decode()
    rdf_checks(s, url)


def virtuoso(s):
    state = OUT / f"virtuoso-state-{time.time_ns()}"
    state.mkdir()
    s.docker("openlink/virtuoso-opensource-7:latest",
             ["-p", "127.0.0.1:18891:8890", "-e", "DBA_PASSWORD=rpq-smoke-local",
              "-e", "VIRT_Parameters_DirsAllowed=/input", "-e", "VIRT_Parameters_NumberOfBuffers=10000",
              "-e", "VIRT_Parameters_MaxDirtyBuffers=6000", "-v", f"{state}:/database"])
    for attempt in range(40):
        try:
            output = s.run(["docker", "exec", s.container, "isql", "1111", "dba", "rpq-smoke-local",
                            "EXEC=status();"], timeout=5)
            if "Error" in output:
                raise RuntimeError(output)
            s.result["version"] = output[:500]
            break
        except Exception:
            if attempt == 39:
                raise
            time.sleep(1)
    output = s.run(["docker", "exec", s.container, "isql", "1111", "dba", "rpq-smoke-local",
                    "EXEC=ld_dir('/input/rdf','graph.nt','http://example.org/rpq250k'); rdf_loader_run(); checkpoint;"])
    if "Error" in output:
        raise RuntimeError(output)
    # Virtuoso import goes to a named graph; explicitly select it in every query.
    url = "http://127.0.0.1:18891/sparql"
    ids = {MANIFEST["base_iri"]+line.rsplit(maxsplit=1)[0].strip("<>"): int(line.rsplit(maxsplit=1)[1])
           for line in (DATA.parent / "pathrex/vertices.txt").read_text().splitlines()}
    for q in QUERIES:
        text = q["sparql"].replace("WHERE", "FROM <http://example.org/rpq250k> WHERE", 1)
        (QUERY_DIR / f'q{q["id"]}.virtuoso.rq').write_text(text+"\n")
        s.check(q, s.query(q, lambda: [ids[next(iter(r.values()))["value"]]
                for r in sparql_http(url, text)["results"]["bindings"]]))




def millenniumdb(s):
    exe = OUT / "build/millenniumdb/bin/mdb"
    state = OUT / f"millenniumdb-db-{time.time_ns()}"
    s.result["version"] = s.run([exe, "--help"]).splitlines()[0]
    s.run([exe, "import", DATA / "rdf/graph.nt", state, "--buffer-strings", "256MB", "--buffer-tensors", "256MB"])
    log = (OUT / "logs/millenniumdb-server.log").open("w")
    args = list(map(str, [exe, "server", state, "--port", "12345", "--browser", "false", "--threads", "2",
                         "--strings-dynamic", "64MB", "--strings-static", "64MB", "--tensors-dynamic", "64MB",
                         "--tensors-static", "64MB", "--private-buffer", "64MB", "--versioned-buffer", "64MB"]))
    process = subprocess.Popen(args, stdout=log, stderr=log)
    try:
        url = "http://127.0.0.1:12345/sparql"
        for attempt in range(40):
            try:
                request = urllib.request.Request(url, data=b"ASK {}", headers={"Content-Type":"application/sparql-query", "Accept":"text/csv"})
                urllib.request.urlopen(request,timeout=3).read()
                break
            except Exception:
                if attempt == 39:
                    raise
                time.sleep(1)
        ids = {MANIFEST["base_iri"]+line.rsplit(maxsplit=1)[0].strip("<>"): int(line.rsplit(maxsplit=1)[1])
               for line in (DATA.parent / "pathrex/vertices.txt").read_text().splitlines()}
        for q in QUERIES:
            request = urllib.request.Request(url, data=q["sparql"].encode(), headers={"Content-Type":"application/sparql-query", "Accept":"text/csv"})
            def execute():
                output = urllib.request.urlopen(request, timeout=60).read().decode()
                rows = list(csv.reader(io.StringIO(output)))
                return [ids[row[0].strip("<>")] for row in rows[1:] if row]
            values = s.query(q, execute)
            s.check(q, values)
    finally:
        process.terminate()
        process.wait(timeout=10)
        log.close()


def ring(s):
    dat = DATA / "matrix/graph.dat"
    s.run([OUT / "build/ring/build-index-basic", dat])
    output = s.run([OUT / "build/ring/query-index-basic", dat, QUERY_DIR / "ring.tsv"])
    s.result["output"] = output
    for line in output.splitlines():
        parts = line.split(";")
        if len(parts) >= 3 and parts[0].isdigit():
            index = int(parts[0])
            if 1 <= index <= len(QUERIES):
                s.check(QUERIES[index-1], count=int(parts[1]))


def larpq(s):
    command = [OUT / "build/larpq-smoke", DATA / "matrix/graph.dat", QUERY_DIR / "larpq.tsv",
               MANIFEST["vertices"], len(MANIFEST["labels"])]
    if SUFFIX == "-workload20":
        command.append("extended")
    output = s.run(command)
    for line in output.splitlines():
        qid, values = line.split(";", 1)
        q = next(q for q in QUERIES if q["id"] == qid)
        s.check(q, list(map(int, values.split(","))) if values else [])


def main():
    global QUERIES, QUERY_DIR, SUFFIX
    parser = argparse.ArgumentParser(description=__doc__)
    aliases = {"la-rpq":"larpq", "rpq-matrix":"rpqmatrix", "rpq-matrix_gb":"rpqmatrixGB",
               "mdb":"millenniumdb", "ring-rpq":"ring", "rinq-rpq":"ring"}
    canonical = ["duckdb", "postgres", "pathrex", "rpqmatrix", "rpqmatrixGB", "kuzu", "neo4j", "memgraph", "falkordb", "jena", "blazegraph", "virtuoso", "millenniumdb", "ring", "larpq"]
    parser.add_argument("engine", choices=canonical + list(aliases))
    parser.add_argument("--output", type=Path, default=OUT, help="Directory for reports/logs; build and tool cache stays in Results/competitors_250k")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--workload20", action="store_true", help="Check 20 instantiated upstream templates instead of six smoke queries")
    selection.add_argument("--basic", action="store_true", help="Four existing simple queries shared by all 15 competitors")
    args = parser.parse_args()
    try:
        load_inputs()
    except ValueError as error:
        parser.error(str(error))
    (OUT / "logs").mkdir(parents=True, exist_ok=True)
    args.engine = aliases.get(args.engine, args.engine)
    if args.basic:
        from prepare_basic import prepare
        QUERIES = prepare()
        QUERY_DIR = DATA / "basic"
        SUFFIX = "-basic"
    if args.workload20:
        if args.engine in ("neo4j", "memgraph", "falkordb", "kuzu"):
            parser.error("No complete workload20 adapter for this engine; use the six-query smoke")
        QUERY_DIR = DATA / "workload20"
        QUERIES = json.loads((QUERY_DIR / "manifest.json").read_text())["queries"]
        SUFFIX = "-workload20"
    s = Smoke(args.engine, args.output.resolve())
    try:
        fn = {"duckdb": duckdb, "postgres": postgres,
              "pathrex": native, "rpqmatrix": native, "rpqmatrixGB": native,
              "kuzu": kuzu, "neo4j": bolt, "memgraph": bolt, "falkordb": falkordb,
              "jena": jena, "blazegraph": blazegraph, "virtuoso": virtuoso,
              "millenniumdb": millenniumdb, "ring": ring, "larpq": larpq}[args.engine]
        fn(s)
        validate_checks(args.engine, s.result["checks"])
        failures = [c for c in s.result["checks"] if c["status"] in ("mismatch", "query_error")]
        gaps = [c for c in s.result["checks"] if c["status"] in ("unsupported", "no_translation", "not_checked")]
        s.result["status"] = "completed_with_failures" if failures else ("completed_with_gaps" if gaps else "completed")
    except Exception as e:
        s.result.update(status="failed", error=str(e))
    finally:
        s.finish()
    if s.result["status"] in ("failed", "completed_with_failures"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
