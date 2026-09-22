#define _POSIX_C_SOURCE 200809L

#include <GraphBLAS.h>

#include <inttypes.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define OK(call)                                                               \
    do {                                                                       \
        GrB_Info info_ = (call);                                               \
        if (info_ != GrB_SUCCESS) {                                            \
            fprintf(stderr, "%s failed with GraphBLAS status %d\n", #call,   \
                    (int)info_);                                               \
            exit(EXIT_FAILURE);                                                \
        }                                                                      \
    } while (0)

typedef struct {
    double mean_ms;
    double median_ms;
    double min_ms;
    double max_ms;
} Stats;

static double now_seconds(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
        perror("clock_gettime");
        exit(EXIT_FAILURE);
    }
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

static int compare_double(const void *lhs, const void *rhs) {
    double a = *(const double *)lhs;
    double b = *(const double *)rhs;
    return (a > b) - (a < b);
}

static Stats summarize(const double *samples, size_t count) {
    double *sorted = malloc(count * sizeof(*sorted));
    if (sorted == NULL) {
        perror("malloc");
        exit(EXIT_FAILURE);
    }
    memcpy(sorted, samples, count * sizeof(*sorted));
    qsort(sorted, count, sizeof(*sorted), compare_double);

    double sum = 0.0;
    for (size_t i = 0; i < count; ++i) {
        sum += sorted[i];
    }
    Stats stats = {
        .mean_ms = sum / (double)count,
        .median_ms = count % 2 == 0
                         ? (sorted[count / 2 - 1] + sorted[count / 2]) / 2.0
                         : sorted[count / 2],
        .min_ms = sorted[0],
        .max_ms = sorted[count - 1],
    };
    free(sorted);
    return stats;
}

static uint64_t parse_u64(const char *value, const char *name) {
    char *end = NULL;
    unsigned long long parsed = strtoull(value, &end, 10);
    if (value[0] == '\0' || end == NULL || *end != '\0' || parsed == 0) {
        fprintf(stderr, "invalid %s: %s\n", name, value);
        exit(EXIT_FAILURE);
    }
    return (uint64_t)parsed;
}

static void print_stats(const char *name, Stats stats) {
    printf("%-28s median %10.3f us  mean %10.3f us  min %10.3f us  max %10.3f us\n",
           name, stats.median_ms * 1000.0, stats.mean_ms * 1000.0,
           stats.min_ms * 1000.0, stats.max_ms * 1000.0);
}

int main(int argc, char **argv) {
    if (argc > 6) {
        fprintf(stderr,
                "usage: %s [dimension] [degree] [warmups] [runs] [threads]\n",
                argv[0]);
        return EXIT_FAILURE;
    }

    uint64_t dimension = argc > 1 ? parse_u64(argv[1], "dimension") : 10000000;
    uint64_t degree = argc > 2 ? parse_u64(argv[2], "degree") : 8;
    size_t warmups = (size_t)(argc > 3 ? parse_u64(argv[3], "warmups") : 2);
    size_t runs = (size_t)(argc > 4 ? parse_u64(argv[4], "runs") : 10);
    int threads = (int)(argc > 5 ? parse_u64(argv[5], "threads") : 1);

    if (degree > dimension || dimension > UINT64_MAX / degree) {
        fprintf(stderr, "dimension * degree overflows or degree exceeds dimension\n");
        return EXIT_FAILURE;
    }
    uint64_t entries_u64 = dimension * degree;
    if (entries_u64 > SIZE_MAX) {
        fprintf(stderr, "number of entries does not fit size_t\n");
        return EXIT_FAILURE;
    }
    size_t entries = (size_t)entries_u64;

    double tuple_gib = (double)entries *
                       (2.0 * sizeof(GrB_Index) + sizeof(bool)) /
                       (1024.0 * 1024.0 * 1024.0);
    printf("dimension=%" PRIu64 ", degree=%" PRIu64 ", nnz=%zu, warmups=%zu, "
           "runs=%zu, threads=%d\n",
           dimension, degree, entries, warmups, runs, threads);
    printf("temporary COO arrays: approximately %.2f GiB\n", tuple_gib);

    OK(GrB_init(GrB_NONBLOCKING));
    OK(GxB_Global_Option_set(GxB_NTHREADS, threads));

    GrB_Index *rows = malloc(entries * sizeof(*rows));
    GrB_Index *cols = malloc(entries * sizeof(*cols));
    bool *values = malloc(entries * sizeof(*values));
    if (rows == NULL || cols == NULL || values == NULL) {
        fprintf(stderr, "cannot allocate COO arrays for %zu entries\n", entries);
        free(rows);
        free(cols);
        free(values);
        OK(GrB_finalize());
        return EXIT_FAILURE;
    }

    for (uint64_t row = 0; row < dimension; ++row) {
        for (uint64_t edge = 0; edge < degree; ++edge) {
            size_t index = (size_t)(row * degree + edge);
            rows[index] = (GrB_Index)row;
            cols[index] = (GrB_Index)((row * 11400714819323198485ull +
                                       edge * 7046029254386353131ull) %
                                      dimension);
            values[index] = true;
        }
    }

    GrB_Matrix adjacency = GrB_NULL;
    OK(GrB_Matrix_new(&adjacency, GrB_BOOL, dimension, dimension));
    OK(GxB_Matrix_Option_set(adjacency, GxB_FORMAT, GxB_BY_ROW));
    double build_start = now_seconds();
    OK(GrB_Matrix_build_BOOL(adjacency, rows, cols, values, entries,
                             GrB_LOR));
    OK(GrB_Matrix_wait(adjacency, GrB_MATERIALIZE));
    printf("matrix build: %.3f s\n", now_seconds() - build_start);
    free(rows);
    free(cols);
    free(values);

    GrB_Index adjacency_nnz = 0;
    OK(GrB_Matrix_nvals(&adjacency_nnz, adjacency));
    GrB_Index source = (GrB_Index)(dimension / 2);

    GrB_Matrix bound_matrix = GrB_NULL;
    GrB_Matrix left_matrix_result = GrB_NULL;
    GrB_Matrix right_matrix_result = GrB_NULL;
    GrB_Vector bound_vector = GrB_NULL;
    GrB_Vector left_vector_result = GrB_NULL;
    GrB_Vector right_vector_result = GrB_NULL;
    OK(GrB_Matrix_new(&bound_matrix, GrB_BOOL, dimension, dimension));
    OK(GxB_Matrix_Option_set(bound_matrix, GxB_FORMAT, GxB_BY_ROW));
    OK(GrB_Matrix_setElement_BOOL(bound_matrix, true, source, source));
    OK(GrB_Matrix_wait(bound_matrix, GrB_MATERIALIZE));
    OK(GrB_Matrix_new(&left_matrix_result, GrB_BOOL, dimension, dimension));
    OK(GxB_Matrix_Option_set(left_matrix_result, GxB_FORMAT, GxB_BY_ROW));
    OK(GrB_Matrix_new(&right_matrix_result, GrB_BOOL, dimension, dimension));
    OK(GxB_Matrix_Option_set(right_matrix_result, GxB_FORMAT, GxB_BY_COL));

    OK(GrB_Vector_new(&bound_vector, GrB_BOOL, dimension));
    OK(GrB_Vector_setElement_BOOL(bound_vector, true, source));
    OK(GrB_Vector_wait(bound_vector, GrB_MATERIALIZE));
    OK(GrB_Vector_new(&left_vector_result, GrB_BOOL, dimension));
    OK(GrB_Vector_new(&right_vector_result, GrB_BOOL, dimension));

    for (size_t i = 0; i < warmups; ++i) {
        OK(GrB_mxm(left_matrix_result, GrB_NULL, GrB_NULL, GxB_ANY_PAIR_BOOL,
                   bound_matrix, adjacency, GrB_DESC_R));
        OK(GrB_Matrix_wait(left_matrix_result, GrB_MATERIALIZE));
        OK(GrB_vxm(left_vector_result, GrB_NULL, GrB_NULL, GxB_ANY_PAIR_BOOL,
                   bound_vector, adjacency, GrB_DESC_R));
        OK(GrB_Vector_wait(left_vector_result, GrB_MATERIALIZE));
    }

    double *left_matrix_ms = malloc(runs * sizeof(*left_matrix_ms));
    double *left_vector_ms = malloc(runs * sizeof(*left_vector_ms));
    double *right_matrix_ms = malloc(runs * sizeof(*right_matrix_ms));
    double *right_vector_ms = malloc(runs * sizeof(*right_vector_ms));
    if (left_matrix_ms == NULL || left_vector_ms == NULL ||
        right_matrix_ms == NULL || right_vector_ms == NULL) {
        fprintf(stderr, "cannot allocate timing samples\n");
        return EXIT_FAILURE;
    }

    for (size_t i = 0; i < runs; ++i) {
        double start = now_seconds();
        OK(GrB_mxm(left_matrix_result, GrB_NULL, GrB_NULL, GxB_ANY_PAIR_BOOL,
                   bound_matrix, adjacency, GrB_DESC_R));
        OK(GrB_Matrix_wait(left_matrix_result, GrB_MATERIALIZE));
        left_matrix_ms[i] = (now_seconds() - start) * 1000.0;

        start = now_seconds();
        OK(GrB_vxm(left_vector_result, GrB_NULL, GrB_NULL, GxB_ANY_PAIR_BOOL,
                   bound_vector, adjacency, GrB_DESC_R));
        OK(GrB_Vector_wait(left_vector_result, GrB_MATERIALIZE));
        left_vector_ms[i] = (now_seconds() - start) * 1000.0;

    }

    GrB_Index left_matrix_nnz = 0, left_vector_nnz = 0;
    GrB_Index right_matrix_nnz = 0, right_vector_nnz = 0;
    OK(GrB_Matrix_nvals(&left_matrix_nnz, left_matrix_result));
    OK(GrB_Vector_nvals(&left_vector_nnz, left_vector_result));

    double convert_start = now_seconds();
    OK(GxB_Matrix_Option_set(adjacency, GxB_FORMAT, GxB_BY_COL));
    OK(GrB_Matrix_wait(adjacency, GrB_MATERIALIZE));
    printf("CSR to CSC conversion: %.3f s (outside timed region)\n",
           now_seconds() - convert_start);

    for (size_t i = 0; i < warmups; ++i) {
        OK(GrB_mxm(right_matrix_result, GrB_NULL, GrB_NULL, GxB_ANY_PAIR_BOOL,
                   adjacency, bound_matrix, GrB_DESC_R));
        OK(GrB_Matrix_wait(right_matrix_result, GrB_MATERIALIZE));
        OK(GrB_mxv(right_vector_result, GrB_NULL, GrB_NULL, GxB_ANY_PAIR_BOOL,
                   adjacency, bound_vector, GrB_DESC_R));
        OK(GrB_Vector_wait(right_vector_result, GrB_MATERIALIZE));
    }

    for (size_t i = 0; i < runs; ++i) {
        double start = now_seconds();
        OK(GrB_mxm(right_matrix_result, GrB_NULL, GrB_NULL, GxB_ANY_PAIR_BOOL,
                   adjacency, bound_matrix, GrB_DESC_R));
        OK(GrB_Matrix_wait(right_matrix_result, GrB_MATERIALIZE));
        right_matrix_ms[i] = (now_seconds() - start) * 1000.0;

        start = now_seconds();
        OK(GrB_mxv(right_vector_result, GrB_NULL, GrB_NULL, GxB_ANY_PAIR_BOOL,
                   adjacency, bound_vector, GrB_DESC_R));
        OK(GrB_Vector_wait(right_vector_result, GrB_MATERIALIZE));
        right_vector_ms[i] = (now_seconds() - start) * 1000.0;
    }

    OK(GrB_Matrix_nvals(&right_matrix_nnz, right_matrix_result));
    OK(GrB_Vector_nvals(&right_vector_nnz, right_vector_result));
    if (left_matrix_nnz != left_vector_nnz ||
        right_matrix_nnz != right_vector_nnz) {
        fprintf(stderr,
                "result mismatch: left mxm/vxm=%" PRIu64 "/%" PRIu64
                ", right mxm/mxv=%" PRIu64 "/%" PRIu64 "\n",
                (uint64_t)left_matrix_nnz, (uint64_t)left_vector_nnz,
                (uint64_t)right_matrix_nnz, (uint64_t)right_vector_nnz);
        return EXIT_FAILURE;
    }

    Stats left_matrix_stats = summarize(left_matrix_ms, runs);
    Stats left_vector_stats = summarize(left_vector_ms, runs);
    Stats right_matrix_stats = summarize(right_matrix_ms, runs);
    Stats right_vector_stats = summarize(right_vector_ms, runs);
    printf("adjacency nnz=%" PRIu64 ", left result nnz=%" PRIu64
           ", right result nnz=%" PRIu64 "\n",
           (uint64_t)adjacency_nnz, (uint64_t)left_matrix_nnz,
           (uint64_t)right_matrix_nnz);
    print_stats("D(one entry) x A [mxm]", left_matrix_stats);
    print_stats("v(one entry) x A [vxm]", left_vector_stats);
    printf("left-bound median vector speedup:  %.2fx\n\n",
           left_matrix_stats.median_ms / left_vector_stats.median_ms);
    print_stats("A x D(one entry) [mxm]", right_matrix_stats);
    print_stats("A x v(one entry) [mxv]", right_vector_stats);
    printf("right-bound median vector speedup: %.2fx\n",
           right_matrix_stats.median_ms / right_vector_stats.median_ms);

    free(left_matrix_ms);
    free(left_vector_ms);
    free(right_matrix_ms);
    free(right_vector_ms);
    OK(GrB_Vector_free(&right_vector_result));
    OK(GrB_Vector_free(&left_vector_result));
    OK(GrB_Vector_free(&bound_vector));
    OK(GrB_Matrix_free(&right_matrix_result));
    OK(GrB_Matrix_free(&left_matrix_result));
    OK(GrB_Matrix_free(&bound_matrix));
    OK(GrB_Matrix_free(&adjacency));
    OK(GrB_finalize());
    return EXIT_SUCCESS;
}
