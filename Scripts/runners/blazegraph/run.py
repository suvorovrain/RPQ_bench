import json
import time
import urllib.request
import uuid
from ..http import iri_ids, sparql_http, target_ids
from ..runtime import require


def run(s):
    state = s.folder / f"blazegraph-state-{time.time_ns()}"
    state.mkdir()
    (state / "blazegraph.properties").write_text('''com.bigdata.journal.AbstractJournal.file=/state/blazegraph.jnl
com.bigdata.journal.AbstractJournal.bufferMode=DiskRW
com.bigdata.rdf.sail.truthMaintenance=false
com.bigdata.rdf.store.AbstractTripleStore.quads=false
com.bigdata.rdf.store.AbstractTripleStore.statementIdentifiers=false
com.bigdata.rdf.store.AbstractTripleStore.axiomsClass=com.bigdata.rdf.axioms.NoAxioms
''')
    (state / "log4j.properties").write_text("""log4j.rootLogger=WARN, console
log4j.appender.console=org.apache.log4j.ConsoleAppender
log4j.appender.console.layout=org.apache.log4j.PatternLayout
log4j.appender.console.layout.ConversionPattern=%p %c - %m%n
log4j.logger.com.bigdata.bop.engine.QueryLog=INFO, query
log4j.additivity.com.bigdata.bop.engine.QueryLog=false
log4j.appender.query=org.apache.log4j.FileAppender
log4j.appender.query.File=/state/queries.log
log4j.appender.query.layout=org.apache.log4j.PatternLayout
log4j.appender.query.layout.ConversionPattern=%m%n
""")
    s.result["version"] = "Blazegraph BLAZEGRAPH_2_1_6_RC official release JAR"
    s.docker("eclipse-temurin:21-jdk", ["-p", "127.0.0.1:19999:9999", "-v", f"{s.runtime}/tools:/tools:ro", "-v", f"{state}:/state"],
             ["java", "-Xmx768m", "-Dlog4j.configuration=file:/state/log4j.properties",
              "-Djetty.home=jar:file:/tools/blazegraph.jar!/war",
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
    request = urllib.request.Request(url, data=(s.data / "rdf/graph.nt").read_bytes(),
                                    headers={"Content-Type":"application/n-triples"})
    s.result["import_response"] = urllib.request.urlopen(request, timeout=120).read().decode()
    ids = iri_ids(s)
    tokens = {}
    for q in s.queries:
        tokens[q["id"]] = []
        start, separator, body = q["sparql"].partition("{")
        require(separator, f"Missing WHERE group for Blazegraph query {q['id']}")
        for iteration in range(-s.args.warmups, s.args.runs):
            token = str(uuid.uuid4())
            hint = f'<http://www.bigdata.com/queryHints#Query> <http://www.bigdata.com/queryHints#queryId> "{token}" .'
            response = sparql_http(url, f"{start}{{ {hint} {body}")
            s.check(q, target_ids(response, ids))
            tokens[q["id"]].append(token)
    (s.folder / "query-log-ids.json").write_text(json.dumps(tokens, indent=2) + "\n")
    expected = {token for group in tokens.values() for token in group}
    deadline = time.monotonic() + 5
    log = state / "queries.log"
    while True:
        timings = {}
        if log.exists():
            for line in log.read_text().splitlines():
                fields = line.split("\t")
                if len(fields) > 8 and fields[0] in expected and fields[8] == "total":
                    require(fields[0] not in timings and not fields[6], f"Invalid Blazegraph query log row: {line}")
                    timings[fields[0]] = int(fields[4])
        if expected == timings.keys():
            break
        require(time.monotonic() < deadline, f"Missing Blazegraph QueryLog rows: {expected - timings.keys()}")
        time.sleep(0.05)
    for q in s.queries:
        s.add(q, [timings[token] for token in tokens[q["id"]][s.args.warmups:]],
              "blazegraph_query_engine", "endpoint_set_every_run", extra={"resolution_ms": 1})


if __name__ == "__main__":
    from ..workflow import main

    main(default_engine='blazegraph')
