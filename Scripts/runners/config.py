"""Configuration for one sequential benchmark run."""
from dataclasses import dataclass
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = Path(__file__).with_name("config.json")
ENGINES = (
    "pathrex", "larpq", "rpqmatrix", "rpqmatrixGB", "ring", "duckdb", "kuzu",
    "jena", "postgres", "millenniumdb", "blazegraph", "virtuoso", "neo4j",
    "memgraph", "falkordb",
)
NATIVE_COUNTS = {"pathrex": "target_count", "rpqmatrix": "pair_count",
                 "rpqmatrixGB": "pair_count", "ring": "pair_count"}
TOKEN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*")


def repo_path(value):
    return (ROOT / value).resolve()


@dataclass
class Selection:
    engine: str
    directory: Path
    queries: list
    options: dict


def load(path, dataset, engines, ids, query_set=None):
    config = json.loads(path.read_text())
    if not TOKEN.fullmatch(dataset):
        raise ValueError("Invalid dataset name")
    data = config["datasets"][dataset]
    selected = engines or data["engines"]
    if not selected or len(set(selected)) != len(selected) or set(selected) - set(ENGINES):
        raise ValueError("Competitors must be a nonempty list of distinct known engines")
    selections = []
    for engine in selected:
        overridden = data.get("competitors", {}).get(engine, {})
        options = {**config.get("competitors", {}).get(engine, {}), **overridden}
        suite = query_set or options.get("query_set", data["query_set"])
        if not TOKEN.fullmatch(suite):
            raise ValueError(f"Invalid query set for {engine}")
        query_dir = repo_path(options.get("query_dir", f"Queries/{engine}/{dataset}/{suite}"))
        if query_set:
            query_dir = repo_path(f"Queries/{engine}/{dataset}/{suite}")
        catalog = json.loads((query_dir / "manifest.json").read_text())["queries"]
        by_id = {str(q["id"]): q for q in catalog}
        if len(by_id) != len(catalog):
            raise ValueError(f"{engine}: duplicate query IDs")
        which = [str(qid) for qid in (ids or options.get("query_ids", data.get("query_ids", list(by_id))))]
        if not which or len(set(which)) != len(which) or set(which) - set(by_id):
            raise ValueError(f"{engine}: invalid query IDs {which}; available: {list(by_id)}")
        queries = []
        for qid in which:
            q = dict(by_id[qid], id=qid)
            if not TOKEN.fullmatch(qid):
                raise ValueError(f"{engine}: unsafe query ID {qid!r}")
            mode = q.get("mode", "con-any")
            if mode == "con-any":
                if q.get("count") != len(set(q["targets"])):
                    raise ValueError(f"{engine}/{qid}: count and endpoint oracle disagree")
            else:
                metric = NATIVE_COUNTS.get(engine)
                if mode not in {"any-con", "any-any", "con-con"} or not metric:
                    raise ValueError(f"{engine}/{qid}: unsupported endpoint mode {mode}")
                count = q.get(metric)
                if type(count) is not int or count < 0:
                    raise ValueError(f"{engine}/{qid}: {mode} requires a verified {metric}")
                q["count"], q["count_metric"] = count, metric
            queries.append(q)
        selections.append(Selection(engine, query_dir, queries, options))
    return config, data, selections
