#!/usr/bin/env python3
"""Probe actual result contracts on a seven-vertex graph; no performance timings.

Uses upstream nt-to-mm, pinned native binaries and Kuzu wheel. --jena additionally
checks SPARQL with the locked Java image and downloaded Jena distribution.
Outputs fixtures/logs in Results/contract and compact evidence in Databases/guides.
"""
import argparse
import csv
import io
import json
import os
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Results/contract"
NAMES = list("ABCDEFG")
EDGES = [("A","p","B"),("A","p","C"),("B","p","D"),("C","p","D"),
         ("B","q","A"),("C","q","A"),("E","z","E"),("F","p","G"),("G","q","F")]
CASES = [
    ("con_any", "<A> <p> ?t", 2),
    ("diamond", "<A> <p>/<p> ?t", 1),
    ("repeat_edge", "<F> <p>/<q>/<p> ?t", 1),
    ("zero_length", "<E> (<p>)* ?t", 1),
    ("positive_empty", "<E> (<p>)+ ?t", 0),
    ("optional", "<E> (<p>)? ?t", 1),
    ("any_con", "?s <p> <D>", 2),
    ("any_any", "?s <p> ?t", 5),
    ("con_con_true", "<A> <p>/<p> <D>", 1),
    ("con_con_false", "<A> <p> <D>", 0),
    ("same_variable", "?x <p> ?x", 0),
    ("inverse", "<D> ^<p> ?t", 2),
    ("inverse_closure", "<D> ^(<p>*) ?t", 4),
    ("inverse_nested", "<A> (<p>|^<q>)* ?t", 4),
    ("missing_label_star", "<E> (<missing>)* ?t", 1),
    # E is in V, Outside is not: graph-relative relation excludes Outside.
    ("outside_vertex_star", "<Outside> (<p>)* ?t", 0),
]


def run(args, **kwargs):
    result = subprocess.run(list(map(str,args)), cwd=ROOT, capture_output=True, text=True,
                            timeout=180, env={**os.environ,"OMP_NUM_THREADS":"2"}, **kwargs)
    with (OUT / "commands.log").open("a") as log:
        log.write(repr(list(map(str,args)))+"\n"+result.stdout+result.stderr+"\n")
    result.check_returncode()
    return result.stdout


def upstream_automata_probe():
    scripts=ROOT/"vendor/larpq/Scripts"
    (OUT/"short.nt").write_text(run([sys.executable,scripts/"deprefix-nt",OUT/"graph.nt"]))
    mm=OUT/"mm-short"
    if not mm.exists(): run([sys.executable,scripts/"nt-to-mm",OUT/"short.nt",mm])
    queries=OUT/"upstream-queries.txt"
    queries.write_text("".join(f"{i},{q[1]}\n" for i,q in enumerate(CASES[:6],1)))
    automata=OUT/"upstream-automata"
    run([sys.executable,scripts/"sparql-to-fa",queries,mm,automata])
    rows=[]
    for i in range(1,7):
        folder=automata/str(i); meta=(folder/"meta.txt").read_text().splitlines()
        source=int(meta[0].split()[0])-1
        starts=list(map(int,meta[1].split()[1:])); finals=list(map(int,meta[2].split()[1:]))
        transitions=[]; states=0
        for path in folder.glob("*.txt"):
            if path.stem in ("meta","raw"): continue
            label=int(path.stem)-1
            lines=[line for line in path.read_text().splitlines() if line and not line.startswith("%")]
            states=int(lines[0].split()[0])
            for line in lines[1:]:
                s,t=map(int,line.split()); transitions.append((s-1,label,t-1))
        rows.append(f"{i} {source} {states} {sum(1<<(s-1) for s in starts)} "
                    f"{sum(1<<(s-1) for s in finals)} 0 {len(transitions)} "
                    +" ".join(" ".join(map(str,t)) for t in transitions))
    (OUT/"upstream-larpq.tsv").write_text("\n".join(rows)+"\n")
    def mapping(path):
        return {line.rsplit(maxsplit=1)[0].strip("<>"):int(line.rsplit(maxsplit=1)[1])
                for line in path.read_text().splitlines()}
    vertices=mapping(mm/"vertices.txt"); labels=mapping(mm/"edges.txt")
    (OUT/"graph.dat").write_text("".join(f"{vertices[s]} {labels[p]} {vertices[t]}\n" for s,p,t in EDGES))
    output=run([ROOT/"Results/competitors_250k/build/larpq-smoke",OUT/"graph.dat",
                OUT/"upstream-larpq.tsv",7,3,"extended"])
    checks=[]
    for line in output.splitlines():
        index,values=line.split(";"); case=CASES[int(index)-1]
        count=len(values.split(",")) if values else 0
        assert count==case[2],(case,count)
        checks.append({"id":case[0],"count":count,"status":"pass"})
    assert len(checks)==6
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jena", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    nt=OUT/"graph.nt"
    nt.write_text("".join(f'<http://example.org/{s}> <http://example.org/{p}> <http://example.org/{t}> .\n' for s,p,t in EDGES))
    mm=OUT/"mm"
    if not mm.exists():
        run([sys.executable,ROOT/"vendor/larpq/Scripts/nt-to-mm",nt,mm])
    patterns=OUT/"pathrex.txt"
    patterns.write_text("".join(f"{i},{re.sub(r'<([^>]+)>', r'<http://example.org/\1>', pattern)}\n"
                               for i,(_,pattern,_) in enumerate(CASES,1)))
    report={"date":"2026-10-11","graph":{"vertices":NAMES,"edges":EDGES},
            "conversion":"vendor/larpq/Scripts/nt-to-mm; full IRIs retained",
            "pathrex":{},"larpq":{},"kuzu":{}}
    for algorithm in ["rpqmatrix","nfarpq"]:
        output=OUT/f"pathrex-{algorithm}.json"
        command=[ROOT/"Databases/pathrex/target/release/pathrex","query","-g",mm,"-q",patterns,
                 "-a",algorithm,"-o",output]
        if algorithm=="rpqmatrix": command.extend(["-p","pang-hybrid"])
        run(command)
        results=json.loads(output.read_text())["results"]
        assert len(results)==len(CASES)
        report["pathrex"][algorithm]=[
            {"id":case[0],"pattern":case[1],"relation_answer_count":case[2],
             **entry["algorithms"][algorithm]}
            for case,entry in zip(CASES,results)]
    build=ROOT/"Results/competitors_250k/build"
    run(["gcc",ROOT/"Scripts/competitors/contract_larpq.c","-o",OUT/"larpq-contract",
         "-IDatabases/larpq/include","-Ivendor/GraphBLAS/Include",
         f"-L{build}/larpq/experimental",f"-L{build}/larpq/src","-Lvendor/GraphBLAS/build",
         f"-Wl,-rpath,{build}/larpq/experimental:{build}/larpq/src:{ROOT}/vendor/GraphBLAS/build",
         "-llagraphx","-llagraph","-lgraphblas","-fopenmp"])
    expected={"con_any_p":[1,2],"diamond_pp":[3],"repeated_edge_pqp":[6],
              "zero_length_E":[4],"multi_source_p":[3],"all_sources_p":[1,2,3,6],
              "inverse_label_from_D":[1,2],"whole_inverse_from_D":[1,2],
              "whole_inverse_without_state_swap":[]}
    for line in run([OUT/"larpq-contract"]).splitlines():
        key,values=line.split(";")
        actual=list(map(int,values.split(","))) if values else []
        assert actual==expected[key],(key,actual,expected[key])
        report["larpq"][key]={"targets":[NAMES[i] for i in actual],"status":"pass"}
    report["upstream_sparql_to_fa_larpq"]=upstream_automata_probe()
    import kuzu
    db=kuzu.Database(buffer_pool_size=64*1024**2,max_num_threads=2)
    con=kuzu.Connection(db)
    con.execute("CREATE NODE TABLE Node(id INT64, name STRING, PRIMARY KEY(id))")
    for label in ["p","q","z"]: con.execute(f"CREATE REL TABLE {label}(FROM Node TO Node)")
    for i,name in enumerate(NAMES): con.execute(f"CREATE (:Node {{id:{i},name:'{name}'}})")
    for s,p,t in EDGES:
        con.execute(f"MATCH (s:Node {{name:'{s}'}}),(t:Node {{name:'{t}'}}) CREATE (s)-[:{p}]->(t)")
    def kuzu_values(key,query):
        r=con.execute(query); values=[]
        while r.has_next(): values.append(r.get_next())
        report["kuzu"][key]={"query":query,"rows":values}
        return values
    assert kuzu_values("repeat_edge","MATCH (s:Node {name:'F'})-[:p]->()-[:q]->()-[:p]->(t) RETURN DISTINCT t.name")==[["G"]]
    assert kuzu_values("any_con","MATCH (s)-[:p]->(t:Node {name:'D'}) RETURN DISTINCT s.name")==[["B"],["C"]]
    assert kuzu_values("same_variable","MATCH (s)-[:p]->(s) RETURN DISTINCT s.name")==[]
    # A separate 31-edge chain exposes default recursion cap without cycles.
    for i in range(100,132): con.execute(f"CREATE (:Node {{id:{i},name:'chain{i}'}})")
    for i in range(100,131): con.execute(f"MATCH (s:Node {{id:{i}}}),(t:Node {{id:{i+1}}}) CREATE (s)-[:p]->(t)")
    default=kuzu_values("default_depth","MATCH (s:Node {id:100})-[:p*1..]->(t) RETURN DISTINCT t.id ORDER BY t.id")
    try:
        kuzu_values("explicit_depth31","MATCH (s:Node {id:100})-[:p*1..31]->(t) RETURN DISTINCT t.id ORDER BY t.id")
    except RuntimeError as error:
        report["kuzu"]["explicit_depth31"]={"error":str(error)}
    assert len(default)==30
    con.execute("CALL var_length_extend_max_depth=31")
    explicit=kuzu_values("configured_depth31","MATCH (s:Node {id:100})-[:p*1..31]->(t) RETURN DISTINCT t.id ORDER BY t.id")
    assert len(explicit)==31
    con.close(); db.close()
    if args.jena:
        lock=json.loads((ROOT/"Databases/guides/runtime-lock.json").read_text())
        image=lock["images"]["eclipse-temurin:21-jdk"]
        report["jena"]={}
        for key,pattern,expected_count in CASES:
            if key not in ["repeat_edge","diamond","any_con","any_any","same_variable","missing_label_star","outside_vertex_star"]: continue
            query=OUT/f"{key}.rq"
            query.write_text(f"BASE <http://example.org/> SELECT (COUNT(*) AS ?n) WHERE {{ SELECT DISTINCT * WHERE {{ {pattern} }} }}\n")
            result=run(["docker","run","--rm","--memory","2g","--cpus","2",
                        "-v",f"{OUT}:/input:ro","-v",f"{ROOT}/Results/competitors_250k/tools:/tools:ro",
                        image,"/tools/apache-jena-6.2.0/bin/arq","--data","/input/graph.nt",
                        "--query",f"/input/{key}.rq","--results","CSV"])
            actual=int(next(csv.DictReader(io.StringIO(result)))["n"])
            report["jena"][key]={"actual":actual,"graph_relation_count":expected_count}
    path=ROOT/"Databases/guides/contract-results.json"
    path.write_text(json.dumps(report,indent=2)+"\n")
    print("Contract evidence:",path)


if __name__=="__main__": main()
