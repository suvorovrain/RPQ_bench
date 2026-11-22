# Apache Jena TDB2 / ARQ

> Актуальные команды запуска находятся в [гайде раннера](../../Scripts/runners/README.md),
> а подготовка входов — в [гайде конвертеров](../../Scripts/converters/README.md).
> Ниже сохранены команды исторической серии.

Дата проверки: 2026-10-11. Команды — из корня RPQ_bench. Перед запуском выполнить
[общую подготовку](README.md#подготовка-окружения-и-запуск) (окружение/данные).
Фактическая версия и результат находятся в [отчёте](smoke-results.md);
Docker digest / JAR checksum / source SHA — в [runtime-lock.json](runtime-lock.json).

## Поставка и запуск

Использована официальная binary distribution Apache Jena 6.2.0, Java 21 через
Temurin Docker. Это не build нашего submodule. download_tools.py проверяет
SHA256 архива и распаковывает его в Results/.../tools/apache-jena-6.2.0.

```bash
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py jena
```

Если Java 21+ установлена на хосте, эквивалентный ручной путь:

```bash
Results/competitors_250k/tools/apache-jena-6.2.0/bin/tdb2.tdbloader \
  --loc Results/competitors_250k/jena-manual-db \
  Datasets/rpqbench_250k/prepared/rdf/graph.nt
Results/competitors_250k/tools/apache-jena-6.2.0/bin/tdb2.tdbquery \
  --loc Results/competitors_250k/jena-manual-db \
  --query Datasets/rpqbench_250k/prepared/queries/q4.rq --results CSV
```

## Вход / запросы / нюансы

Loader принимает RDF formats; здесь N3 преобразован в N-Triples для общей
проекции. Default graph, без entailment. Query — полноценный SPARQL 1.1 SELECT
DISTINCT с property paths; возвращается `t` column в CSV. ARQ `Path` — regex
expression, не witness. Все шесть endpoint sets совпали с эталоном.

TDB2 несовместим с TDB1: использовать именно `tdb2.*` инструменты и отдельный
каталог. Не запускать конкурирующие writers над одной БД. В smoke каждый query
исполняется отдельным CLI/JVM; такое wall time нельзя сравнивать с warm in-memory
Pathrex. Для benchmark — embedded ARQ/TDB2 session или постоянно работающий
Fuseki server, warmups в той же JVM, импорт отдельно.

RDF full.nt также можно загрузить, но это будет другой граф и другой workload:
нельзя сравнивать его ответы с нашим short-name Pathrex input. Java 21 requirement
относится к выбранной Jena 6 binary distribution.

Расширенный запуск `smoke_250k.py jena --workload20` также прошёл
20/20 точных endpoint sets (con-any / any-con).

Источники: [download / Java requirement](https://jena.apache.org/download/),
[TDB2 commands](https://jena.apache.org/documentation/tdb2/tdb2_cmds.html),
[property paths](https://jena.apache.org/documentation/query/property_paths.html).

[Все гайды](README.md) · [Семантика RPQ](../reachability.md).
