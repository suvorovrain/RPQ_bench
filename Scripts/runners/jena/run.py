from pathlib import Path
from ..config import ROOT
from ..runtime import java_command, require
def run(s):
    folder=s.folder.relative_to(ROOT);docker_folder=Path("/work")/folder
    inputs=s.folder/"jena-queries.tsv"
    inputs.write_text("".join(q["id"]+"\t"+",".join(map(str,q["targets"]))+"\t"+q["sparql"].replace("\n"," ")+"\n" for q in s.queries))
    classes=docker_folder/"build"
    java_command(s,["javac","-proc:none","-cp","/tools/apache-jena-6.2.0/lib/*","-d",classes,
                       "/work/Scripts/runners/jena/JenaBench.java"])
    output=java_command(s,["java",s.options.get("heap", "-Xmx768m"),"-cp",f"/tools/apache-jena-6.2.0/lib/*:{classes}",
        "JenaBench","/input/rdf/graph.nt",docker_folder/"jena-tdb",docker_folder/inputs.name,
        "/graph/vertices.txt",s.args.runs,s.args.warmups,s.manifest["base_iri"]])
    queries = {q["id"]: q for q in s.queries}
    parsing = {qid: [] for qid in queries}
    txn = {qid: [] for qid in queries}
    for line in output.splitlines():
        if line.startswith("JENA;"):
            _, qid, iteration, parse_ms, txn_ms, count = line.split(";")
            require(int(iteration) == len(txn[qid]) and int(count) == queries[qid]["count"], line)
            parsing[qid].append(float(parse_ms))
            txn[qid].append(float(txn_ms))
    for qid, q in queries.items():
        s.add(q, txn[qid], "jena_tdb_read_transaction", "endpoint_set_every_run",
              phases={"sparql_parse": parsing[qid]})


if __name__ == "__main__":
    from ..workflow import main

    main(default_engine='jena')
