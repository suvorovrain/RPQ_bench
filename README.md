# RPQ benchmark harness

Стенд для сравнения движков на регулярных путевых запросах.
[Все 15 конкурентов и их ограничения](Databases/README.md).

| Каталог | Назначение |
| --- | --- |
| [Databases](Databases/README.md) | Закреплённые исходники и гайды движков |
| [Datasets](Datasets/README.md) | Исходные графы и представления для движков |
| [Queries](Queries/README.md) | Запросы по движкам и датасетам |
| [Scripts/converters](Scripts/converters/README.md) | Получение входов, конвертация и oracle |
| [Scripts/runners](Scripts/runners/README.md) | Общий конфиг и запуск отдельных движков |
| [Scripts/analyse](Scripts/analyse/README.md) | Таблицы и гистограммы |

После подготовки графа и сборки нужных движков из корня репозитория:

```bash
python -m Scripts.converters.general.queries
Scripts/runners/run_rpq250k --engines pathrex larpq rpqmatrixGB --name first-run
```

Прогоны сохраняются в `Results/<датасет>/<timestamp>-<name>/`. В `info.txt`
записаны настройки и команды каждого движка. Описание измерений и настройки
для отдельных запросов находятся в [гайде раннера](Scripts/runners/README.md).

Предыдущие прогоны находятся локально в `Results/archive/`, включая
`Results/archive/wikidata/`. Старый `Scripts/benchmarks` сохранён целиком в
`Scripts/analyse/archive/benchmarks/`, включая таблицы и сырые артефакты
Wikidata. [Карта архивов](Scripts/README.md).
