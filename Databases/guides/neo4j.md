# Neo4j Community

> Актуальные команды запуска находятся в [гайде раннера](../../Scripts/runners/README.md),
> а подготовка входов — в [гайде конвертеров](../../Scripts/converters/README.md).
> Ниже сохранены команды исторической серии.

Дата проверки: 2026-10-11. Команды — из корня RPQ_bench. Перед запуском выполнить
[общую подготовку](README.md#подготовка-окружения-и-запуск) (окружение/данные).
Фактическая версия и результат находятся в [отчёте](smoke-results.md);
Docker digest / JAR checksum / source SHA — в [runtime-lock.json](runtime-lock.json).

## Поставка и запуск

Использован neo4j:5.26-community с закреплённым digest, а не current Cypher 25
source build. Java входит в образ. Heap 256–512 MB, page cache 256 MB,
localhost Bolt 17687; auth выключен только для локального smoke.

```bash
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py neo4j
```

## Данные / импорт

Nodes: Node(id integer,name string), relationship types — девять edge labels.
Runner создаёт UNIQUE constraint на Node.id и импортирует parameterized UNWIND
batches по 1000. CSV уже подготовлен из N3-проекции. Альтернативный LOAD CSV:

```cypher
LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
CREATE (:Node {id:toInteger(row.id), name:row.name});
LOAD CSV WITH HEADERS FROM 'file:///edges_creator.csv' AS row
MATCH (s:Node {id:toInteger(row.src)}), (t:Node {id:toInteger(row.dst)})
CREATE (s)-[:creator]->(t);
```

Для этого server.directories.import должен указывать на mounted CSV directory;
это другой путь импорта, не выполненный smoke path. Native neo4j-admin bulk import
потребует специальных header columns и новой offline database; текущие CSV
не объявляются готовыми neo4j-admin inputs.

## Запросы / semantics

```cypher
MATCH (s:Node {id:1})-[:references]->()-[:cite]->()-[:creator]->(t:Node)
RETURN DISTINCT t.id AS id;
```

Prepared Cypher q1/q2/q3/q5/q6 исполнились, endpoints совпали 5/5. Q4 compound
closure no_translation. Default relationship uniqueness может отличаться от
WALK для общего regex. Возможности REPEATABLE ELEMENTS / explicit WALK текущих
Cypher 25 docs нельзя приписывать выбранной Neo4j 5.26 автоматически.
Для fair benchmark нужен отдельный proof/semantics test каждого перевода.

Считать `count(DISTINCT t)`, а не число matched paths. Для single-source имеет
значение constraint/index и параметризация query. Измерять планы/profile,
server execution и result fetching отдельно; warm JVM/database не запускать
заново перед каждым measured query.

Источники: [LOAD CSV](https://neo4j.com/docs/cypher-manual/current/clauses/load-csv/),
[current match/path modes — для сравнения версий](https://neo4j.com/docs/cypher-manual/current/patterns/reference/match-modes-and-path-modes/),
[Docker](https://neo4j.com/docs/operations-manual/current/docker/introduction/).

[Все гайды](README.md) · [Семантика RPQ](../reachability.md).

[Проверка контракта](contract.md): один MATCH для `F-p-G-q-F-p-G` дал пустой
ответ из-за повторения ребра; три отдельных MATCH вернули G. Это различие
с WALK Pathrex/LARPQ и рабочий перевод фиксированной последовательности.
