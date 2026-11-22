import csv
import time

def query_text(q, mode="default"):
    if "cypher" in q:
        return q["cypher"].get(mode, q["cypher"].get("default"))
    if q.get("suite") != "basic4":
        return None
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


def run_bolt(s, measure):
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
        with (s.data / "csv/nodes.csv").open() as f:
            rows = [dict(id=int(r["id"]), name=r["name"]) for r in csv.DictReader(f)]
        for start in range(0, len(rows), 1000):
            session.run("UNWIND $rows AS r CREATE (:Node {id:r.id, name:r.name})", rows=rows[start:start+1000]).consume()
        for label in s.manifest["labels"].values():
            with (s.data / f"csv/edges_{label}.csv").open() as f:
                rows = [dict(src=int(r["src"]), dst=int(r["dst"])) for r in csv.DictReader(f)]
            for start in range(0, len(rows), 1000):
                session.run(f"UNWIND $rows AS r MATCH (s:Node {{id:r.src}}), (t:Node {{id:r.dst}}) CREATE (s)-[:{label}]->(t)", rows=rows[start:start+1000]).consume()
        s.result["loaded_edges"] = session.run("MATCH ()-[r]->() RETURN count(r) AS n").single()["n"]
        for q in s.queries:
            query = query_text(q, s.engine)
            if query is None:
                s.skip(q, "Compound closure has no verified direct translation")
                continue
            (s.folder / f'q{q["id"]}.{s.engine}.cypher').write_text(query+";\n")
            measure(s, session, q, query)
    driver.close()
