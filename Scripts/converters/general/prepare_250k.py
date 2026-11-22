#!/usr/bin/env python3
"""Prepare one graph, shared queries and exact endpoint oracles for competitors.

Requires rdflib. Does not overwrite the user's existing engine inputs.
"""
import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections import defaultdict, deque
from pathlib import Path

BASE = "http://example.org/"


def mapping(path):
    result = {}
    for line in path.read_text().splitlines():
        name, number = line.rsplit(maxsplit=1)
        result[int(number)] = name.strip("<>")
    return result


def write_csv(path, header, rows):
    with path.open("w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(header)
        writer.writerows(rows)


def endpoints(edges, query):
    adjacency = defaultdict(list)
    transitions = defaultdict(list)
    for s, label, t in edges:
        adjacency[s, label].append(t)
    for state, label, next_state in query["transitions"]:
        transitions[state, label].append(next_state)
    queue = deque([(query["source"], 0)])
    visited = set(queue)
    answer = set()
    while queue:
        node, state = queue.popleft()
        if state in query["finals"]:
            answer.add(node)
        for (q, label), next_states in transitions.items():
            if q != state:
                continue
            for target in adjacency[node, label]:
                for next_state in next_states:
                    pair = target, next_state
                    if pair not in visited:
                        visited.add(pair)
                        queue.append(pair)
    return sorted(answer)


def prepare(source_dir, bootstrap_mm=False):
    from rdflib import Graph

    out = source_dir / "prepared"
    if out.exists():
        raise SystemExit(f"Refusing to overwrite {out}; choose a new source directory or move it aside.")
    mm = source_dir / "pathrex"
    if not mm.exists() and bootstrap_mm:
        scripts = Path(__file__).resolve().parents[3] / "vendor/larpq/Scripts"
        with tempfile.TemporaryDirectory(prefix="rpq250k-") as temporary:
            temporary = Path(temporary)
            for command, target in [
                ([scripts / "truncate", source_dir / "rpqbench_250k.n3",
                  "--s=^(<http://localhost|_)", "--p=.*", "--o=^(<http://localhost|_)"], temporary / "truncated.nt"),
                ([scripts / "deprefix-nt", temporary / "truncated.nt"], temporary / "short.nt"),
                ([scripts / "remove-dups", temporary / "short.nt"], temporary / "unique.nt")]:
                with target.open("w") as stream:
                    subprocess.run([sys.executable, *map(str, command)], stdout=stream, check=True)
            subprocess.run([sys.executable, str(scripts / "nt-to-mm"), str(temporary / "unique.nt"), str(mm)], check=True)
    nodes, labels = mapping(mm / "vertices.txt"), mapping(mm / "edges.txt")
    edges = set()
    for pid in labels:
        lines = [line for line in (mm / f"{pid}.txt").read_text().splitlines()
                 if line and not line.startswith("%")]
        for line in lines[1:]:
            s, t = map(int, line.split()[:2])
            edges.add((s, pid, t))

    graph = Graph().parse(source_dir / "rpqbench_250k.n3", format="n3")
    node_ids = {name: number for number, name in nodes.items()}
    label_ids = {name: number for number, name in labels.items()}
    actual = set()
    collisions = defaultdict(set)
    # This generator writes one triple per line and explicit _: identifiers.
    # N3 parsers may rename those identifiers. Keep the lexical IDs used by the
    # existing matrices, while validating the full N3 above with a real parser.
    prefixes = dict(re.findall(r'@prefix\s+(\w+):\s*<([^>]+)>\s*\.',
                               (source_dir / "rpqbench_250k.n3").read_text()))
    term = r'(?:<[^>]+>|_:[\w.-]+|[\w]+:[\w.-]+)'
    resource_triple = re.compile(rf'^({term})\s+({term})\s+({term})\s*\.\s*$')
    projected_rows = 0
    def expanded(token):
        if token.startswith('<'):
            return token[1:-1]
        if token.startswith('_:'):
            return token
        prefix, local = token.split(':', 1)
        return prefixes[prefix] + local
    def short(token):
        if token.startswith('<'):
            return token[1:-1].rsplit('/', 1)[-1]
        return token.split(':', 1)[1]
    for line in (source_dir / "rpqbench_250k.n3").read_text().splitlines():
        match = resource_triple.fullmatch(line)
        if not match:
            continue
        tokens = match.groups()
        if not all(t.startswith('<http://localhost') or t.startswith('_:') for t in (tokens[0], tokens[2])):
            continue
        names = [short(t) for t in tokens]
        projected_rows += 1
        for name, token in zip(names, tokens):
            collisions[name].add(expanded(token))
        if names[0] not in node_ids or names[1] not in label_ids or names[2] not in node_ids:
            raise ValueError(f"Source edge missing from existing dictionaries: {names}")
        actual.add((node_ids[names[0]], label_ids[names[1]], node_ids[names[2]]))
    if actual != edges:
        raise ValueError(f"Source/MM mismatch: source-only={len(actual-edges)}, MM-only={len(edges-actual)}")
    ambiguous = {k: sorted(v) for k, v in collisions.items() if len(v) > 1}

    out.mkdir()
    for name in ("csv", "rdf", "matrix", "queries", "automata"):
        (out / name).mkdir()
    graph.serialize(out / "rdf/full.nt", format="nt")
    edges = sorted(edges)
    with (out / "rdf/graph.nt").open("w") as f:
        for s, p, t in edges:
            f.write(f"<{BASE}{nodes[s]}> <{BASE}{labels[p]}> <{BASE}{nodes[t]}> .\n")
    write_csv(out / "csv/nodes.csv", ["id", "name", "iri"],
              ((i, name, BASE+name) for i, name in nodes.items()))
    write_csv(out / "csv/vertices.csv", ["id"], ((i,) for i in nodes))
    write_csv(out / "csv/edges.csv", ["src", "pid", "dst"], edges)
    for pid, label in labels.items():
        write_csv(out / f"csv/edges_{label}.csv", ["src", "dst"],
                  ((s, t) for s, p, t in edges if p == pid))
    dat = out / "matrix/graph.dat"
    dat.write_text("".join(f"{s} {p} {t}\n" for s, p, t in edges))
    Path(str(dat)+".SO").write_text("".join(f"{i} <{name}>\n" for i, name in nodes.items()))
    Path(str(dat)+".P").write_text("".join(f"{i} <{name}>\n" for i, name in labels.items()))

    def anchor(label):
        return next(s for s, p, t in edges if p == label_ids[label])

    specifications = [
        ("creator", "<creator>", [(0, "creator", 1)], [1], 2),
        ("references", "<references>/<cite>/<creator>", [(0, "references", 1), (1, "cite", 2), (2, "creator", 3)], [3], 4),
        ("coauthor", "(<coauthor>)*", [(0, "coauthor", 0)], [0], 1),
        ("references", "(<references>/<cite>)*", [(0, "references", 1), (1, "cite", 0)], [0], 2),
        ("editor", "(<editor>|<creator>)", [(0, "editor", 1), (0, "creator", 1)], [1], 2),
        ("coauthor", "(<coauthor>)?", [(0, "coauthor", 1)], [0, 1], 2),
    ]
    queries = []
    for qid, (label, regex, transitions, finals, states) in enumerate(specifications, 1):
        q = dict(id=str(qid), source=anchor(label), regex=regex, finals=finals, states=states,
                 transitions=[[s, label_ids[p], t] for s, p, t in transitions])
        q["targets"] = endpoints(edges, q)
        q["count"] = len(q["targets"])
        q["source_name"] = nodes[q["source"]]
        q["pattern"] = f'<{q["source_name"]}> {regex} ?t'
        q["sparql"] = f'BASE <{BASE}> SELECT DISTINCT ?t WHERE {{ {q["pattern"]} }}'
        (out / f'queries/q{qid}.rq').write_text(q["sparql"] + "\n")
        # COUNT uses a DISTINCT subquery to count endpoints, not matching walks.
        (out / f'queries/q{qid}-count.rq').write_text(
            f'BASE <{BASE}> SELECT (COUNT(*) AS ?count) WHERE {{ {{ SELECT DISTINCT ?t WHERE {{ {q["pattern"]} }} }} }}\n')
        (out / f'automata/q{qid}.json').write_text(json.dumps(q, indent=2)+"\n")
        for pid in labels:
            pairs = [(s, t) for s, p, t in q["transitions"] if p == pid]
            (out / f'automata/q{qid}-{pid}.mtx').write_text(
                f'%%MatrixMarket matrix coordinate pattern general\n{states} {states} {len(pairs)}\n'
                + "".join(f"{s+1} {t+1}\n" for s, t in pairs))
        sql = f'''WITH RECURSIVE transitions(q,label,r) AS (VALUES {", ".join(f"({s},{p},{t})" for s,p,t in q["transitions"])}),
reach(v,q) AS (SELECT CAST({q["source"]} AS BIGINT), 0 UNION
SELECT e.dst, t.r FROM reach r JOIN transitions t ON r.q=t.q JOIN edges e ON e.src=r.v AND e.pid=t.label)
SELECT DISTINCT v FROM reach WHERE q IN ({",".join(map(str,finals))}) ORDER BY v;\n'''
        (out / f'queries/q{qid}.sql').write_text(sql)
        queries.append(q)
    (out / "queries/pathrex.txt").write_text("".join(f'{q["id"]},{q["pattern"]}\n' for q in queries))
    (out / "queries/matrix.tsv").write_text("".join(f'{q["id"]} {q["pattern"]}#\n' for q in queries))
    # Upstream Ring's do/getline/while(!eof) parser crashes on a trailing newline.
    (out / "queries/ring.tsv").write_text("\n".join(f'{q["pattern"]}#' for q in queries))
    (out / "queries/larpq.tsv").write_text("".join(
        f'{q["id"]} {q["source"]-1} {q["states"]} {sum(1<<x for x in q["finals"])} {len(q["transitions"])} '
        + " ".join(f"{s} {p-1} {t}" for s,p,t in q["transitions"]) + "\n" for q in queries))
    manifest = dict(source=str(source_dir / "rpqbench_250k.n3"),
                    source_sha256=hashlib.sha256((source_dir / "rpqbench_250k.n3").read_bytes()).hexdigest(),
                    source_rdf_triples=len(graph), projected_source_rows=projected_rows,
                    vertices=len(nodes), edges=len(edges),
                    labels=labels, projection="legacy local-name projection, matching existing matrices; resource edges only; duplicate edges collapsed",
                    local_name_collisions=ambiguous,
                    matches_existing_matrix_graph=True, base_iri=BASE, queries=queries)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(json.dumps({k:v for k,v in manifest.items() if k != "queries"}, indent=2))
    subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "rpqmatrixGB/matrix_market.py"),
                    str(mm), "--output-base", str(out / "matrix-gb/graph.dat"), "--copy"], check=True)
    print("Expected counts:", [(q["id"], q["count"]) for q in queries])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?", default=Path("Datasets/rpq_250k"))
    parser.add_argument("--bootstrap-mm", action="store_true", help="Create missing legacy MatrixMarket inputs using author converters")
    args = parser.parse_args()
    prepare(args.source, args.bootstrap_mm)
