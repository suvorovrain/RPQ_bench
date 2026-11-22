# Virtuoso Open Source 7

> Актуальные команды запуска находятся в [гайде раннера](../../Scripts/runners/README.md),
> а подготовка входов — в [гайде конвертеров](../../Scripts/converters/README.md).
> Ниже сохранены команды исторической серии.

Дата проверки: 2026-10-11. Команды — из корня RPQ_bench. Перед запуском выполнить
[общую подготовку](README.md#подготовка-окружения-и-запуск) (окружение/данные).
Фактическая версия и результат находятся в [отчёте](smoke-results.md);
Docker digest / JAR checksum / source SHA — в [runtime-lock.json](runtime-lock.json).

## Поставка и запуск

Использован официальный `openlink/virtuoso-opensource-7`, фактическая версия
07.20.3243; Docker digest закреплён. Не source build. Runner задаёт DBA password
для локального smoke, memory buffers и DirsAllowed=/input, монтирует отдельную
database directory и открывает localhost:18891 → container:8890.

```bash
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py virtuoso
```

## Данные / импорт

N-Triples `rdf/graph.nt` загружается через isql bulk loader в named graph
`http://example.org/rpq250k`. Файл должен быть виден серверу и разрешён DirsAllowed.

```bash
docker start rpq-bench-250k-virtuoso
docker exec rpq-bench-250k-virtuoso isql 1111 dba rpq-smoke-local \
  "EXEC=ld_dir('/input/rdf','graph.nt','http://example.org/rpq250k'); rdf_loader_run(); checkpoint;"
```

После smoke импорт уже выполнен. Для нового файла проверить loader errors
в output и `DB.DBA.load_list`, не считать HTTP readiness доказательством загрузки.
Source N3 конвертируется общим prepare; чтение RDF с полными IRI возможно, но
`full.nt` не является тем же графом, что matrix inputs.

## Запросы

В каждом prepared `qN.virtuoso.rq` указан `FROM <http://example.org/rpq250k>`.
Без него нельзя предполагать совпадение default graph с загруженным named graph.

```bash
curl -H 'Accept: application/sparql-results+json' \
  --data-urlencode query@Datasets/rpqbench_250k/prepared/queries/q4.virtuoso.rq \
  http://127.0.0.1:18891/sparql
```

SPARQL property paths исполняют endpoint RPQ; все шесть sets совпали. TRANSITIVE
path-step extension для этого сравнения не нужен. Query/result limits, buffers,
timeout и inference фиксировать перед большим workload. HTTP total time и
server execution time измерять отдельно. База сохраняется в virtuoso-state-*.

Расширенный запуск `smoke_250k.py virtuoso --workload20` также прошёл
20/20 точных endpoint sets (con-any / any-con).

Источники: [официальный образ](https://hub.docker.com/r/openlink/virtuoso-opensource-7),
[property paths](https://vos.openlinksw.com/VOS/VirtTipsAndTricksSPARQL11PropertyPaths),
[bulk loader](https://docs.openlinksw.com/virtuoso/fn_ld_dir/).

[Все гайды](README.md) · [Семантика RPQ](../reachability.md).
