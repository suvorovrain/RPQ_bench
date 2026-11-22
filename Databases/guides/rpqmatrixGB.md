# rpqmatrixGB (GraphBLAS baseline)

> Актуальные команды запуска находятся в [гайде раннера](../../Scripts/runners/README.md),
> а подготовка входов — в [гайде конвертеров](../../Scripts/converters/README.md).
> Ниже сохранены команды исторической серии.

Дата проверки: 2026-10-11. Команды — из корня RPQ_bench. Перед запуском выполнить
[общую подготовку](README.md#подготовка-окружения-и-запуск) (окружение/данные).
Фактическая версия и результат находятся в [отчёте](smoke-results.md);
Docker digest / JAR checksum / source SHA — в [runtime-lock.json](runtime-lock.json).

## Сборка и зависимости

Нужны vendor/GraphBLAS и vendor/LAGraph из этого проекта; алгоритмическая ветка
Databases/larpq их не заменяет. Сначала собрать vendor libraries по корневому
README, затем:

```bash
cmake -S Databases/rpq-matrix_GB -B Databases/rpq-matrix_GB/build \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5
cmake --build Databases/rpq-matrix_GB/build --target baselineGB_query -j 2
Results/competitors_250k/venv/bin/python Scripts/competitors/smoke_250k.py rpqmatrixGB
```

CMake добавляет runtime paths для shared GraphBLAS/LAGraph. Если переносить
binary отдельно, сохранить совместимые `.so`/RPATH или настроить loader paths.
Выполненный smoke использовал существующий executable и новый GB input layout.

## Вход

Словари `.SO`/`.P` как у rpqmatrix, но содержимое `.baseline-64/*.mat` другое:
здесь это MatrixMarket text с 1-based coordinates. Нельзя копировать binary
`.mat` из обычного baseline. Dataset base `.dat` может быть пустым: driver
использует имя для поиска словарей/матриц.

```bash
python3 Scripts/converters/mm_to_rpq_GB.py Datasets/rpqbench_250k/pathrex \
  --output-base Datasets/rpqbench_250k/prepared/matrix-gb/graph.dat --copy
Databases/rpq-matrix_GB/build/baselineGB_query \
  Datasets/rpqbench_250k/prepared/matrix-gb/graph.dat \
  Datasets/rpqbench_250k/prepared/queries/matrix.tsv 9 61017 1 0
```

`--copy` делает переносимый layout; без него создаются absolute symlinks.
Метки/вершины сохраняют исходные IDs. Повторные coordinates старых MM input
трактуются как Boolean edge; endpoint graph сверяется по уникальным рёбрам.
Не редактировать hardcoded constants по старому README вслепую: интерфейс
нашего driver уже получает P/N аргументами.

## Запросы и ограничения

Query format такой же, как у [rpqmatrix](rpqmatrix.md): `id pattern#`.
Ответ — cardinality, не witnesses; проверены все шесть counts. Подготовка
матриц/GraphBLAS allocation отдельно от query timing. `OMP_NUM_THREADS=2`
задаётся smoke subprocess; для benchmark проверить фактические GraphBLAS threads.

Дополнительно проверены все 20 upstream шаблонов: counts 20/20. Native
parser ожидает односимвольное имя конечной переменной (`?t#`); `?obj#`
воспринимается ошибочно и может молча дать 0. Converter переименовывает
`?sub`→`?s`, `?obj`→`?t` только в native query files; RDF/Pathrex variables
сохраняются. Это ограничение формата driver, не расхождение RPQ алгоритма.

Источники: [CMake](../rpq-matrix_GB/CMakeLists.txt),
[query driver](../rpq-matrix_GB/src/baselineGB_query.cpp),
[наш converter](../../Scripts/converters/mm_to_rpq_GB.py).

[Все гайды](README.md) · [Семантика RPQ](../reachability.md).
