#!/usr/bin/env python3
"""Summarize actual local smoke records into small, reviewable checked-in docs."""
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Results/competitors_250k"
GUIDES = ROOT / "Databases/guides"
ENGINES = ["pathrex", "rpqmatrix", "rpqmatrixGB", "larpq", "ring", "millenniumdb", "jena",
           "blazegraph", "virtuoso", "falkordb", "memgraph", "neo4j", "kuzu",
           "postgres", "duckdb"]


def compact(path):
    if not path.exists():
        return None
    result = json.loads(path.read_text())
    return {k:v for k,v in result.items() if k not in ("outputs", "commands", "output", "output_excerpt", "import_response")}


def stats(result):
    if result is None:
        return "Не запускался"
    if result.get("status") == "failed" and not result.get("checks"):
        return "Сбой до ответов"
    counts = Counter(c["status"] for c in result.get("checks", []))
    return f'{counts["pass"]}/{len(result.get("checks", []))}'


def main():
    source = json.loads((ROOT / "Datasets/rpqbench_250k/prepared/manifest.json").read_text())
    report = dict(date="2026-10-11", source_sha256=source["source_sha256"],
                  source_rdf_triples=source["source_rdf_triples"],
                  projected_source_rows=source["projected_source_rows"],
                  unique_edges=source["edges"], vertices=source["vertices"],
                  local_name_collision_groups=len(source["local_name_collisions"]),
                  engines={})
    notes = {
        "pathrex":"6 optimizers: 5/6 smoke; optional unsupported in RPQMatrix. Workload20 q12: target count=1 vs 136 sources. NFA отдельно 6/6.",
        "rpqmatrix":"Counts, не sets; native variables переименованы в односимвольные.",
        "rpqmatrixGB":"Counts, не sets; .mat = MatrixMarket, не binary baseline.",
        "larpq":"Exact sets; новый minimal C harness, extended any-con format.",
        "ring":"Counts; query file без trailing newline; result bound 1M; Debug source build.",
        "millenniumdb":"Exact sets; RDF mode, source build; all-variable zero-length не проверен.",
        "jena":"Exact sets; TDB2 CLI / Java 21 / official binary, не source build.",
        "blazegraph":"Exact sets; RC JAR, explicit NanoSparqlServer, journal / no axioms.",
        "virtuoso":"Exact sets; named graph явно указан в FROM.",
        "falkordb":"5 exact sets; q4 no_translation, не тест unsupported синтаксиса.",
        "memgraph":"5 exact sets; BFS star требует UNION с zero-length source; q4 no_translation.",
        "neo4j":"5 exact sets; Neo4j 5.26 Community, не Cypher 25; q4 no_translation.",
        "kuzu":"5 exact sets; 0.11.3; default cap 30, q4 no_translation.",
        "postgres":"Exact sets; recursive UNION / product states.",
        "duckdb":"Exact sets; recursive UNION / product states, без DuckPGQ.",
    }
    versions = {
        "pathrex":"source checkout / fresh release build", "rpqmatrix":"existing native executable",
        "rpqmatrixGB":"existing native executable / GraphBLAS 10.3.1", "larpq":"LAGraph 2-rpq / GraphBLAS 10.3.1",
        "ring":"pinned Ring + locked author SDSL", "millenniumdb":"pinned source mdb 1.0.0",
        "jena":"Apache Jena 6.2.0 / Temurin 21", "blazegraph":"BLAZEGRAPH_2_1_6_RC / Temurin 21",
        "virtuoso":"07.20.3243", "falkordb":"official Docker, MODULE LIST in JSON",
        "memgraph":"3.13.2", "neo4j":"5.26 Community", "kuzu":"Python 0.11.3",
        "postgres":"official postgres:18 (server version in JSON)", "duckdb":"Python 1.5.6",
    }
    lines = ["# Фактические результаты запуска", "", "Проверка 2026-10-11. Это функциональные проверки, не performance benchmark.",
             "Числитель — совпавшие ответы, знаменатель — все query records, включая gaps.",
             "У Pathrex шесть optimizers, поэтому 36 и 120 records вместо 6 и 20.", "",
             "Basic4 — новый общий простой набор, проверка 2026-10-18; 4 записи (24 у Pathrex).",
             "Smoke6 / Workload20 — исторические проверки 2026-10-11.", "",
             "| Движок | Версия / поставка | Basic4 | Smoke6 | Workload20 | Нюанс |",
             "| --- | --- | --- | --- | --- | --- |"]
    for engine in ENGINES:
        basic = compact(OUT / f"{engine}.json")
        extended = compact(OUT / f"{engine}-workload20.json")
        simple = compact(OUT / f"{engine}-basic.json")
        report["engines"][engine] = dict(basic4=simple, smoke6=basic, workload20=extended, note=notes[engine])
        lines.append(f"| [{engine}]({engine}.md) | {versions[engine]} | {stats(simple)} | {stats(basic)} | {stats(extended)} | {notes[engine]} |")
    nfa = json.loads((OUT / "pathrex-nfarpq.json").read_text())
    report["pathrex_nfarpq_smoke6"] = nfa["results"]
    lines += ["", "Все 15 текущих конкурентов были проверены на общей проекции.",
              "Cypher systems покрывают пять переведённых",
              "запросов, а не произвольный regex workload. Нулевые ответы части workload20",
              "не заменяют дополнительные adversarial cases.", "",
              "## Найденные проблемы и исправления адаптации", "",
              "- Native matrix/Ring parser ожидает `?t#`. С `?obj#` часть строк молча",
              "  дала 0. После variable renaming обе матрицы и Ring прошли 20/20.",
              "- Ring abort-ился после последнего ответа из-за trailing newline; prepared",
              "  query files её исключают. Upstream source не патчился.",
              "- Memgraph BFS не включил zero-length source для `*BFS 0..`; явный UNION",
              "  с источником исправил endpoint query для label-star.",
              "- Текущий Pathrex RPQMatrix явно не поддерживает `?`; NFA mode прошёл этот",
              "  smoke query. В any-con q12 CLI считает непустые target columns (1),",
              "  остальные evaluators/эталон — 136 distinct sources. До benchmark нужен",
              "  согласованный count contract, а не объявление этой цифры ошибкой relation.",
              "## Воспроизводимость и состояние", "",
              "Exact commands/stdout/stderr: `Results/competitors_250k/logs/*`.",
              "Машинные query records: [smoke-results.json](smoke-results.json).",
              "Actual source revisions/images/artifact checksums: [runtime-lock.json](runtime-lock.json).",
              "2026-10-18 по запросу пользователя удалены все Docker containers.",
              "Bind-mounted databases, input files, logs и Docker volumes сохранены.",
              "Source dataset, большие prepared inputs и binaries остаются локальными",
              "в игнорируемых Datasets/Results. Результаты воспроизводятся генераторами",
              "и [командами](README.md)."]
    (GUIDES / "smoke-results.json").write_text(json.dumps(report, indent=2)+"\n")
    (GUIDES / "smoke-results.md").write_text("\n".join(lines)+"\n")
    lock_path = GUIDES / "runtime-lock.json"
    lock = json.loads(lock_path.read_text())
    lock["native_binaries"] = {}
    for engine, relative in {
        "pathrex":"Databases/pathrex/target/release/pathrex",
        "rpqmatrix":"Databases/rpq-matrix/build/baseline_query",
        "rpqmatrixGB":"Databases/rpq-matrix_GB/build/baselineGB_query",
        "larpq":"Results/competitors_250k/build/larpq-smoke",
        "millenniumdb":"Results/competitors_250k/build/millenniumdb/bin/mdb",
        "ring_build":"Results/competitors_250k/build/ring/build-index-basic",
        "ring_query":"Results/competitors_250k/build/ring/query-index-basic",
    }.items():
        lock["native_binaries"][engine] = dict(path=relative, sha256=hashlib.sha256((ROOT / relative).read_bytes()).hexdigest())
    (GUIDES / "runtime-lock.json").write_text(json.dumps(lock, indent=2)+"\n")
    print("Recorded",len(ENGINES),"engines")


if __name__ == "__main__":
    main()
