# Reachability: контракт и поддержка выбранных 15 конкурентов

Набор актуализирован 2026-10-18. Исследование источников и диагностические
проверки выполнены 2026-10-11; новый общий Basic4 проверен 2026-10-18.
[Общий README](README.md) содержит форматы, конвертацию, запуск и статусы.
[Контракт](guides/contract.md) — source/API разбор и маленькие контрпримеры;
[отчёт](guides/smoke-results.md) — фактическое покрытие выбранных версий.
Поддержка по документации не равна проверке каждого оператора в pinned binary.

## Контракт для сравнения

WALK RPQ — отношение пар `(s,t)`, для которых существует walk с допустимым
словом меток. Вершины/рёбра могут повторяться; разные walks одной пары не
создают разные ответы. Если выражение принимает ε, учитывается нулевой путь.

- con-any: distinct targets; это общий режим Basic4.
- any-con: distinct sources; для vector API обращаем запрос от target.
- any-any: distinct pairs; multi-source union targets пары не сохраняет.
- con-con: Boolean существования; не количество найденных путей.

Pathrex Matrix API имеет relation matrix и `nnz`, но CLI считает непустые
колонки. Pathrex NFA и LARPQ возвращают target vector. Поэтому current
Pathrex CLI нельзя сравнивать с числом sources/pairs без адаптации.
У Pathrex также проверены расхождения для одинаковых endpoint variables,
missing-label и zero-length constants вне V; подробности в [контракте](guides/contract.md).

## Системы

| Система | Reachability | Witness paths | Ограничение / основание |
| --- | --- | --- | --- |
| la-rpq | Single-source / multi-source target set | Нет в подключённом API | Автомат, Boolean GraphBLAS, inverse labels; union sources теряет provenance. [Статья](https://arxiv.org/html/2412.10287), [код](larpq/experimental/algorithm/LAGraph_RegularPathQuery.c) |
| rpq-matrix | Boolean relation / pairs | Нет в baseline API | Matrix algebra; CLI возвращает cardinality. [Статья](https://arxiv.org/html/2307.14930), [код](rpq-matrix/) |
| rpq-matrix_gb | Boolean relation / pairs | Нет в baseline API | GraphBLAS backend матричного метода; отдельная публикация для этой реализации не установлена. [Код](rpq-matrix_GB/) |
| pathrex | Relation API / target-only CLI | Нет в текущем RPQ API | Matrix не поддерживает optional; NFA поддерживает. Оптимизаторы не меняют контракт ответа. [Код](pathrex/pathrex/src/rpq/rpqmatrix/result.rs) |
| Blazegraph | SPARQL endpoints | GAS traversal/predecessors — отдельный механизм | DISTINCT; RC binary; GAS не доказывает arbitrary regex witness retrieval. [Property paths](https://github.com/blazegraph/database/wiki/PropertyPaths), [GAS](https://github.com/blazegraph/database/wiki/RDF_GAS_API) |
| DuckDB | Наш recursive SQL endpoint evaluator | Можно программировать SQL path lists; здесь не реализовано | RPQ→automaton→product-state fixpoint, без DuckPGQ. [WITH](https://duckdb.org/docs/current/sql/query_syntax/with), [USING KEY](https://duckdb.org/2025/05/23/using-key) |
| Jena | SPARQL endpoint relation | Не через standard property-path pattern | DISTINCT; zero-length SPARQL universe отличается от graph-only API. [ARQ paths](https://jena.apache.org/documentation/query/property_paths.html) |
| Kuzu | Endpoints для поддерживаемых recursive patterns | Да | Default WALK, default depth 30; compound regex не установлен. [MATCH](https://kuzudb.github.io/docs/cypher/query-clauses/match/), [CIDR 2023](https://www.cidrdb.org/cidr2023/papers/p48-jin.pdf) |
| Memgraph | Endpoints для поддерживаемых patterns / BFS | Да | Один MATCH в проверенном p/q/p исключает повторение ребра; split MATCH помогает для фиксированной sequence. [Traversals](https://memgraph.com/docs/advanced-algorithms/deep-path-traversal) |
| mdb / MillenniumDB | RDF/SPARQL endpoint executors | PathFinder / extended languages | Не смешивать RDF и challenge mode. Проверить известное zero-length any-any отклонение. [PathFinder](https://semantic-web-journal.net/system/files/swj3930.pdf), [SPARQL status](https://github.com/MillenniumDB/MillenniumDB/wiki/SPARQL-Implementation-Status) |
| Neo4j | Endpoints для поддерживаемых patterns | Да | 5.26 Community: один MATCH запрещает повторное relationship; current Cypher 25 docs нельзя переносить на эту версию. [Neo4j 5 patterns](https://neo4j.com/docs/cypher-manual/5/patterns/variable-length-paths/) |
| PostgreSQL | Наш recursive SQL evaluator | Можно программировать arrays; здесь не реализовано | UNION по `(vertex,state)`; для all-pairs добавить source dimension. [Recursive queries](https://www.postgresql.org/docs/current/queries-with.html) |
| Ring-RPQ | Regex endpoint pairs | Нет в рассмотренном query API | Glushkov/Ring, CLI result bound 1M, basic source build сейчас Debug. [ICDE paper](https://www.aidanhogan.com/docs/ring-graph-rpq.pdf), [driver](ring-rpq/src/query-index-basic.cpp) |
| Virtuoso | SPARQL endpoints | TRANSITIVE может выдавать шаги и path IDs | Это разные механизмы; TRANSITIVE не доказывает произвольный regex witness API. [Property paths](https://vos.openlinksw.com/VOS/VirtTipsAndTricksSPARQL11PropertyPaths), [TRANSITIVE](https://docs.openlinksw.com/virtuoso/transitivityinsql/) |
| FalkorDB | Endpoints для поддерживаемых patterns | Да | Проверенный p/q/p допускает повторение ребра; это отличается от Neo4j/Memgraph. Arbitrary compound regex пока не подтверждён. [MATCH](https://docs.falkordb.com/cypher/match) |

SPARQL property paths: label, sequence, alternation, optional, star/plus,
inverse; negated property sets — отдельный оператор. Endpoint queries не
возвращают сам walk. Некоторые SPARQL конструкции дают multiset solutions:
для сравнения использовать DISTINCT, а count брать над distinct subquery.
[Стандарт W3C](https://www.w3.org/TR/sparql11-query/#propertypaths).

## Что фактически проверено и что осталось

Все 15 систем прошли одинаковые четыре con-any queries Basic4. Это метка,
фиксированная последовательность, label-star и alternation. У четырёх Cypher
systems составное `(A/B)*` пока имеет статус `no_translation`; это отсутствие
нашего перевода, не доказательство невозможности СУБД.

Десять систем ранее прошли 20/20 шаблонов; у Pathrex 19/20 counts на optimizer:
any-con q12 выявил target/source count mismatch. Optional отдельно прошёл NFA.
Успех этого набора не доказывает полноту inverse/any-any/equality/zero-length.
Часть шаблонов имеет пустые ответы, нужны дополнительные непустые cases.

До сравнения скорости согласовать extraction ответа и проверить sets, где
сейчас доступен только count. Контролировать LIMIT/result caps, повторение
рёбер, достаточность глубины, изолированные вершины и nullable expressions.
Конечный depth bound допустим, если доказана его достаточность для графа и
автомата; default cap без такого доказательства неполон.

Для performance отдельно измерять import/index, regex→automaton/SQL,
parse/plan/execute и materialization, фиксировать warmups, repetitions,
threads/memory и версии. Наш smoke не даёт сопоставимого рейтинга скорости.
