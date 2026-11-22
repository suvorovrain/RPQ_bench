# Подробные гайды запуска на rpqbench_250k

Общий обзор всех 15 систем, статусы подключения, новый Basic4 и полный путь
N3/NT→форматы находятся в [Databases/README.md](../README.md).
Этот документ дополняет обзор техническими деталями прежних smoke-наборов.

Проверка 2026-10-11. Здесь 15 отдельных гайдов, подготовленные входы, запросы
и фактические результаты запусков. Исходники submodules и бинарные поставки —
разные версии: Docker digest, JAR checksum и source SHA записаны в
[runtime-lock.json](runtime-lock.json). Общий benchmark runner пока не расширен;
[smoke_250k.py](../../Scripts/competitors/smoke_250k.py) — отдельный проверочный
runner с импортом и сравнением ответов, без performance ranking.

## Навигация

| Конкурент | Гайд | Вход |
| --- | --- | --- |
| Pathrex / оптимизаторы | [pathrex](pathrex.md) | MatrixMarket, SPARQL patterns |
| rpqmatrix | [rpqmatrix](rpqmatrix.md) | `.dat`, `.SO`, `.P`, binary matrix index |
| rpqmatrixGB | [rpqmatrixGB](rpqmatrixGB.md) | словари и MatrixMarket `.mat` |
| LARPQ | [larpq](larpq.md) | GraphBLAS graph + NFA; наш C harness |
| Ring-RPQ | [ring](ring.md) | `.dat`, словари, Ring index |
| MillenniumDB | [millenniumdb](millenniumdb.md) | N-Triples → RDF database, SPARQL |
| Jena TDB2 | [jena](jena.md) | N-Triples → TDB2, SPARQL |
| Blazegraph | [blazegraph](blazegraph.md) | N-Triples → journal, SPARQL |
| Virtuoso | [virtuoso](virtuoso.md) | N-Triples → named graph, SPARQL |
| FalkorDB | [falkordb](falkordb.md) | CSV → property graph, Cypher |
| Memgraph | [memgraph](memgraph.md) | CSV → property graph, Cypher/BFS |
| Neo4j | [neo4j](neo4j.md) | CSV → property graph, Cypher |
| Kuzu | [kuzu](kuzu.md) | CSV → typed node/relationship tables, Cypher |
| PostgreSQL | [postgres](postgres.md) | CSV → edges table, recursive SQL |
| DuckDB | [duckdb](duckdb.md) | CSV → edges table, recursive SQL |

Фактические версии, проверки и ошибки собраны в [smoke-results.md](smoke-results.md)
и [smoke-results.json](smoke-results.json).
[Отдельная проверка контракта](contract.md) сопоставляет API/CLI Pathrex и LARPQ
с остальными системами и фиксирует различия на циклах, bindings и zero-length.
Подробные логи находятся локально в
[Results/competitors_250k/logs](../../Results/competitors_250k/logs/).

## Один датасет для всех движков

Источник: [rpqbench_250k.n3](../../Datasets/rpqbench_250k/rpqbench_250k.n3).
Несмотря на расширение, файл использует префиксы и typed literals; его нельзя
передать как N-Triples без разбора/преобразования. Полный RDF содержит
**249 739 уникальных троек**. Для сравнения с имеющимися матрицами используется
другая, уже существовавшая в проекте проекция: **24 225 вершин, 9 меток,
63 052 исходных строк рёбер, 61 017 уникальных рёбер**.

Принципиальный нюанс: старое преобразование снимает namespace и сохраняет только
локальные имена. Разные оригинальные IRI могут слиться, например журналы одного
года. Blank nodes с явными `_:` именами также превращаются в именованные
вершины. Это не изоморфная конвертация полного RDF. Новый скрипт проверяет
равенство множества рёбер старым матрицам, сохраняет IDs и перечисляет коллизии
в manifest. Все smoke-движки получают эту одну проекцию; исходные файлы и матрицы
не перезаписываются. Дубликаты схлопнуты для set reachability; для path/multigraph
benchmark потребуется отдельный контракт кратности рёбер.

[prepare_250k.py](../../Scripts/competitors/prepare_250k.py) специально рассчитан
на этот плоский генераторный файл и существующие словари, а не на любой N3.
Полный файл валидируется RDFLib, проекция сверяется по исходным лексическим
именам blank nodes. Для произвольного нового датасета сначала нужен общий RDF
разбор с сохранением полных IRI/blank-node identity и новое согласованное
назначение IDs; нельзя переносить сокращение имён без проверки коллизий.

Подготовленные файлы лежат в
[Datasets/rpqbench_250k/prepared](../../Datasets/rpqbench_250k/prepared/):

| Файл / каталог | Содержание |
| --- | --- |
| `rdf/full.nt` | Полный исходный RDF в N-Triples, включая свойства/literals. Не smoke graph. |
| `rdf/graph.nt` | Общая проекция; вершины/предикаты — IRI с base `http://example.org/`. |
| `csv/nodes.csv` | `id,name,iri`; vertex IDs 1-based, 24 225 строк. |
| `csv/vertices.csv` | Только `id`, нужен для zero-length all-pairs SQL. |
| `csv/edges.csv` | `src,pid,dst`; 61 017 уникальных строк. |
| `csv/edges_<label>.csv` | `src,dst` отдельно для каждого из 9 relationship types. |
| `matrix/graph.dat` | Без заголовка, текстовые `subject_id predicate_id object_id`. |
| `matrix/graph.dat.SO`, `.P` | `id <short_name>`; IDs совпадают с существующими матрицами. |
| `matrix/graph.dat.baseline-64/` | Binary CSR/CSC index, построенный baseline_build. |
| `matrix/graph.dat.*` | Дополнительные Ring index files после запуска Ring. |
| `matrix-gb/graph.dat.*` | Отдельный GB layout; `.mat` здесь MatrixMarket, не binary baseline. |
| `automata/` | JSON и per-label MatrixMarket для шести smoke NFA. |
| `queries/` | SPARQL, SQL и native-query files; Cypher-файлы после соответствующего smoke. |
| `workload20/` | 20 upstream шаблонов с фиксированными bindings, SPARQL, SQL, NFA и эталоном. |
| `manifest.json` | SHA256 источника, параметры графа, коллизии и точные smoke endpoint sets. |

Эти большие/машинные файлы остаются локальными: `Datasets/*/` и `Results/`
игнорируются Git. В репозитории сохраняются генераторы, инструкции, lock и
компактный отчёт. Наличие `rdf/full.nt` не означает, что все движки тестировались
на полном RDF: запускается `rdf/graph.nt` или эквивалентные CSV/матрицы.

## Подготовка окружения и запуск

Все команды — из корня RPQ_bench. Нужны Python 3.12 (зафиксированные wheel
versions), Docker, для native builds — CMake/GCC/G++/OpenMP и Rust для Pathrex.
Java на хосте не требуется: использован Temurin 21 в Docker. Проверка использует
2 threads/CPU и до 2 GB на контейнер; native library compilation запускается
с `-j 2`, поскольку рабочая машина имеет 16 GB RAM.

```bash
mkdir -p Results/competitors_250k/logs Results/competitors_250k/tools
python3 -m venv Results/competitors_250k/venv
Results/competitors_250k/venv/bin/pip install -r Scripts/competitors/requirements.txt
Results/competitors_250k/venv/bin/python Scripts/competitors/download_tools.py --images
```

На новой копии, где `prepared/` ещё отсутствует:

```bash
Results/competitors_250k/venv/bin/python Scripts/competitors/prepare_250k.py --bootstrap-mm
Results/competitors_250k/venv/bin/python Scripts/competitors/prepare_workload.py
```

`prepare_250k.py` отказывается перезаписывать `prepared/`. Уже подготовленную
директорию использовать сразу. Native executables построить по
[build-native.md](build-native.md) и гайдам соответствующих движков.

Пример полного smoke-цикла одного движка:

```bash
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py postgres
```

Варианты: `pathrex`, `rpqmatrix`, `rpqmatrixGB`, `larpq`, `ring`, `millenniumdb`,
`jena`, `blazegraph`, `virtuoso`, `falkordb`, `memgraph`, `neo4j`, `kuzu`,
`postgres`, `duckdb`. Запускать последовательно: ограничения
ресурсов относятся к каждому движку, а не ко всей группе.

Runner сам создаёт новую БД/импортирует граф, исполняет запросы и пишет
`Results/competitors_250k/<engine>.json`. При error/mismatch exit code — 1;
unsupported/no_translation/not_checked отражаются как gaps в JSON. Созданные серверы останавливаются после
проверки. Bind-mounted базы и логи сохраняются. При повторении удаляется только
остановленный контейнер с собственным label `rpq-bench.smoke=250k`; запущенные
или чужие контейнеры не изменяются. SQL Docker DB могут храниться в anonymous
volumes; этот smoke не заменяет persistent compose setup для benchmark.

Для ручной работы с уже созданным контейнером:

```bash
docker start rpq-bench-250k-postgres
docker logs rpq-bench-250k-postgres
docker stop rpq-bench-250k-postgres
```

Порты привязаны к localhost: Postgres 15542, Neo4j 17687,
Memgraph 17688, FalkorDB 16389, Blazegraph 19999, Virtuoso 18891.
MillenniumDB native HTTP server использует 12345. Если порт занят, изменить
runner/гайд согласованно; не останавливать чужой сервис.

## Запросы и границы проверки

Шесть con-any запросов используют одинаковые bindings во всех двигателях.
Эталон построен независимым Python обходом произведения графа и автомата.

| ID | Source | RPQ | Distinct targets |
| --- | --- | --- | --- |
| 1 | Article1 | creator | 56 |
| 2 | Article1 | references/cite/creator | 109 |
| 3 | Tashiya_Marrable | coauthor* | 3 |
| 4 | Article1 | (references/cite)* | 51 |
| 5 | 1940 | editor OR creator | 1 |
| 6 | Tashiya_Marrable | coauthor? | 2 |

В RDF/SQL/LARPQ проверяются точные endpoint sets; матричные CLI, Ring и Pathrex
выдают counts, поэтому проверка там слабее: только cardinality. В пересобранном текущем Pathrex RPQMatrix q6 (`?`) явно unsupported; NFA режим
отдельно прошёл 6/6. В наборе20 any-con q12 выявил CLI count contract: distinct
targets (1) против distinct sources (136). Это требуется согласовать до benchmark.
Cypher smoke пропускает q4 как `no_translation`: эквивалентный перевод
compound closure ещё не реализован, это не результат runtime-теста поддержки
произвольного regex. Совпадение остальных пяти не доказывает полный WALK RPQ.

[prepare_workload.py](../../Scripts/competitors/prepare_workload.py) берёт 20
[upstream шаблонов](../../vendor/larpq/Datasets/RPQBench/sparql-queries-templates.txt),
фиксирует bindings и строит epsilon-free DFA, SQL и эталон. Для any-con
используются обратные переходы автомата и обратный граф. Это демонстрационный
workload с некоторыми пустыми ответами, а не восстановление опубликованной
random-source выборки. Шесть smoke-запросов и эти двадцать — разные наборы;
успех первого не означает проверку второго.

Расширенный запуск для систем с полным подготовленным adapter:

```bash
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py postgres --workload20
```

Поддерживаются Pathrex, обе матрицы, LARPQ, Ring, MillenniumDB, Jena, Blazegraph,
Virtuoso, PostgreSQL и DuckDB. У Cypher полный adapter20 не заявлен.
Отдельные JSON/logs имеют суффикс `-workload20`, six-test результаты сохраняются.

Для будущего общего workload нужны отдельно: inverse, all-pairs, Boolean,
zero-length universe, петли/циклы, повторное использование рёбер и глубина
больше Kuzu default. В all-pairs SQL visited key включает source; в single-source
достаточно `(vertex,state)`. В рекурсию для endpoint fixpoint нельзя бездумно
добавлять depth/path: разные depth/path строки перестают дедуплицироваться.

## Как из этого делать benchmark

Импорт, построение индексов и RPQ→DFA/SQL preparation измерять отдельно от
query execution. Прогревать один уже загруженный граф, повторять запросы в том
же процессе, фиксировать threads/memory/timeouts и планы. Наш smoke перезапускает
некоторые CLI и не даёт сопоставимых performance numbers. RDF entailment
выключить; named/default graph выбирать явно. `COUNT(*)` над путями не равно
числу distinct endpoints: для SPARQL нужен DISTINCT subquery, для Cypher —
DISTINCT endpoint, для SQL — дедупликация product states и конечной проекции.

Первичные источники по синтаксису, импортам и ограничениями приведены в каждом
гайде; академическая классификация остаётся в [reachability.md](../reachability.md).

## Проверка runner перед переносом на сервер

```bash
python3 -m unittest discover -s Scripts/competitors/tests -v
python3 Scripts/competitors/smoke_250k.py --help
python3 Scripts/competitors/benchmark_all.py --help
```

Обе справки доступны без подготовленных данных. Входной N3 и generated inputs
не хранятся в Git: перед bootstrap скопировать `rpqbench_250k.n3` в
`Datasets/rpqbench_250k/`. Новый `--output` smoke-runner позволяет сохранить
проверку отдельно от исторических результатов:

```bash
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py pathrex \
  --basic --output Results/competitor-review/smoke
```

Текущий Pathrex smoke проверяет два режима (`none`, `pang-hybrid`):
8 records для Basic4, 12 для Smoke6 и 40 для Workload20. Числа с шестью
оптимизаторами в сохранённых JSON относятся к историческому запуску.

Актуальное [ревью и проверка всех 15 adapters от 22 ноября](review-20261122.md)
отделены от исторических smoke-отчётов.
