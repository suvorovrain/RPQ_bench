# Kuzu embedded

> Актуальные команды запуска находятся в [гайде раннера](../../Scripts/runners/README.md),
> а подготовка входов — в [гайде конвертеров](../../Scripts/converters/README.md).
> Ниже сохранены команды исторической серии.

Дата проверки: 2026-10-11. Команды — из корня RPQ_bench. Перед запуском выполнить
[общую подготовку](README.md#подготовка-окружения-и-запуск) (окружение/данные).
Фактическая версия и результат находятся в [отчёте](smoke-results.md);
Docker digest / JAR checksum / source SHA — в [runtime-lock.json](runtime-lock.json).

## Поставка и запуск

Использован Python wheel kuzu==0.11.3, embedded database без сервера. Это
бинарная поставка, не source build архивированного submodule. Версия фиксирована
в requirements.txt. Buffer pool 512 MB, max_num_threads=2.

```bash
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py kuzu
```

## Schema / CSV

```cypher
CREATE NODE TABLE Node(id INT64, name STRING, iri STRING, PRIMARY KEY(id));
COPY Node FROM '/absolute/path/to/prepared/csv/nodes.csv' (HEADER=true);
CREATE REL TABLE creator(FROM Node TO Node);
COPY creator FROM '/absolute/path/to/prepared/csv/edges_creator.csv' (HEADER=true);
```

Создать relationship table для каждой из девяти меток. Headers/column order
должны совпадать со schema; Node.id обеспечивает одинаковую external identity.
Query results читает Python Connection.execute()/get_next(), не Bolt.
N3 напрямую в этом pipeline не читается; CSV конвертирован и сверён с MM graph.

## Запросы и ограничения

```cypher
MATCH (s:Node {id:1})-[:creator]->(t:Node) RETURN DISTINCT t.id AS id;
```

Recursive relationships поддерживают WALK default, но если upper bound опущен,
default max hops 30. Smoke five queries укладываются в этот cap и дали 5/5
sets; это не доказательство полноты на более длинном графе. Q4 нет проверенного
прямого перевода. Для общего RPQ нужны compound closures/alternations/inverse
coverage и доказанный достаточный bound либо другой алгоритм.

Binary database directories создаются отдельно (`kuzu-*` в Results). Не
смешивать файловые форматы версий. Не требуются extensions: их server после
архивации проекта не следует считать доступным. Embedded execution удобно для
benchmark без сети; import, connection setup и fetching всё равно выделить.

Источники: [MATCH / hop default](https://kuzudb.github.io/docs/cypher/query-clauses/match/),
[архивированный официальный репозиторий](https://github.com/kuzudb/kuzu).

[Все гайды](README.md) · [Семантика RPQ](../reachability.md).

[Проверка контракта](contract.md) подтвердила повторение ребра для `p/q/p`.
На цепочке 31 hops default вернул 30 targets; явный upper=31 без настройки
был отклонён. После `CALL var_length_extend_max_depth=31` получены все 31.
Это проверка достаточности bound для этой цепочки, не общего regex workload.
