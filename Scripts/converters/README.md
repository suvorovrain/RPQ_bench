# Подготовка графов и запросов

## RPQBench 250k

```bash
python -m Scripts.converters.general.sources rpq_250k --local /path/to/rpqbench_250k.n3
python -m Scripts.converters.general.dataset --bootstrap-250k
python -m Scripts.converters.general.queries
```

Если оригинал уже лежит в `Datasets/rpq_250k`, первую команду можно вызвать
без `--local`. Она сохранит каталог шаблонов из `vendor/larpq`.
У upstream RPQBench также есть генератор `rpqbench_gen`. Его можно передать
через `--generator /path/to/rpqbench_gen`. Для точного воспроизведения
исторических результатов нужен исходный N3. Конвертер проверяет совпадение
ресурсной проекции и MatrixMarket. Существующий `prepared/` переиспользуйте.

Общий подготовленный граф содержит CSV для SQL/Cypher, RDF для SPARQL,
MatrixMarket для Pathrex и GB и `graph.dat` для LA-RPQ, Ring и rpq-matrix.
Движковые индексы и импорт БД выполняются вне таймера запросов. Подготовить или проверить входы одного движка можно через
`python -m Scripts.converters.<движок>.dataset`. Общие файлы создаются
один раз. Например, `python -m Scripts.converters.duckdb.dataset --bootstrap-250k`
подготовит общую проекцию и проверит вход DuckDB.

`python -m Scripts.converters.<движок>.queries` создаёт пакет только
для указанного движка. По умолчанию готовится контрольный Basic4.
Для другого набора задайте `--suite <имя> --catalog <файл>`. Формат:

```text
1,<Article1> <creator> ?t
2,<Article1> <references>/<cite>/<creator> ?t
```

Конвертер строит точный oracle обходом графа и автомата для фиксированного
источника. Можно передать уже проверенный JSON через `--manifest`.
В нём хранится `queries` с ID, выражением, списком `targets` и `count`.
Для SQL и LA-RPQ также нужны состояния и переходы, для RDF поле `sparql`.
Для пользовательского Cypher-набора передайте проверенный перевод
в `cypher` по имени движка или ключу `default`. Поддержка составных RPQ
зависит от синтаксиса и семантики конкретной СУБД.

## Wikidata

[Источник снимка и исходный протокол](../../vendor/larpq/Datasets/Wikidata/README.md).
Скачайте подходящий снимок через ссылку Figshare из upstream README и
передайте прямой URL файла либо локальный исходник:

```bash
python -m Scripts.converters.general.sources wiki --local /data/wikidata.nt
Scripts/converters/pathrex/preprocess_nt.sh Datasets/wiki/wikidata.nt Datasets/wiki/pathrex
python -m Scripts.converters.general.prepare_matrix Datasets/wiki/pathrex Datasets/wiki/prepared --base-iri http://example.org/
```

`sources wiki --url <прямой URL NT>` скачает файл сразу в нужный каталог.
Команда копирует upstream query catalog в `Datasets/wiki/upstream-queries.txt`.
Подготовка Pathrex использует upstream `truncate`, `deprefix-nt`,
`remove-dups` и `nt-to-mm`. Эти инструменты имеют собственные требования
к памяти. Настройка `--base-iri` должна соответствовать выбранной проекции
и именам в запросах. Проверенные manifest и запросы с фиксированным
началом нужны для запуска новой схемы на wiki. Полный Wikidata локально
не прогонялся.

Для произвольного небольшого RDF-графа используйте
`python -m Scripts.converters.general.prepare_rdf <source> <output> --format nt`.
Он генерирует общую нумерацию и специально предназначен для данных,
которые помещаются в RAM. В конфиге раннера укажите `prepared` равным
выходному каталогу, а `graph` равным его подпапке `pathrex`.

Для `any-con`, `any-any` и `con-con` нативные Pathrex, rpqmatrix,
rpqmatrixGB и Ring принимают manifest с эталоном. Укажите `mode`, `pattern`
и `target_count` для Pathrex либо `pair_count` для матриц и Ring. Эти счётчики
могут различаться при одинаковом отношении. Конвертер не вычисляет oracle
для таких запросов. Матрицы и Ring требуют разных переменных на свободных
концах. Остальные адаптеры в этом workflow проверяют запросы с фиксированным
источником.
