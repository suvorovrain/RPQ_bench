# Native сборки для smoke

Команды из корня репозитория. Новые build directories находятся в `.rpq-runtime/`,
поэтому upstream исходники не патчатся. Нужны GCC/G++, CMake, OpenMP; для
MillenniumDB также ICU/OpenSSL/ncurses development packages. Сборка может занять
несколько минут; особенно первая сборка GraphBLAS внутри Pathrex.
Для сборки сначала создайте `.rpq-runtime/tools`.


## Pathrex и матричные baseline

Из корня репозитория после инициализации submodules:

```bash
git submodule update --init --recursive
cargo build --release --manifest-path Databases/pathrex/Cargo.toml --features bench

cmake -S Databases/rpq-matrix -B Databases/rpq-matrix/build -DCMAKE_BUILD_TYPE=Release
cmake --build Databases/rpq-matrix/build --target baseline_query create_pairs baseline_build -j 2

cmake -S vendor/GraphBLAS -B vendor/GraphBLAS/build \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON \
  -DGRAPHBLAS_USE_CUDA=OFF -DSUITESPARSE_DEMOS=OFF
cmake --build vendor/GraphBLAS/build -j 2
cmake -S vendor/LAGraph -B vendor/LAGraph/build \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DBUILD_TESTING=OFF \
  -DGraphBLAS_DIR="$PWD/vendor/GraphBLAS/build"
cmake --build vendor/LAGraph/build -j 2
cmake -S Databases/rpq-matrix_GB -B Databases/rpq-matrix_GB/build -DCMAKE_BUILD_TYPE=Release
cmake --build Databases/rpq-matrix_GB/build --target baselineGB_query -j 2
```

Для старого CMakeLists под CMake 4 может потребоваться
`-DCMAKE_POLICY_VERSION_MINIMUM=3.5`. Rust и Cargo версии 1.90 или новее
нужны для сборки Pathrex.

## LARPQ

Подключённый `Databases/larpq` — библиотека LAGraph с experimental RPQ API,
не готовый executable. Использован уже собранный vendor GraphBLAS 10.3.1.
Если его нет, сначала собрать по командам выше. Эти команды были выполнены:

```bash
cmake -S Databases/larpq -B .rpq-runtime/build/larpq \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DBUILD_TESTING=OFF \
  -DLAGRAPH_EXPERIMENTAL=ON -DGraphBLAS_ROOT="$PWD/vendor/GraphBLAS"
cmake --build .rpq-runtime/build/larpq --target LAGraphX -j 2

gcc Scripts/runners/larpq/driver.c \
  -o .rpq-runtime/build/larpq-smoke \
  -IDatabases/larpq/include -Ivendor/GraphBLAS/Include \
  -L.rpq-runtime/build/larpq/experimental \
  -L.rpq-runtime/build/larpq/src -Lvendor/GraphBLAS/build \
  -Wl,-rpath,"$PWD/.rpq-runtime/build/larpq/experimental:$PWD/.rpq-runtime/build/larpq/src:$PWD/vendor/GraphBLAS/build" \
  -llagraphx -llagraph -lgraphblas -fopenmp
```

В этой комбинации CheckGraph требует BY_ROW для adjacency и cached transpose.
Наш harness задаёт формат явно, в том числе для односостоянийного автомата.
Нельзя просто использовать API из vendor/LAGraph вместо этой ветки: это другой
checkout и другой интерфейс. Не менять оба backend одновременно без проверки.

## MillenniumDB

Pinned CMake ожидает Boost 1.82 headers в `third_party/boost_1_82/include`;
первоначальная сборка упала без них. Upstream setup script скачивает тот же tarball.
Полный setup с системными установками не запускался; использована только header
dependency, игнорируемая upstream Git.

```bash
curl -fL https://archives.boost.io/release/1.82.0/source/boost_1_82_0.tar.gz \
  -o .rpq-runtime/tools/boost.tar.gz
mkdir -p Databases/millenniumdb/third_party/boost_1_82/include
tar -xzf .rpq-runtime/tools/boost.tar.gz --strip-components=1 \
  -C Databases/millenniumdb/third_party/boost_1_82/include boost_1_82_0/boost
cmake -S Databases/millenniumdb -B .rpq-runtime/build/millenniumdb \
  -DCMAKE_BUILD_TYPE=Release
cmake --build .rpq-runtime/build/millenniumdb --target mdb -j 2
```

Текущий executable — `mdb` с subcommands. Старые `mdb-import` / `mdb-server`
из vendor scripts не соответствуют этому checkout. Source build выполнен
без изменения tracked CMake/исходников.

## Ring-RPQ

Нужен авторский fork SDSL, а не произвольный distribution package sdsl.
Точная ревизия записана в runtime-lock.json. В командах checkout берётся из lock;
инициализация nested googletest/libdivsufsort нужна для SDSL CMake.

```bash
git clone https://github.com/adriangbrandon/sdsl-lite.git .rpq-runtime/tools/sdsl-lite
RPQ_SDSL_SHA=$(python3 -c 'import json; print(json.load(open("Databases/guides/runtime-lock.json"))["sources"]["sdsl"])')
git -C .rpq-runtime/tools/sdsl-lite checkout "$RPQ_SDSL_SHA"
git -C .rpq-runtime/tools/sdsl-lite submodule update --init --recursive
cmake -S .rpq-runtime/tools/sdsl-lite -B .rpq-runtime/build/sdsl \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DCMAKE_INSTALL_PREFIX="$PWD/.rpq-runtime/tools/sdsl-install"
cmake --build .rpq-runtime/build/sdsl -j 2
cmake --install .rpq-runtime/build/sdsl
cmake -S Databases/ring-rpq -B .rpq-runtime/build/ring \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DCMAKE_CXX_FLAGS="-I$PWD/.rpq-runtime/tools/sdsl-install/include" \
  -DCMAKE_EXE_LINKER_FLAGS="-L$PWD/.rpq-runtime/tools/sdsl-install/lib"
cmake --build .rpq-runtime/build/ring \
  --target build-index-basic query-index-basic -j 2
```

Не нужен install в домашние `~/include`/`~/lib`: CMake flags перенаправляют
зависимости в локальный prefix. Upstream Ring CMake жёстко задаёт Debug;
это не оптимальная benchmark-сборка, даже при успешном smoke. Для измерений
выбрать и явно зафиксировать Release configuration после отдельного изменения
в изолированной копии. Nested Ring `external/malloc_count` не понадобился
двум выбранным targets; это не проверка всех targets/вариантов RingA/RingAB.

## Проверка собранных Pathrex и матриц

Их команды и дополнительные условия — в [pathrex.md](pathrex.md),
[rpqmatrix.md](rpqmatrix.md), [rpqmatrixGB.md](rpqmatrixGB.md).
Во время первых попыток найден старый Pathrex executable, который не знал
`pang-hybrid`/`sampling`: перед запуском сверять help и пересобирать текущий
source, не выводить список доступных оптимизаторов только из git revision.
