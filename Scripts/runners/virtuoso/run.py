import json
import re
import time
from ..http import iri_ids, sparql_http, target_ids
from ..runtime import require


def run(s):
    state = s.folder / f"virtuoso-state-{time.time_ns()}"
    state.mkdir()
    s.docker("openlink/virtuoso-opensource-7:latest",
             ["-p", "127.0.0.1:18891:8890", "-e", "DBA_PASSWORD=rpq-smoke-local",
              "-e", "VIRT_Parameters_DirsAllowed=/input,/database", "-e", "VIRT_Parameters_NumberOfBuffers=10000",
              "-e", "VIRT_Parameters_MaxDirtyBuffers=6000", "-v", f"{state}:/database"])
    def sql(statement, timeout=None):
        output = s.run(["docker", "exec", s.container, "isql", "1111", "dba", "rpq-smoke-local",
                        "ERRORS=STDOUT", "BLOBS=ON", "EXEC=" + " ".join(statement.split())], timeout=timeout)
        require("*** Error" not in output, f"Virtuoso SQL failed: {output}")
        return output

    for attempt in range(40):
        try:
            s.result["version"] = sql("status();", timeout=5).splitlines()[1]
            break
        except Exception:
            if attempt == 39:
                raise
            time.sleep(1)
    sql("ld_dir('/input/rdf','graph.nt','http://example.org/rpq250k'); rdf_loader_run(); checkpoint;")
    sql("prof_enable(1, 1);")
    # Virtuoso import goes to a named graph; explicitly select it in every query.
    url = "http://127.0.0.1:18891/sparql"
    ids = iri_ids(s)
    requests = []
    for q in s.queries:
        text = q["sparql"].replace("WHERE", "FROM <http://example.org/rpq250k> WHERE", 1)
        (s.query_dir / f'q{q["id"]}.virtuoso.rq').write_text(text+"\n")
        for iteration in range(-s.args.warmups, s.args.runs):
            s.check(q, target_ids(sparql_http(url, text), ids))
            requests.append((q, iteration, text))
    sql("prof_enable(0);")
    output = sql("""
        SELECT concat('RPQ:', cast(ql_id as varchar), ':', cast(ql_rt_msec as varchar), ':',
                      cast(ql_c_msec as varchar), ':', bin2hex(cast(ql_text as varbinary))) AS timing
        FROM DB.DBA.SYS_QUERY_LOG
        WHERE qrl_file = '/database/virtuoso.qrl' AND ql_user = 'SPARQL' AND ql_error IS NULL;
    """)
    entries = [re.fullmatch(r"RPQ:(\d+):(\d+):(\d+):([0-9a-fA-F]+)", line.strip()) for line in output.splitlines()]
    entries = [entry.groups() for entry in entries if entry]
    entries.sort(key=lambda entry: int(entry[0]))
    require(len(entries) == len(requests), f"Virtuoso query log has {len(entries)} rows for {len(requests)} requests")
    require(len({entry[0] for entry in entries}) == len(entries), "Duplicate Virtuoso query log ID")
    execution = {q["id"]: [] for q in s.queries}
    compilation = {q["id"]: [] for q in s.queries}
    mapping = []
    for (q, iteration, text), (log_id, elapsed, compiling, encoded) in zip(requests, entries):
        statement = bytes.fromhex(encoded).decode()
        require(statement == f"sparql {{\n{text}\n}}",
                f"Virtuoso query log text mismatch for {q['id']} at iteration {iteration}: {statement}")
        mapping.append(dict(id=q["id"], iteration=iteration, log_id=int(log_id),
                            elapsed_ms=int(elapsed), compilation_ms=int(compiling)))
        if iteration >= 0:
            execution[q["id"]].append(int(elapsed))
            compilation[q["id"]].append(int(compiling))
    (s.folder / "query-log.json").write_text(json.dumps(mapping, indent=2) + "\n")
    for q in s.queries:
        s.add(q, execution[q["id"]], "virtuoso_query_log_elapsed", "endpoint_set_every_run",
              extra={"resolution_ms": 1}, phases={"compilation": compilation[q["id"]]})


if __name__ == "__main__":
    from ..workflow import main

    main(default_engine='virtuoso')
