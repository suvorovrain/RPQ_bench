"""Generate adapters' query files and endpoint oracles for fixed-source RPQs."""
import argparse
from collections import defaultdict, deque
import csv
import json
from pathlib import Path
import re
import string

from Scripts.runners.config import ENGINES, NATIVE_COUNTS, ROOT, TOKEN
from Scripts.runners.workflow import QUERY_FILES

LABEL = re.compile(r"<([^<>]+)>")
EDGE_PATTERN = re.compile(r"(<[^<>]+>)\s+(.+)\s+(\?[A-Za-z_]\w*)")


def mapping(path):
    return {line.rsplit(maxsplit=1)[0].strip("<>"): int(line.rsplit(maxsplit=1)[1])
            for line in path.read_text().splitlines() if line.strip()}


def compile_catalog(path, graph, prepared, base):
    from pyformlang.regular_expression import PythonRegex

    nodes, labels = (mapping(graph / source) for source in ("vertices.txt", "edges.txt"))
    adjacency = defaultdict(list)
    with (prepared / "csv/edges.csv").open() as stream:
        for row in csv.DictReader(stream):
            adjacency[int(row["src"]), int(row["pid"])].append(int(row["dst"]))
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        qid, pattern = line.strip().split(",", 1)
        match = EDGE_PATTERN.fullmatch(pattern.strip())
        if not match:
            raise ValueError(f"{qid}: expected <fixed-source> <RPQ> ?variable")
        source, regex, _ = match.groups()
        if not re.fullmatch(r"[()/|*+?\s]*", LABEL.sub("", regex)):
            raise ValueError(f"{qid}: use labels, /, |, *, + and ?")
        names = list(dict.fromkeys(LABEL.findall(regex)))
        if len(names) > len(string.ascii_letters):
            raise ValueError(f"{qid}: too many distinct labels")
        chars = dict(zip(names, string.ascii_letters))
        pids = {char: labels[name] for name, char in chars.items()}
        expression = LABEL.sub(lambda m: chars[m[1]], regex)
        expression = re.sub(r"[/\s]+", "", expression)
        dfa = PythonRegex(expression).to_epsilon_nfa().to_deterministic().minimize()
        states = {state: i for i, state in enumerate(sorted(dfa.states, key=str))}
        starts = [states[state] for state in dfa.start_states]
        finals = [states[state] for state in dfa.final_states]
        transitions = [(states[start], pids[str(symbol.value)], states[end])
                       for start, row in dfa.to_dict().items() for symbol, end in row.items()]
        edges = defaultdict(list)
        for start, label, end in transitions:
            edges[start].append((label, end))
        source_id = nodes[source.strip("<>")]
        result = set()
        seen = {(source_id, state) for state in starts}
        queue = deque(seen)
        while queue:
            node, state = queue.popleft()
            if state in finals:
                result.add(node)
            for pid, end in edges[state]:
                for target in adjacency[node, pid]:
                    pair = target, end
                    if pair not in seen:
                        seen.add(pair)
                        queue.append(pair)
        yield {"id": qid, "pattern": f"{source} {regex} ?t",
               "sparql": f"BASE <{base}> SELECT DISTINCT ?t WHERE {{ {source} {regex} ?t }}",
               "source": source_id, "starts": starts, "finals": finals,
               "states": len(states), "transitions": transitions,
               "targets": sorted(result), "count": len(result)}


def sql(q):
    values = ", ".join(f"({s},{p},{t})" for s, p, t in q["transitions"])
    if not values:
        values = "(NULL::INTEGER,NULL::INTEGER,NULL::INTEGER)"
    seeds = ", ".join(f"(CAST({q['source']} AS BIGINT),{state})" for state in q.get("starts", [0]))
    finals = ",".join(map(str, q["finals"])) or "NULL"
    return (f"WITH RECURSIVE transitions(q,label,r) AS (VALUES {values}),\n"
            f"reach(v,q) AS (VALUES {seeds} UNION SELECT e.dst,t.r FROM reach r "
            "JOIN transitions t ON r.q=t.q JOIN edges e ON e.src=r.v AND e.pid=t.label)\n"
            f"SELECT DISTINCT v FROM reach WHERE q IN ({finals}) ORDER BY v;\n")


def write_suite(queries, engine, out):
    ids = [str(q["id"]) for q in queries]
    if len(ids) != len(set(ids)) or any(not TOKEN.fullmatch(qid) for qid in ids):
        raise ValueError("Invalid or repeated query IDs")
    output_files = {"manifest.json": json.dumps({"queries": queries}, indent=2) + "\n"}
    if engine in QUERY_FILES:
        name, separator = QUERY_FILES[engine]
        if engine == "pathrex":
            lines = [f'{q["id"]},{q["pattern"]}' for q in queries]
        elif engine == "larpq":
            lines = []
            for q in queries:
                if q["states"] > 63 or not str(q["id"]).isdecimal():
                    raise ValueError("LA-RPQ requires numeric query IDs and at most 63 automaton states")
                if q.get("starts", [0]) != [0]:
                    # The timed driver uses start state zero. Remap the DFA without changing the oracle.
                    states = [q["starts"][0]] + [i for i in range(q["states"]) if i not in q["starts"]]
                    remap = {state: i for i, state in enumerate(states)}
                else:
                    remap = {i: i for i in range(q["states"])}
                mask = sum(1 << remap[f] for f in q["finals"])
                arcs = q["transitions"]
                lines.append(f'{q["id"]} {q["source"]-1} {q["states"]} {mask} {len(arcs)} '
                             + " ".join(f"{remap[s]} {p-1} {remap[t]}" for s,p,t in arcs))
        elif separator is None:
            lines = [matrix_pattern(q) + "#" for q in queries]
        else:
            lines = [f'{q["id"]} {matrix_pattern(q)}#' for q in queries]
        output_files[name] = "\n".join(lines) + ("\n" if separator else "")
    elif engine in {"postgres", "duckdb"}:
        output_files.update({f'q{q["id"]}.sql': sql(q) for q in queries})
    elif engine in {"jena", "blazegraph", "virtuoso", "millenniumdb"}:
        output_files.update({f'q{q["id"]}.rq': q["sparql"] + "\n" for q in queries})
    out.mkdir(parents=True, exist_ok=True)
    for name, value in output_files.items():
        target = out / name
        if target.exists() and target.read_text() != value:
            raise FileExistsError(f"{target} differs. Choose a new --suite or --output-root.")
    for name, value in output_files.items():
        target = out / name
        if not target.exists():
            target.write_text(value)


def matrix_pattern(query):
    subject, rest = query["pattern"].strip().split(maxsplit=1)
    expression, obj = rest.rsplit(maxsplit=1)
    if subject.startswith("?"):
        if subject == obj:
            raise ValueError(f"{query['id']}: matrix and Ring adapters require different endpoint variables")
        subject = "?s"
    if obj.startswith("?"):
        obj = "?t"
    return f"{subject} {expression} {obj}"


def main(default_engine=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="rpq_250k")
    parser.add_argument("--engines", nargs="+", choices=ENGINES, default=[default_engine] if default_engine else ENGINES)
    parser.add_argument("--suite", default="basic4")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--catalog", type=Path, help="id,<fixed-source> <RPQ> ?target. Builds oracle on the supplied CSV graph.")
    source.add_argument("--manifest", type=Path, help="Use a prepared, verified query manifest instead of building the oracle.")
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--graph", type=Path)
    parser.add_argument("--output-root", type=Path, default=ROOT / "Queries")
    args = parser.parse_args()
    if any(not TOKEN.fullmatch(x) for x in (args.dataset, args.suite)):
        parser.error("Invalid dataset or suite name")
    if default_engine and args.engines != [default_engine]:
        parser.error(f"This converter prepares {default_engine}")
    dataset = ROOT / "Datasets" / args.dataset
    prepared = args.prepared or dataset / "prepared"
    graph = args.graph or dataset / "pathrex"
    if args.catalog:
        base = json.loads((prepared / "manifest.json").read_text())["base_iri"]
        queries = list(compile_catalog(args.catalog, graph, prepared, base))
    elif args.manifest:
        queries = json.loads(args.manifest.read_text())["queries"]
    elif args.dataset == "rpq_250k" and args.suite == "basic4":
        source = json.loads((prepared / "manifest.json").read_text())["queries"]
        queries = [dict(q, suite="basic4") for q in source if str(q["id"]) in {"1", "2", "3", "5"}]
        if len(queries) != 4:
            parser.error("Expected 4 Basic4 queries in prepared graph manifest")
    else:
        parser.error("Supply --catalog or --manifest")
    if not queries:
        parser.error("Empty query suite")
    for engine in args.engines:
        out = args.output_root / engine / args.dataset / args.suite
        for q in queries:
            if q.get("mode", "con-any") != "con-any":
                metric = NATIVE_COUNTS.get(engine)
                if not metric or type(q.get(metric)) is not int or q[metric] < 0:
                    parser.error(f"{engine}/{q['id']}: expected fixed-source query or verified {metric or 'oracle'}")
        write_suite(queries, engine, out)
        print(f"{engine}: {len(queries)} queries -> {out}")


if __name__ == "__main__":
    main()
