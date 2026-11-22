# Blazegraph: journal / SPARQL HTTP

Дата проверки: 2026-10-11. Команды — из корня RPQ_bench. Перед запуском выполнить
[общую подготовку](README.md#подготовка-окружения-и-запуск) (окружение/данные).
Фактическая версия и результат находятся в [отчёте](smoke-results.md);
Docker digest / JAR checksum / source SHA — в [runtime-lock.json](runtime-lock.json).

## Поставка и запуск

Использован официальный `BLAZEGRAPH_2_1_6_RC` blazegraph.jar с Java 21 в Docker.
Это RC binary, не source build и не доказательство совместимости других JDK.
Checksum и URL зафиксированы. Runner создаёт отдельный journal directory и
properties file, задаёт heap 768 MB и отключает inference/axioms.

```bash
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py blazegraph
```

## Импорт / query interface

Сервер — `/blazegraph/namespace/kb/sparql`, внешний порт 19999. Docker mapping использует `19999:9999`. В испробованном JAR `java -jar`
запустил standalone launcher, проигнорировав переданные port/properties.
Поэтому runner вызывает main class явно, задавая resource location для Jetty:

```bash
java -Xmx768m \
  '-Djetty.home=jar:file:/tools/blazegraph.jar!/war' \
  '-Djetty.resourceBase=jar:file:/tools/blazegraph.jar!/war' \
  -cp /tools/blazegraph.jar com.bigdata.rdf.sail.webapp.NanoSparqlServer \
  9999 kb /state/blazegraph.properties
```

Без `jetty.home` этот main class с Java 21 падает на поиске ресурса `/war`.
С указанными параметрами проверено
применение properties и создание persistent journal в bind-mounted /state.
Ориентироваться на startup serviceURL и journal file, а не только на аргументы.

С уже запущенным созданным контейнером:

```bash
docker start rpq-bench-250k-blazegraph
curl -H 'Content-Type: application/n-triples' \
  --data-binary @Datasets/rpqbench_250k/prepared/rdf/graph.nt \
  http://127.0.0.1:19999/blazegraph/namespace/kb/sparql
curl -H 'Accept: application/sparql-results+json' \
  --data-urlencode query@Datasets/rpqbench_250k/prepared/queries/q4.rq \
  http://127.0.0.1:19999/blazegraph/namespace/kb/sparql
```

POST RDF выполняет загрузку, POST form `query=` — SPARQL. После smoke данные уже
загружены; повторный import не нужен. Query format — полноценный SELECT DISTINCT.
Все шесть endpoint sets совпали. Journal находится в `Results/competitors_250k/blazegraph-state-*`;
это persistent bind mount. После остановки и повторного запуска проверено
сохранение всех 61 017 троек.

## Ограничения

Property paths возвращают endpoints; GAS graph APIs — отдельный механизм и не
нужны для RPQ comparison. Set triples в RDF схлопывают duplicates. Для native
performance выбрать/зафиксировать JVM heap, warm JVM и query plans; версия RC и
старые dependencies делают переносимость отдельным вопросом. Smoke не проверяет
всю SPARQL test suite или all-pairs zero-length universe.

Расширенный запуск `smoke_250k.py blazegraph --workload20` также прошёл
20/20 точных endpoint sets (con-any / any-con).

Источники: [релизы](https://github.com/blazegraph/database/releases),
[REST API](https://github.com/blazegraph/database/wiki/REST_API),
[property paths](https://github.com/blazegraph/database/wiki/PropertyPaths).

[Все гайды](README.md) · [Семантика RPQ](../reachability.md).
