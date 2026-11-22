# MillenniumDB: RDF/SPARQL режим

Дата проверки: 2026-10-11. Команды — из корня RPQ_bench. Перед запуском выполнить
[общую подготовку](README.md#подготовка-окружения-и-запуск) (окружение/данные).
Фактическая версия и результат находятся в [отчёте](smoke-results.md);
Docker digest / JAR checksum / source SHA — в [runtime-lock.json](runtime-lock.json).

## Сборка и импорт

Выполнена source build закреплённой ревизии; Boost headers потребовалось
скачать отдельно. Команды — в [build-native.md](build-native.md#millenniumdb).
Текущий CLI объединён в `mdb`; старые vendor команды `mdb-import` не подходят.

```bash
Results/competitors_250k/build/millenniumdb/bin/mdb import \
  Datasets/rpqbench_250k/prepared/rdf/graph.nt \
  Results/competitors_250k/mdb-manual-db \
  --buffer-strings 256MB --buffer-tensors 256MB
Results/competitors_250k/build/millenniumdb/bin/mdb server \
  Results/competitors_250k/mdb-manual-db --port 12345 --browser false --threads 2
```

Import требует buffer-strings не меньше 256 MB: попытка 64 MB отвергается.
Выбирать новую database directory; не импортировать поверх пользовательской БД.
Format поддерживает nt/ttl/n3/rdf, но для одинакового graph benchmark берём
`rdf/graph.nt`, не полный N3 с properties. Не применять старые patches для
unprefixed IRIs: prepared graph имеет валидные полные IRI.

## Запросы

```bash
curl -H 'Content-Type: application/sparql-query' -H 'Accept: text/csv' \
  --data-binary @Datasets/rpqbench_250k/prepared/queries/q4.rq \
  http://127.0.0.1:12345/sparql
```

`.rq` — полный SPARQL SELECT DISTINCT; source binding, regex и base уже указаны.
HTTP output text/csv сравнивается по endpoints. RDF/SPARQL, Quad/MQL и GQL —
разные модели: не смешивать loaders/queries. Paths возвращаются расширенными
языками, для нашего benchmark нужен обычный endpoint result.

```bash
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py millenniumdb
```

Runner сам импортирует новую БД, запускает native server с уменьшенными memory
buffers, проверяет sets 6/6 и завершает сервер. Databases остаются в Results.

Официальная implementation-status wiki описывает ограничения negated property
sets и zero-length all-variable `?s :P* ?o`. Успешные anchored six tests не
проверяют этот all-pairs случай. Для будущего workload добавить его отдельно.

Расширенный запуск `smoke_250k.py millenniumdb --workload20` также прошёл
20/20 точных endpoint sets (con-any / any-con).

Источники: [официальный запуск](https://github.com/MillenniumDB/MillenniumDB/wiki/Creating-and-running-a-database),
[CLI](../millenniumdb/src/bin/mdb.cc),
[SPARQL status](https://github.com/MillenniumDB/MillenniumDB/wiki/SPARQL-Implementation-Status).

[Все гайды](README.md) · [Семантика RPQ](../reachability.md).
