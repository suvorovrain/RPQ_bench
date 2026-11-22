# 15 конкурентов × Basic4 × 100 повторов

> Актуальные команды запуска находятся в [гайде раннера](../../Scripts/runners/README.md),
> а подготовка входов — в [гайде конвертеров](../../Scripts/converters/README.md).
> Ниже сохранены команды исторической серии.

Дата: 2026-10-18. Датасет — существующая resource-edge проекция
`rpqbench_250k`: 24 225 vertices, 9 labels, 61 017 unique edges.
Все 15 систем завершили четыре общих запроса с правильными ответами.
В историческом прогоне Pathrex использован с **RPQMatrix / hybrid**.
Новые запуски скриптов используют `pang-hybrid`: прежний `hybrid` удалён.
Сохранённые результаты не пересчитывались.

| Query | Pattern | Distinct targets |
| --- | --- | --- |
| Q1 | `<Article1> <creator> ?t` | 56 |
| Q2 | `<Article1> <references>/<cite>/<creator> ?t` | 109 |
| Q3 | `<Tashiya_Marrable> (<coauthor>)* ?t` | 3 |
| Q5 | `<1940> (<editor>\|<creator>) ?t` | 1 |

На каждый запрос — **10 warmup executions + 100 measured executions**.
Итого 6 000 основных измерений, 60 строк статистики. Import, graph loading,
index building, process/JVM startup и проверка правильности вне таймеров.
Процессы исполнялись последовательно. Для всех повторов сохраняется один
загруженный graph/database; соединения серверных драйверов переиспользуются
там, где это обеспечивает API. HTTP requests urllib открывают соединение
по своему обычному протоколу, его overhead остаётся в client time.

## Артефакты

Все файлы созданы локально в
[`Results/competitors_bench_250k/2026-10-18-basic4-100`](../../Results/archive/competitors_bench_250k/2026-10-18-basic4-100/).
Большие/машинные результаты игнорируются Git; воспроизводятся командами ниже.

- [Самодостаточный HTML отчёт](../../Results/archive/competitors_bench_250k/2026-10-18-basic4-100/report/report.html)
  с графиками, цветной таблицей и методикой.
- [Гистограмма / bar charts PNG](../../Results/archive/competitors_bench_250k/2026-10-18-basic4-100/report/histogram.png)
  и [SVG](../../Results/archive/competitors_bench_250k/2026-10-18-basic4-100/report/histogram.svg).
- [Цветная таблица PNG](../../Results/archive/competitors_bench_250k/2026-10-18-basic4-100/report/table.png)
  и [Excel](../../Results/archive/competitors_bench_250k/2026-10-18-basic4-100/report/table.xlsx).
- [Распределения всех samples](../../Results/archive/competitors_bench_250k/2026-10-18-basic4-100/report/distributions.png).
- [Статистика CSV](../../Results/archive/competitors_bench_250k/2026-10-18-basic4-100/report/summary.csv),
  [все 6 000 samples CSV](../../Results/archive/competitors_bench_250k/2026-10-18-basic4-100/report/samples.csv)
  и [summary JSON](../../Results/archive/competitors_bench_250k/2026-10-18-basic4-100/report/summary.json).
- `metadata.json`, `<engine>.json`, `logs/`: версии, полные команды, per-query
  samples и scopes, hashes executable files, source dataset hash и проверки.

Зелёный = mean ниже Pathrex для этого запроса; красный = выше;
синий = baseline Pathrex. В таблице **mean ± sample standard deviation, ms**.
В CSV дополнительно median, p95, min/max, CV. GM — геометрическое среднее
отношений mean времени к Pathrex по четырём queries; меньше — быстрее.
Цвета описывают средние, не являются тестом статистической значимости.
Bar charts используют log scale: разница между native и server scopes велика.

## Границы таймеров и ограничения сравнения

Таблица ниже описывает исторический smoke-прогон. Метрики действующих
раннеров приведены в [Scripts/runners/README.md](../../Scripts/runners/README.md#что-измеряет-каждый-раннер).

Это измерения реально используемых интерфейсов, а не единый kernel-only ranking.
Тип границы подписан на графике и присутствует в каждой строке CSV.

| Системы | Что измеряется |
| --- | --- |
| Pathrex | Native `evaluate`: preparation/optimizer + execution; graph и SPARQL parsing уже вне таймера. Result count снаружи |
| rpq-matrix / GB | Native solver, без native text parsing и graph loading; время в ns из driver переводится в ms |
| LA-RPQ | Вызов NFA API + `GrB_Vector_wait(MATERIALIZE)`; graph/NFA подготовлены заранее |
| Ring-RPQ | Native query call, включая работу query API, без text parsing и index load |
| DuckDB / Kuzu | Python embedded execute + полное чтение результатов |
| Jena | Одна JVM/TDB2 database: read transaction, query parsing/execution, полное извлечение endpoints |
| PostgreSQL / mdb / Neo4j / Memgraph / FalkorDB / Blazegraph / Virtuoso | Client roundtrip: запрос, server work, получение/разбор ответа |

Числа server client-time включают protocol/driver overhead; native solver-time
этого overhead не имеет. Query compilation и result materialization тоже
включены неодинаково. Сравнение через одну таблицу нужно читать с этими scopes;
оно не доказывает универсальное превосходство одного алгоритма.

Для Python/Jena/серверов проверяются endpoint sets; для native matrix/Ring —
counts. В LA-RPQ count проверяется на всех повторениях, endpoint set — после
серии. Pathrex CLI выводит result_count, а не endpoints; его correctness check
опирается на это число. Совпавший count слабее равенства множеств.

Native Pathrex CLI по своему протоколу дополнительно исполняет 100 **ffi-only**
итераций на query и отдельные warmups. Они сохранены как diagnostic samples,
но не подменяют 100 основных `total` executions в таблице/графиках.

Ring driver собирается из изолированной копии upstream source с `-O3`;
existing SDSL/nfa libraries переиспользуются, это не пересборка всех dependencies
в Release. В копии исправлена только выдача timing: upstream округляет duration
до integer microseconds и затем применяет неверный scale. Новый driver пишет
`duration<double, milli>`; original submodule не патчится.

Docker engines ограничены 2 CPUs / 2 GiB; native/embedded host processes имеют
OMP_NUM_THREADS=2, embedded настройки потоков — 2. У host processes нет того же
hard memory limit/CPU quota. CPU model/load не контролировались внешним стендом.
Первые четыре native серии повторены после окончания установки environment
dependencies; предыдущие samples сохранены отдельно и не входят в отчёт.
JIT/GC/server caches могут давать выбросы; все samples сохранены, ничего не
отбрасывается. Один маленький граф и четыре anchored queries — ограниченный
workload, не замена измерению больших графов и разных binding modes.

## Повторить benchmark и построить отчёт

Сначала [подготовить данные и binaries](../README.md). Дополнительные зависимости
построения графиков устанавливать **до** начала timed runs:

```bash
Results/competitors_250k/venv/bin/pip install -r Scripts/competitors/requirements-plot.txt
Results/competitors_250k/venv/bin/python Scripts/competitors/benchmark_all.py \
  --output Results/competitors_bench_250k/my-run --runs 100 --warmups 10
Results/competitors_250k/venv/bin/python Scripts/competitors/plot_benchmarks.py \
  Results/competitors_bench_250k/my-run
```

Output должен находиться внутри repository root (Java Docker mount).
Существующий output не перезаписывается: использовать новую директорию или
`--resume` с теми же runs/warmups. Завершённые engines тогда пропускаются.
В `--engines` используются внутренние keys из help; для baseline comparison
включить `pathrex`. По умолчанию включены все 15 и только optimizer pang-hybrid.

Скрипты:
[benchmark_all.py](../../Scripts/archive/competitors/benchmark_all.py),
[plot_benchmarks.py](../../Scripts/archive/competitors/plot_benchmarks.py),
[JenaBench.java](../../Scripts/archive/competitors/JenaBench.java),
[larpq_smoke.c](../../Scripts/archive/competitors/larpq_smoke.c).
Все созданные benchmark containers останавливаются и удаляются после серии;
images/volumes, database directories и полные logs сохраняются.

## Новые серии и resume

`--runs` и `--warmups` задают фактические числа повторов; metadata записывает
текущее время UTC. `--resume` допускает повторный запуск подмножества ранее
выбранных engines, но проверяет запросы/эталон, исходный граф, версии пакетов,
контрольные суммы адаптеров и доступных native binaries, а также runtime lock.
При изменении этих параметров нужна новая output-directory. Старые серии без
этого fingerprint нельзя продолжать новым runner; их исходные данные сохраняются.

GB использует MatrixMarket layout без binary CSR/CSC index. Для rpqmatrix
бинарный index по-прежнему обязателен. Операционные проверки не отключаются
при запуске Python с `-O`.

`OMP_NUM_THREADS=2` в metadata означает запрошенную настройку окружения.
Это не измеренный фактический лимит GraphBLAS: см. известное поведение
ThreadScope в Pathrex. Docker использует quota 2 CPU; embedded/native процессы
не закрепляются на двух CPU. Перед сравнением производительности на новом
сервере отдельно подтвердить эффективные потоки и affinity. Эта поддержка
фиксирует рабочие интерфейсы Basic4, а не одинаковые физические kernels всех систем.
