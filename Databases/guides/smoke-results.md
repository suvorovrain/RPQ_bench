# Фактические результаты запуска

Проверка 2026-10-11. Это функциональные проверки, не performance benchmark.
Числитель — совпавшие ответы, знаменатель — все query records, включая gaps.
У Pathrex шесть optimizers, поэтому 36 и 120 records вместо 6 и 20.

Basic4 — новый общий простой набор, проверка 2026-10-18; 4 записи (24 у Pathrex).
Smoke6 / Workload20 — исторические проверки 2026-10-11.

| Движок | Версия / поставка | Basic4 | Smoke6 | Workload20 | Нюанс |
| --- | --- | --- | --- | --- | --- |
| [pathrex](pathrex.md) | source checkout / fresh release build | 24/24 | 30/36 | 114/120 | 6 optimizers: 5/6 smoke; optional unsupported in RPQMatrix. Workload20 q12: target count=1 vs 136 sources. NFA отдельно 6/6. |
| [rpqmatrix](rpqmatrix.md) | existing native executable | 4/4 | 6/6 | 20/20 | Counts, не sets; native variables переименованы в односимвольные. |
| [rpqmatrixGB](rpqmatrixGB.md) | existing native executable / GraphBLAS 10.3.1 | 4/4 | 6/6 | 20/20 | Counts, не sets; .mat = MatrixMarket, не binary baseline. |
| [larpq](larpq.md) | LAGraph 2-rpq / GraphBLAS 10.3.1 | 4/4 | 6/6 | 20/20 | Exact sets; новый minimal C harness, extended any-con format. |
| [ring](ring.md) | pinned Ring + locked author SDSL | 4/4 | 6/6 | 20/20 | Counts; query file без trailing newline; result bound 1M; Debug source build. |
| [millenniumdb](millenniumdb.md) | pinned source mdb 1.0.0 | 4/4 | 6/6 | 20/20 | Exact sets; RDF mode, source build; all-variable zero-length не проверен. |
| [jena](jena.md) | Apache Jena 6.2.0 / Temurin 21 | 4/4 | 6/6 | 20/20 | Exact sets; TDB2 CLI / Java 21 / official binary, не source build. |
| [blazegraph](blazegraph.md) | BLAZEGRAPH_2_1_6_RC / Temurin 21 | 4/4 | 6/6 | 20/20 | Exact sets; RC JAR, explicit NanoSparqlServer, journal / no axioms. |
| [virtuoso](virtuoso.md) | 07.20.3243 | 4/4 | 6/6 | 20/20 | Exact sets; named graph явно указан в FROM. |
| [falkordb](falkordb.md) | official Docker, MODULE LIST in JSON | 4/4 | 5/6 | Не запускался | 5 exact sets; q4 no_translation, не тест unsupported синтаксиса. |
| [memgraph](memgraph.md) | 3.13.2 | 4/4 | 5/6 | Не запускался | 5 exact sets; BFS star требует UNION с zero-length source; q4 no_translation. |
| [neo4j](neo4j.md) | 5.26 Community | 4/4 | 5/6 | Не запускался | 5 exact sets; Neo4j 5.26 Community, не Cypher 25; q4 no_translation. |
| [kuzu](kuzu.md) | Python 0.11.3 | 4/4 | 5/6 | Не запускался | 5 exact sets; 0.11.3; default cap 30, q4 no_translation. |
| [postgres](postgres.md) | official postgres:18 (server version in JSON) | 4/4 | 6/6 | 20/20 | Exact sets; recursive UNION / product states. |
| [duckdb](duckdb.md) | Python 1.5.6 | 4/4 | 6/6 | 20/20 | Exact sets; recursive UNION / product states, без DuckPGQ. |

Все 15 текущих конкурентов были проверены на общей проекции.
Cypher systems покрывают пять переведённых
запросов, а не произвольный regex workload. Нулевые ответы части workload20
не заменяют дополнительные adversarial cases.

## Найденные проблемы и исправления адаптации

- Native matrix/Ring parser ожидает `?t#`. С `?obj#` часть строк молча
  дала 0. После variable renaming обе матрицы и Ring прошли 20/20.
- Ring abort-ился после последнего ответа из-за trailing newline; prepared
  query files её исключают. Upstream source не патчился.
- Memgraph BFS не включил zero-length source для `*BFS 0..`; явный UNION
  с источником исправил endpoint query для label-star.
- Текущий Pathrex RPQMatrix явно не поддерживает `?`; NFA mode прошёл этот
  smoke query. В any-con q12 CLI считает непустые target columns (1),
  остальные evaluators/эталон — 136 distinct sources. До benchmark нужен
  согласованный count contract, а не объявление этой цифры ошибкой relation.
## Воспроизводимость и состояние

Exact commands/stdout/stderr: `Results/competitors_250k/logs/*`.
Машинные query records: [smoke-results.json](smoke-results.json).
Actual source revisions/images/artifact checksums: [runtime-lock.json](runtime-lock.json).
2026-10-18 по запросу пользователя удалены все Docker containers.
Bind-mounted databases, input files, logs и Docker volumes сохранены.
Source dataset, большие prepared inputs и binaries остаются локальными
в игнорируемых Datasets/Results. Результаты воспроизводятся генераторами
и [командами](README.md).
