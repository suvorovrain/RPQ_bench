# Ring-RPQ

> Актуальные команды запуска находятся в [гайде раннера](../../Scripts/runners/README.md),
> а подготовка входов — в [гайде конвертеров](../../Scripts/converters/README.md).
> Ниже сохранены команды исторической серии.

Дата проверки: 2026-10-11. Команды — из корня RPQ_bench. Перед запуском выполнить
[общую подготовку](README.md#подготовка-окружения-и-запуск) (окружение/данные).
Фактическая версия и результат находятся в [отчёте](smoke-results.md);
Docker digest / JAR checksum / source SHA — в [runtime-lock.json](runtime-lock.json).

## Сборка и варианты

Сборка авторского SDSL fork и Ring targets — в
[build-native.md](build-native.md#ring-rpq). Проверены build-index-basic и
query-index-basic; split/RingAB отдельно не запускались. Upstream CMake задаёт
Debug, поэтому эти результаты — функциональные, не финальная benchmark build.

```bash
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py ring
```

## Датасет / индекс

Текст `graph.dat` с 1-based s/p/o и словари `.SO`/`.P` ровно как у matrix.
N3 → общая проекция → этот layout уже подготовлены. Нельзя передать N3 напрямую.

```bash
Results/competitors_250k/build/ring/build-index-basic \
  Datasets/rpqbench_250k/prepared/matrix/graph.dat
Results/competitors_250k/build/ring/query-index-basic \
  Datasets/rpqbench_250k/prepared/matrix/graph.dat \
  Datasets/rpqbench_250k/prepared/queries/ring.tsv
```

Builder создаёт дополнительные BWT/index файлы рядом с base name. Query driver
принимает base name `graph.dat`, а не отдельный `.bwts` файл; словари должны
оставаться рядом. Нужно место и право записи при построении индекса.

## Запросы / найденные особенности

Одна строка `<Article1> <creator> ?t#`, без внешнего query_id. Порядок строк
задаёт qid. Предел числа ответов в driver — 1 000 000; для полного all-pairs
ответа его надо контролировать. Код выдаёт `qid;count;time`, не сами walks.

**В pinned driver нельзя заканчивать query file переводом строки**: цикл
`do/getline/while(!eof)` делает лишнее чтение и `line.at(0)` падает. Сначала
все шесть ответов получились правильными, но процесс abort-нулся после них.
Подготовленный `ring.tsv` теперь не имеет trailing newline; повторный запуск
завершился нормально и проверил counts 6/6. Blank lines тоже исключить.

Прототип имеет ручной parser и ограничения automaton representation; покрытие
long/nested expressions и другие endpoint bindings проверять отдельно. Публичный
RPQ метод возвращает pairs; cardinality smoke слабее сравнения множества пар.

Дополнительно проверены все 20 upstream шаблонов: counts 20/20. Native
parser ожидает односимвольное имя конечной переменной (`?t#`); `?obj#`
воспринимается ошибочно и может молча дать 0. Converter переименовывает
`?sub`→`?s`, `?obj`→`?t` только в native query files; RDF/Pathrex variables
сохраняются. Это ограничение формата driver, не расхождение RPQ алгоритма.

Источники: [README](../ring-rpq/README.md),
[driver](../ring-rpq/src/query-index-basic.cpp),
[статья](https://www.aidanhogan.com/docs/ring-graph-rpq.pdf).

[Все гайды](README.md) · [Семантика RPQ](../reachability.md).
