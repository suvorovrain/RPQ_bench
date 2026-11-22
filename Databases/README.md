# Конкуренты RPQ: форматы, конвертация и запуск

> Актуальные команды запуска находятся в [гайде раннера](../Scripts/runners/README.md),
> а подготовка входов — в [гайде конвертеров](../Scripts/converters/README.md).
> Ниже сохранены команды исторической серии.

Актуальный набор — **15 систем**. Общий простой набор на `rpqbench_250k`
проверяется **2026-10-18**. Команды выполняются из корня `RPQ_bench`.
Это функциональная проверка; общий performance runner пока поддерживает только
Pathrex и две матричные реализации.

LA-RPQ — алгоритмическая ветка LAGraph `2-rpq` в `Databases/larpq`.
Авторские preprocessing scripts — в **`vendor/larpq`** (upstream `la-rpq`).
`mdb` — executable MillenniumDB. `rinq-rpq` из списка трактуется как
**Ring-RPQ**; runner принимает оба написания. Checkout paths не переименованы.

## Все конкуренты и их форматы

| Система | Checkout / подробный гайд | Формат графа для нашего запуска | Формат запроса | CLI name |
| --- | --- | --- | --- | --- |
| la-rpq | [larpq](guides/larpq.md), `larpq/` | Boolean GraphBLAS decomposition; harness читает `graph.dat` | ε-free NFA; наш `larpq.tsv` | `la-rpq` |
| rpq-matrix | [rpqmatrix](guides/rpqmatrix.md), `rpq-matrix/` | `.dat` + `.SO` + `.P` → binary CSR/CSC index | `id source regex target#`, `matrix.tsv` | `rpq-matrix` |
| rpq-matrix_gb | [rpqmatrixGB](guides/rpqmatrixGB.md), `rpq-matrix_GB/` | словари + per-label MatrixMarket `.mat` | native `matrix.tsv` | `rpq-matrix_gb` |
| pathrex | [pathrex](guides/pathrex.md), `pathrex/` | MatrixMarket: `vertices.txt`, `edges.txt`, `N.txt` | `id,SPARQL property-path pattern` | `pathrex` |
| blazegraph | [blazegraph](guides/blazegraph.md), `blazegraph/` | N-Triples → journal | SPARQL SELECT DISTINCT, HTTP | `blazegraph` |
| DuckDB | [duckdb](guides/duckdb.md), `duckdb/` | CSV → `edges(src,pid,dst)` | recursive SQL по произведению графа и автомата | `duckdb` |
| Jena | [jena](guides/jena.md), `jena/` | N-Triples → TDB2 | SPARQL SELECT DISTINCT, CLI | `jena` |
| Kuzu | [kuzu](guides/kuzu.md), `kuzu/` | CSV → node/relationship tables | Cypher через Python API | `kuzu` |
| Memgraph | [memgraph](guides/memgraph.md), `memgraph/` | CSV → property graph | Cypher/BFS, Bolt | `memgraph` |
| mdb / MillenniumDB | [millenniumdb](guides/millenniumdb.md), `millenniumdb/` | N-Triples → RDF database | SPARQL, native HTTP server | `mdb` |
| Neo4j | [neo4j](guides/neo4j.md), `neo4j/` | CSV → property graph | Cypher, Bolt | `neo4j` |
| PostgreSQL | [postgres](guides/postgres.md), `postgres/` | CSV → `edges(src,pid,dst)` + indexes | recursive SQL, psycopg/psql | `postgres` |
| Ring-RPQ | [ring](guides/ring.md), `ring-rpq/` | `.dat` + `.SO` + `.P` → Ring index | `source regex target#`, `ring.tsv` | `ring-rpq` |
| Virtuoso | [virtuoso](guides/virtuoso.md), `virtuoso/` | N-Triples → named RDF graph | SPARQL с явно выбранным graph | `virtuoso` |
| FalkorDB | [falkordb](guides/falkordb.md), `falkordb/` | CSV → property graph | Cypher через Redis GRAPH.QUERY | `falkordb` |

Submodule означает наличие исходников. Запущенные Docker/JAR/wheel версии
могут отличаться от checkout: [runtime-lock.json](guides/runtime-lock.json)
хранит image digests, JAR checksums, source SHAs и native binary hashes.

## Что уже подключено и чего не хватало

«Было» означает состояние до интеграции соответствующего конкурента в проект.
Основные adapters сделаны ранее; Basic4, bootstrap из N3 и общий RDF-конвертер
добавлены при приведении набора к этим 15 системам.

| Система | Чего не хватало / что теперь сделано | Что остаётся |
| --- | --- | --- |
| la-rpq | Был library API без нашего CLI; добавлены C harness, загрузка графа/NFA, inverse adapter | Performance adapter; any-any с сохранением sources |
| rpq-matrix | Runner уже был; добавлены общие данные, отдельный index и проверки | Пересборка с зафиксированными flags для timings; CLI проверяет count |
| rpq-matrix_gb | Runner уже был; согласован MM→GB layout и общий набор | Проверка relation sets вместо только count |
| pathrex | CLI/optimizers уже были; пересобран binary, проверены 6 optimizers | CLI считает targets; any-con/pairs требуют другого счётчика; Matrix не поддерживает `?`; equality endpoints требует исправления |
| blazegraph | Не было JAR/JVM launch, properties, импорта и HTTP adapter | Persistent journal работает; нужна JVM configuration для timings |
| DuckDB | Не было RPQ→automaton→recursive SQL и импорта | Работает; отдельно измерять preparation/execution |
| Jena | Не было согласованной Java поставки, TDB2 import и query adapter | Работает; CLI запускает JVM, это учитывать в timings |
| Kuzu | Не было schema/COPY/Python adapter | Подмножество работает; default max hops 30, compound regex не переведён |
| Memgraph | Не было import/Bolt/BFS adapter; добавлен zero-length UNION для BFS | Полный WALK/compound regex adapter не готов |
| mdb | Не было Boost headers/source build и adapter нового CLI `mdb` | RDF mode работает; zero-length any-any corner case отдельно не проверен |
| Neo4j | Не было CSV import, ID constraint и Bolt adapter | Один MATCH запрещает повторять ребро; общий regex adapter не готов |
| PostgreSQL | Не было общего RPQ→SQL, COPY и индексов | Работает; performance integration отдельно |
| Ring-RPQ | Не было author SDSL, build/index и driver adapter; исправлена подготовка query EOF | Сейчас Debug build; result bound 1M, CLI выдаёт count |
| Virtuoso | Не было NT bulk import, buffers и named-graph adapter | Работает; контролировать server/result limits |
| FalkorDB | Не было property-graph import и Redis/Cypher adapter | Подмножество работает; compound closure перевод ещё не готов |

## Подготовка окружения

Нужны Linux, Git, Python **3.12**, Docker; для native builds — GCC/G++, CMake,
OpenMP и Rust **1.90+** для Pathrex. Java на хосте не обязательна: используется
закреплённый Temurin 21 image. Команды native сборки/зависимостей находятся в
[build-native.md](guides/build-native.md), Pathrex/матриц — в их отдельных гайдах.

```bash
mkdir -p Results/competitors_250k/logs Results/competitors_250k/tools
python3 -m venv Results/competitors_250k/venv
Results/competitors_250k/venv/bin/pip install -r Scripts/competitors/requirements.txt
Results/competitors_250k/venv/bin/python Scripts/competitors/download_tools.py --images
```

На новой копии получить checkout командой `git submodule update --init --
<пути из таблицы>`, также `vendor/larpq`, `vendor/GraphBLAS`, `vendor/LAGraph`.
Вложенные зависимости собирать по гайдам; не собирать одновременно все системы.
Для Docker/JAR/wheel запуска source build соответствующего сервера не требуется.

## Тестовый rpqbench_250k: от исходного N3 до всех движков

Источник: `Datasets/rpqbench_250k/rpqbench_250k.n3`. Это N3 с prefixes и typed
literals; нельзя просто назвать файл NT. Полный RDF имеет 249 739 уникальных
triples. Текущий matrix benchmark использует **авторскую resource-edge
проекцию**: 24 225 vertices, 9 labels, 63 052 строки до dedup и **61 017
уникальных edges**. Все 15 систем получают именно этот общий граф.

Авторский pipeline: RPQBench `truncate` → `deprefix-nt` → `remove-dups` →
`nt-to-mm`. Повторение подтвердило совпадение всех edges и vertex IDs:
[conversion-audit.json](guides/conversion-audit.json). Сокращение namespace
объединяет некоторые разные исходные IRI; это унаследованная проекция, не
изоморфный полный RDF. Полный RDF отдельно сохранён в `rdf/full.nt`.

На **новой копии**, где `prepared/` отсутствует:

```bash
Results/competitors_250k/venv/bin/python Scripts/competitors/prepare_250k.py --bootstrap-mm
Results/competitors_250k/venv/bin/python Scripts/competitors/prepare_basic.py
```

`--bootstrap-mm` создаёт отсутствующий `Datasets/rpqbench_250k/pathrex`
авторскими конвертерами. Существующие матрицы использует и сверяет с исходником.
Существующий `prepared/` не перезаписывается: на текущей машине сразу перейти
к запуску или выполнить только `prepare_basic.py`.

Входы в `Datasets/rpqbench_250k/prepared/`:

| Путь | Формат и потребители |
| --- | --- |
| `rdf/graph.nt` | Общая проекция: Jena, Blazegraph, Virtuoso, mdb |
| `csv/nodes.csv` | `id,name,iri`; IDs 1-based; property graph nodes |
| `csv/edges.csv` | `src,pid,dst`; SQL edge table |
| `csv/edges_<label>.csv` | `src,dst`; отдельный relationship type |
| `matrix/graph.dat` | Text `s p o`, 1-based, без header; LA-RPQ/матрица/Ring |
| `matrix/graph.dat.SO`, `.P` | `id <name>`: vertex / predicate dictionaries |
| `matrix/graph.dat.baseline-64/` | Binary matrix index после rpq-matrix build |
| `matrix-gb/graph.dat.*` | GB dictionaries и MatrixMarket `.mat`, другой layout |
| `basic/` | Общие четыре простых запроса: SPARQL, SQL, native, NFA, manifest |
| `queries/`, `workload20/` | Более широкие диагностические наборы с известными gaps |

Pathrex читает `Datasets/rpqbench_250k/pathrex`; подготовка сверяет этот граф.
Индексы создают native tools: смена расширения NT→DAT или binary MAT→MM не
является конвертацией. Большие Datasets/Results и binaries игнорируются Git.

## Общий простой набор и примеры запуска

Используются четыре существующих **con-any** запроса с разными endpoint
variables. Any-con/pairs не сравниваются с target-count CLI Pathrex.

| ID | Pattern | Distinct targets |
| --- | --- | --- |
| 1 | `<Article1> <creator> ?t` | 56 |
| 2 | `<Article1> <references>/<cite>/<creator> ?t` | 109 |
| 3 | `<Tashiya_Marrable> (<coauthor>)* ?t` | 3 |
| 5 | `<1940> (<editor>\|<creator>) ?t` | 1 |

Один полный цикл — import/index, четыре запроса, проверка oracle, JSON/logs,
остановка сервера:

```bash
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py postgres --basic
```

Пример запуска **каждого** выбранного конкурента, последовательно:

```bash
for engine in la-rpq rpq-matrix rpq-matrix_gb pathrex blazegraph duckdb jena kuzu memgraph mdb neo4j postgres ring-rpq virtuoso falkordb
do
  Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py "$engine" --basic || break
done
```

Фактические результаты: [smoke-results.md](guides/smoke-results.md) и
[JSON](guides/smoke-results.json). У Pathrex четыре queries исполняются каждым
из двух optimizers (`none`, `pang-hybrid`) — 8 checks в текущем runner.
Исторические сохранённые отчёты содержат шесть optimizers и 24 checks. У Pathrex/матриц/Ring сравниваются counts,
у остальных — точные endpoint sets; совпадение count не доказывает равенство sets.

Те же простые запросы в конкретных интерфейсах:

```text
# Pathrex: basic/pathrex.txt
1,<Article1> <creator> ?t
# matrix: basic/matrix.tsv; # — терминатор
1 <Article1> <creator> ?t#
# Ring: basic/ring.tsv; без последнего newline
<Article1> <creator> ?t#
```

```sparql
BASE <http://example.org/>
SELECT DISTINCT ?t WHERE { <Article1> <creator> ?t }
```

```cypher
MATCH (s:Node {id:1})-[:creator]->(t:Node) RETURN DISTINCT t.id AS id;
```

```sql
-- Простой label; остальные basic/qN.sql используют DFA + recursive CTE.
SELECT DISTINCT dst FROM edges WHERE src=1 AND pid=2;
```

```bash
# LA-RPQ harness с теми же четырьмя NFA:
Results/competitors_250k/build/larpq-smoke \
  Datasets/rpqbench_250k/prepared/matrix/graph.dat \
  Datasets/rpqbench_250k/prepared/basic/larpq.tsv 24225 9
# Pathrex с short-name dictionaries:
Databases/pathrex/target/release/pathrex query \
  -g Datasets/rpqbench_250k/pathrex \
  -q Datasets/rpqbench_250k/prepared/basic/pathrex.txt \
  --base-iri http://example.org/ -a rpqmatrix -p join \
  -o Results/competitors_250k/manual-pathrex.json
```

Native build commands, ручные imports и client calls каждого сервера — по
ссылкам первой таблицы. Старые runner keys `larpq`, `rpqmatrix`, `rpqmatrixGB`,
`millenniumdb`, `ring` также работают.

## Другие датасеты: конвертация N3 / NT / Turtle

Для нового графа не применять RPQBench localhost filter или сокращение
исходных namespaces без проверки. Общий [prepare_rdf.py](../Scripts/archive/competitors/prepare_rdf.py)
разбирает RDFLib формат, различает полные IRI/blank nodes, назначает безопасные
имена `vN`, `relN` и сохраняет mapping. Выбираются resource-to-resource edges;
triples с literal object исключаются. Это переименование без коллизий.
Новые IDs отличаются от legacy 250k, эти представления не смешивать.

```bash
# N3 с prefixes, blank nodes, typed literals:
Results/competitors_250k/venv/bin/python Scripts/competitors/prepare_rdf.py \
  Datasets/my_graph/source.n3 Datasets/my_graph/prepared --format n3
# Настоящий N-Triples, другой отсутствующий output directory:
Results/competitors_250k/venv/bin/python Scripts/competitors/prepare_rdf.py \
  Datasets/other_graph/source.nt Datasets/other_graph/prepared --format nt
```

Для Turtle указать `--format turtle`. Output не перезаписывается. RDF разбирается
в памяти; для огромных графов нужен streaming/external-memory pipeline.
Blank-node identity локальна документу: сохранять созданные manifest и файлы
вместе. Проверены NT и N3 с prefixes, blank node, literal и разными IRI с
одинаковым local name; resource identity не сливается.

Результат: `rdf/graph.nt`, `pathrex/` MM, `csv/`, `matrix/`, `matrix-gb/` с
единым numbering. Внутри используются авторский `nt-to-mm` и существующий
`mm_to_rpq_GB.py`. Binary CSR/CSC и Ring indexes строить командами соответствующих
гайдов, подставив V/P/E из нового manifest.

Подготовка запросов для нового графа:

1. По `node_mapping` / `predicate_mapping` заменить исходные термы их `vN` /
   `relN` именами; manifest содержит original→name→numeric-ID. RDF BASE и
   Pathrex `--base-iri` для этих short-name MM dictionaries — `http://rpqbench.local/`.
2. Pathrex: `id,<vN> <relN> ?t`. Matrix: `id <vN> <relN> ?t#`.
   Ring: `<vN> <relN> ?t#` без trailing newline; qid — номер строки.
3. LA-RPQ: из файла patterns без пробелов внутри regex сделать NFA:

   ```bash
   Results/competitors_250k/venv/bin/python vendor/larpq/Scripts/sparql-to-fa \
     Queries/my_graph/queries.txt Datasets/my_graph/prepared/pathrex \
     Queries/my_graph/automata
   ```

   `meta.txt` хранит bindings/start/final/label IDs, `N.txt` — transitions.
   Это upstream MM-NFA, **не `larpq.tsv`**: для прямого API загрузить matrices/meta;
   для harness сериализовать те же transitions в его [TSV schema](guides/larpq.md).
   Готовая сериализация есть для текущих 250k наборов; универсальный MM-NFA→TSV
   CLI пока отсутствует.
4. RDF: SELECT DISTINCT; Virtuoso — явно выбранный graph. Cypher: типы `relN`,
   vertex ID из manifest, эквивалентность pattern проверять отдельно. SQL: автомат
   и recursive UNION по `(vertex,state)`; для одной метки достаточно SELECT.

`smoke_250k.py` привязан к 250k и его manifests. Общая конвертация графа не
означает автоматический перевод произвольных regex для всех систем. На другом
датасете импортировать входы ручными командами из гайдов и подготовить query
adapters. Универсальный query compiler для всех 15 остаётся отдельной задачей.

[Авторские scripts](../vendor/larpq/Scripts/README.md): общий `truncate` исключает
blank nodes по умолчанию, RPQBench wrapper использует другие flags; `nt-to-mm` /
`nt-to-csv` ожидают плоский NT-like input; `sparql-to-fa` — ограниченный текстовый
translator, не полный SPARQL parser. Нельзя напрямую подавать им любой N3.

## Замеры: 100 повторов и графики

Все 15 систем прогнаны на Basic4 по 100 measured executions после 10 warmups.
В исторической серии Pathrex использовал **hybrid**; текущий runner использует
**pang-hybrid**. [Benchmark report и воспроизведение](guides/benchmark.md)
содержат PNG/SVG гистограммы, зелёно-красную HTML/Excel таблицу и все 6 000
samples. Границы native/embedded/JVM/network timing отмечены явно.

## Статусы, ограничения и Docker

Query statuses: `pass` — совпал set/count; `mismatch` — другой ответ;
`query_error` — ошибка; `unsupported` — evaluator отказал; `no_translation` —
нет перевода в нашем adapter; `not_checked` — не проверено. Последние три не
доказывают невозможность СУБД. Run statuses: `completed`, `completed_with_gaps`,
`completed_with_failures`, `failed`; при mismatch/error exit code — 1.

[Проверка контракта](guides/contract.md) объясняет WALK, zero-length, target-only
count Pathrex, multi-source LARPQ и отличия Cypher. [Исследование](reachability.md)
содержит первичные источники. `--workload20` — расширенный набор, для четырёх
Cypher systems полного adapter нет. Без selector используется старый набор
шести queries, включая известные gaps; это не общий `--basic`.

2026-10-18 все Docker containers удалены по запросу пользователя. Images и
volumes сохранены. Snapshot прежних контейнеров находится локально в
`Results/competitors_250k/cleanup-2026-10-18/`. Примеры создают новые containers;
после smoke они остановлены. Удалить только созданные проверочным runner:

```bash
python3 - <<'PY'
import subprocess
ids = subprocess.check_output(['docker', 'ps', '-aq', '--filter', 'label=rpq-bench.smoke=250k'], text=True).split()
if ids:
    subprocess.run(['docker', 'rm', '-f', *ids], check=True)
PY
```

Для performance benchmark нужны общие warmups/repetitions, memory/threads,
планы, нормализация ответа и отдельные preparation/execution/materialization
измерения. Startup/import/index time не считать временем RPQ execution.
