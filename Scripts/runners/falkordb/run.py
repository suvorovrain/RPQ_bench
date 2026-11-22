import csv
import json
import re
import time
from ..cypher import query_text
from ..runtime import require

INTERNAL_TIME = re.compile(rb"Query internal execution time: ([0-9.]+) milliseconds")

def run(s):
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
    with (s.data / "csv/nodes.csv").open() as f:
        rows = list(csv.DictReader(f))
    for start in range(0, len(rows), 500):
        query("CREATE " + ",".join(f'(:Node {{id:{r["id"]},name:{json.dumps(r["name"])}}})' for r in rows[start:start+500]))
    for label in s.manifest["labels"].values():
        with (s.data / f"csv/edges_{label}.csv").open() as f:
            rows = list(csv.DictReader(f))
        for start in range(0, len(rows), 500):
            values = ",".join(f'[{r["src"]},{r["dst"]}]' for r in rows[start:start+500])
            query(f"UNWIND [{values}] AS r MATCH (s:Node {{id:r[0]}}), (t:Node {{id:r[1]}}) CREATE (s)-[:{label}]->(t)")
    s.result["loaded_edges"] = query("MATCH ()-[r]->() RETURN count(r)")[1][0][0][1]
    for q in s.queries:
        text = query_text(q)
        if text is None:
            s.skip(q, "Compound closure has no verified direct translation")
            continue
        (s.query_dir / f'q{q["id"]}.falkordb.cypher').write_text(text + ";\n")
        samples = []
        for iteration in range(-s.args.warmups, s.args.runs):
            _, rows, stats = query(text)
            s.check(q, [row[0][1] for row in rows])
            timings = [match for field in stats if (match := INTERNAL_TIME.fullmatch(field))]
            require(len(timings) == 1, f"Unexpected FalkorDB statistics: {stats!r}")
            if iteration >= 0:
                samples.append(float(timings[0][1]))
        s.add(q, samples, "falkordb_internal_execution", "endpoint_set_every_run")


if __name__ == "__main__":
    from ..workflow import main

    main(default_engine='falkordb')
