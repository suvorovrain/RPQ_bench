#!/usr/bin/env python3
"""Instantiate upstream's 20 RPQBench templates and generate SQL/NFA/oracles.

These are deterministic smoke bindings, not the original random benchmark.
"""
import csv
import json
import re
from collections import defaultdict, deque
from pathlib import Path
from pyformlang.regular_expression import PythonRegex

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "Datasets/rpqbench_250k/prepared"


def main():
    manifest = json.loads((DATA / "manifest.json").read_text())
    node_ids = {line.rsplit(maxsplit=1)[0].strip("<>"): int(line.rsplit(maxsplit=1)[1])
                for line in (DATA.parent / "pathrex/vertices.txt").read_text().splitlines()}
    labels = {name:int(i) for i,name in manifest["labels"].items()}
    chars = {name:chr(65+i) for i,name in enumerate(labels)}
    char_to_pid = {chars[name]:pid for name,pid in labels.items()}
    bindings = dict(article="<Article1>", person=f'<{manifest["queries"][2]["source_name"]}>',
                    inproceeding="<Inproceeding1>", journal="<1940>")
    adjacency = defaultdict(list)
    reverse = defaultdict(list)
    with (DATA / "csv/edges.csv").open() as f:
        for row in csv.DictReader(f):
            s,p,t = map(int, (row["src"],row["pid"],row["dst"]))
            adjacency[s,p].append(t)
            reverse[t,p].append(s)
    out = DATA / "workload20"
    out.mkdir(exist_ok=True)
    workload = []
    for line in (ROOT / "vendor/larpq/Datasets/RPQBench/sparql-queries-templates.txt").read_text().splitlines():
        qid,template = line.split(",",1)
        pattern = template.format(**bindings)
        subject,rest = pattern.split(" ",1)
        regex,obj = rest.rsplit(" ",1)
        python_regex = re.sub(r"<([^>]+)>",lambda m:chars[m[1]],regex).replace("/","")
        dfa = PythonRegex(python_regex).to_epsilon_nfa().to_deterministic().minimize()
        states = {state:i for i,state in enumerate(sorted(dfa.states,key=str))}
        transitions = [(states[s],char_to_pid[str(symbol.value)],states[t])
                       for s,row in dfa.to_dict().items() for symbol,t in row.items()]
        starts = [states[s] for s in dfa.start_states]
        finals = [states[s] for s in dfa.final_states]
        backwards = subject.startswith("?")
        bound = obj if backwards else subject
        source = node_ids[bound.strip("<>")]
        if backwards:
            starts,finals = finals,starts
            transitions = [(t,p,s) for s,p,t in transitions]
        visited = {(source,q) for q in starts}
        queue = deque(visited)
        result = set()
        graph = reverse if backwards else adjacency
        while queue:
            node,state = queue.popleft()
            if state in finals:
                result.add(node)
            for s,p,t in transitions:
                if state == s:
                    for target in graph[node,p]:
                        pair = target,t
                        if pair not in visited:
                            visited.add(pair); queue.append(pair)
        variable = subject if backwards else obj
        sparql = f'BASE <{manifest["base_iri"]}> SELECT DISTINCT {variable} WHERE {{ {pattern} }}'
        values = ",".join(f"({s},{p},{t})" for s,p,t in transitions)
        seeds = ",".join(f"(CAST({source} AS BIGINT),{q})" for q in starts)
        origin,target = ("dst","src") if backwards else ("src","dst")
        sql = (f"WITH RECURSIVE transitions(q,label,r) AS (VALUES {values}),\n"
               f"reach(v,q) AS (VALUES {seeds} UNION SELECT e.{target},t.r FROM reach r "
               f"JOIN transitions t ON r.q=t.q JOIN edges e ON e.{origin}=r.v AND e.pid=t.label)\n"
               f"SELECT DISTINCT v FROM reach WHERE q IN ({','.join(map(str,finals))}) ORDER BY v;\n")
        q = dict(id=qid,pattern=pattern,sparql=sparql,mode="any-con" if backwards else "con-any",
                 source=source,starts=starts,finals=finals,transitions=transitions,
                 reverse_graph=backwards,targets=sorted(result),count=len(result))
        (out / f"q{qid}.rq").write_text(sparql+"\n")
        (out / f"q{qid}.sql").write_text(sql)
        (out / f"q{qid}.automaton.json").write_text(json.dumps(q,indent=2)+"\n")
        workload.append(q)
    (out / "pathrex.txt").write_text("".join(f'{q["id"]},{q["pattern"]}\n' for q in workload))
    # Native parsers inspect the final three bytes '?x#'; long variable names
    # such as upstream ?obj would be misread as bound endpoints and return 0.
    def native_pattern(q):
        return q["pattern"].replace("?sub", "?s").replace("?obj", "?t")
    (out / "matrix.tsv").write_text("".join(f'{q["id"]} {native_pattern(q)}#\n' for q in workload))
    (out / "ring.tsv").write_text("\n".join(f'{native_pattern(q)}#' for q in workload))
    (out / "larpq.tsv").write_text("".join(
        f'{q["id"]} {q["source"]-1} {1+max(max(s,t) for s,p,t in q["transitions"])} '
        f'{sum(1<<s for s in q["starts"])} {sum(1<<s for s in q["finals"])} '
        f'{int(q["reverse_graph"])} {len(q["transitions"])} '
        + " ".join(f"{s} {p-1} {t}" for s,p,t in q["transitions"]) + "\n" for q in workload))
    (out / "manifest.json").write_text(json.dumps(dict(bindings=bindings,queries=workload),indent=2)+"\n")
    print([(q["id"],q["mode"],q["count"]) for q in workload])


if __name__ == "__main__":
    main()
