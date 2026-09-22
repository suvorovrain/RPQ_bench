#define _POSIX_C_SOURCE 200809L

#include <LAGraph.h>

#include <inttypes.h>
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
            fprintf(stderr, "%s failed: status=%d, msg=%s\n", #call,         \
                    (int)info_, msg);                                          \
            exit(EXIT_FAILURE);                                                \
        }                                                                      \
    } while (0)

typedef GrB_Index (*PlanFn)(void);

static char msg[LAGRAPH_MSG_LEN];
static GrB_Index n;
static GrB_Matrix editor;
static GrB_Matrix creator;
static GrB_Matrix predecessor;
static GrB_Matrix coauthor;
static GrB_Matrix bound_matrix;
static GrB_Vector bound_vector;

static double now_seconds(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
        perror("clock_gettime");
        exit(EXIT_FAILURE);
    }
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

static int compare_double(const void *lhs, const void *rhs) {
    const double a = *(const double *)lhs;
    const double b = *(const double *)rhs;
    return (a > b) - (a < b);
}

static GrB_Matrix new_matrix(void) {
    GrB_Matrix result = GrB_NULL;
    OK(GrB_Matrix_new(&result, GrB_BOOL, n, n));
    OK(GxB_Matrix_Option_set(result, GxB_FORMAT, GxB_BY_ROW));
    return result;
}

static GrB_Vector new_vector(void) {
    GrB_Vector result = GrB_NULL;
    OK(GrB_Vector_new(&result, GrB_BOOL, n));
    return result;
}

static GrB_Matrix matrix_union(GrB_Matrix lhs, GrB_Matrix rhs) {
    GrB_Matrix result = new_matrix();
    OK(GrB_eWiseAdd(result, GrB_NULL, GrB_NULL, GxB_ANY_BOOL,
                    lhs, rhs, GrB_DESC_R));
    return result;
}

static GrB_Matrix matrix_multiply(GrB_Matrix lhs, GrB_Matrix rhs) {
    GrB_Matrix result = new_matrix();
    OK(GrB_mxm(result, GrB_NULL, GrB_NULL, GxB_ANY_PAIR_BOOL,
               lhs, rhs, GrB_DESC_R));
    return result;
}

static GrB_Vector vector_union(GrB_Vector lhs, GrB_Vector rhs) {
    GrB_Vector result = new_vector();
    OK(GrB_eWiseAdd(result, GrB_NULL, GrB_NULL, GxB_ANY_BOOL,
                    lhs, rhs, GrB_DESC_R));
    return result;
}

static GrB_Vector vector_multiply(GrB_Vector lhs, GrB_Matrix rhs) {
    GrB_Vector result = new_vector();
    OK(GrB_vxm(result, GrB_NULL, GrB_NULL, GxB_ANY_PAIR_BOOL,
               lhs, rhs, GrB_DESC_R));
    return result;
}

static GrB_Index finish_matrix(GrB_Matrix result) {
    GrB_Index count = 0;
    OK(GrB_Matrix_wait(result, GrB_MATERIALIZE));
    OK(GrB_Matrix_nvals(&count, result));
    OK(GrB_Matrix_free(&result));
    return count;
}

static GrB_Index finish_vector(GrB_Vector result) {
    GrB_Index count = 0;
    OK(GrB_Vector_wait(result, GrB_MATERIALIZE));
    OK(GrB_Vector_nvals(&count, result));
    OK(GrB_Vector_free(&result));
    return count;
}

// D x ((editor | creator) x (predecessor | coauthor))
static GrB_Index q17_unbound_product_first(void) {
    GrB_Matrix left = matrix_union(editor, creator);
    GrB_Matrix right = matrix_union(predecessor, coauthor);
    GrB_Matrix product = matrix_multiply(left, right);
    GrB_Matrix result = matrix_multiply(bound_matrix, product);
    OK(GrB_Matrix_free(&product));
    OK(GrB_Matrix_free(&right));
    OK(GrB_Matrix_free(&left));
    return finish_matrix(result);
}

// (D x (editor | creator)) x (predecessor | coauthor)
static GrB_Index q17_bound_first(void) {
    GrB_Matrix left = matrix_union(editor, creator);
    GrB_Matrix seed = matrix_multiply(bound_matrix, left);
    GrB_Matrix right = matrix_union(predecessor, coauthor);
    GrB_Matrix result = matrix_multiply(seed, right);
    OK(GrB_Matrix_free(&right));
    OK(GrB_Matrix_free(&seed));
    OK(GrB_Matrix_free(&left));
    return finish_matrix(result);
}

// ((D x editor) | (D x creator)) x (predecessor | coauthor)
static GrB_Index q17_distributed_matrix(void) {
    GrB_Matrix from_editor = matrix_multiply(bound_matrix, editor);
    GrB_Matrix from_creator = matrix_multiply(bound_matrix, creator);
    GrB_Matrix seed = matrix_union(from_editor, from_creator);
    GrB_Matrix right = matrix_union(predecessor, coauthor);
    GrB_Matrix result = matrix_multiply(seed, right);
    OK(GrB_Matrix_free(&right));
    OK(GrB_Matrix_free(&seed));
    OK(GrB_Matrix_free(&from_creator));
    OK(GrB_Matrix_free(&from_editor));
    return finish_matrix(result);
}

// (((D x editor) | (D x creator)) x predecessor) |
// (((D x editor) | (D x creator)) x coauthor)
static GrB_Index q17_fully_distributed_matrix(void) {
    GrB_Matrix from_editor = matrix_multiply(bound_matrix, editor);
    GrB_Matrix from_creator = matrix_multiply(bound_matrix, creator);
    GrB_Matrix seed = matrix_union(from_editor, from_creator);
    GrB_Matrix via_predecessor = matrix_multiply(seed, predecessor);
    GrB_Matrix via_coauthor = matrix_multiply(seed, coauthor);
    GrB_Matrix result = matrix_union(via_predecessor, via_coauthor);
    OK(GrB_Matrix_free(&via_coauthor));
    OK(GrB_Matrix_free(&via_predecessor));
    OK(GrB_Matrix_free(&seed));
    OK(GrB_Matrix_free(&from_creator));
    OK(GrB_Matrix_free(&from_editor));
    return finish_matrix(result);
}

// Vector equivalent of the fully distributed matrix plan.
static GrB_Index q17_fully_distributed_vector(void) {
    GrB_Vector from_editor = vector_multiply(bound_vector, editor);
    GrB_Vector from_creator = vector_multiply(bound_vector, creator);
    GrB_Vector seed = vector_union(from_editor, from_creator);
    GrB_Vector via_predecessor = vector_multiply(seed, predecessor);
    GrB_Vector via_coauthor = vector_multiply(seed, coauthor);
    GrB_Vector result = vector_union(via_predecessor, via_coauthor);
    OK(GrB_Vector_free(&via_coauthor));
    OK(GrB_Vector_free(&via_predecessor));
    OK(GrB_Vector_free(&seed));
    OK(GrB_Vector_free(&from_creator));
    OK(GrB_Vector_free(&from_editor));
    return finish_vector(result);
}

static GrB_Matrix matrix_frontier_closure(GrB_Matrix seed, GrB_Matrix step) {
    GrB_Matrix reached = GrB_NULL;
    GrB_Matrix frontier = GrB_NULL;
    OK(GrB_Matrix_dup(&reached, seed));
    OK(GrB_Matrix_dup(&frontier, seed));
    GrB_Index frontier_nnz = 0;
    OK(GrB_Matrix_nvals(&frontier_nnz, frontier));
    while (frontier_nnz > 0) {
        OK(GrB_mxm(frontier, reached, GrB_NULL, GxB_ANY_PAIR_BOOL,
                   frontier, step, GrB_DESC_RSC));
        OK(GrB_Matrix_nvals(&frontier_nnz, frontier));
        OK(GrB_eWiseAdd(reached, GrB_NULL, GrB_NULL, GxB_ANY_BOOL,
                        reached, frontier, GrB_NULL));
    }
    OK(GrB_Matrix_free(&frontier));
    return reached;
}

static GrB_Vector vector_frontier_closure(GrB_Vector seed, GrB_Matrix step) {
    GrB_Vector reached = GrB_NULL;
    GrB_Vector frontier = GrB_NULL;
    OK(GrB_Vector_dup(&reached, seed));
    OK(GrB_Vector_dup(&frontier, seed));
    GrB_Index frontier_nnz = 0;
    OK(GrB_Vector_nvals(&frontier_nnz, frontier));
    while (frontier_nnz > 0) {
        OK(GrB_vxm(frontier, reached, GrB_NULL, GxB_ANY_PAIR_BOOL,
                   frontier, step, GrB_DESC_RSC));
        OK(GrB_Vector_nvals(&frontier_nnz, frontier));
        OK(GrB_eWiseAdd(reached, GrB_NULL, GrB_NULL, GxB_ANY_BOOL,
                        reached, frontier, GrB_NULL));
    }
    OK(GrB_Vector_free(&frontier));
    return reached;
}

// RStar-like evaluation of D x (editor | creator) x
// (predecessor | coauthor)* using matrix frontiers.
static GrB_Index q19_frontier_matrix(void) {
    GrB_Matrix left = matrix_union(editor, creator);
    GrB_Matrix seed = matrix_multiply(bound_matrix, left);
    GrB_Matrix step = matrix_union(predecessor, coauthor);
    GrB_Matrix result = matrix_frontier_closure(seed, step);
    OK(GrB_Matrix_free(&step));
    OK(GrB_Matrix_free(&seed));
    OK(GrB_Matrix_free(&left));
    return finish_matrix(result);
}

// Matrix frontier with the bound restriction distributed through the first
// alternative before the closure starts.
static GrB_Index q19_distributed_frontier_matrix(void) {
    GrB_Matrix from_editor = matrix_multiply(bound_matrix, editor);
    GrB_Matrix from_creator = matrix_multiply(bound_matrix, creator);
    GrB_Matrix seed = matrix_union(from_editor, from_creator);
    GrB_Matrix step = matrix_union(predecessor, coauthor);
    GrB_Matrix result = matrix_frontier_closure(seed, step);
    OK(GrB_Matrix_free(&step));
    OK(GrB_Matrix_free(&seed));
    OK(GrB_Matrix_free(&from_creator));
    OK(GrB_Matrix_free(&from_editor));
    return finish_matrix(result);
}

// Same RStar-like plan while keeping the bound frontier as a vector.
static GrB_Index q19_frontier_vector(void) {
    GrB_Vector from_editor = vector_multiply(bound_vector, editor);
    GrB_Vector from_creator = vector_multiply(bound_vector, creator);
    GrB_Vector seed = vector_union(from_editor, from_creator);
    GrB_Matrix step = matrix_union(predecessor, coauthor);
    GrB_Vector result = vector_frontier_closure(seed, step);
    OK(GrB_Matrix_free(&step));
    OK(GrB_Vector_free(&seed));
    OK(GrB_Vector_free(&from_creator));
    OK(GrB_Vector_free(&from_editor));
    return finish_vector(result);
}

static void benchmark(const char *name, PlanFn plan, size_t warmups,
                      size_t runs, GrB_Index *reference_count) {
    for (size_t i = 0; i < warmups; ++i) {
        (void)plan();
    }

    double *samples = malloc(runs * sizeof(*samples));
    if (samples == NULL) {
        perror("malloc");
        exit(EXIT_FAILURE);
    }
    GrB_Index count = 0;
    for (size_t i = 0; i < runs; ++i) {
        const double start = now_seconds();
        count = plan();
        samples[i] = (now_seconds() - start) * 1000.0;
    }

    double sum = 0.0;
    for (size_t i = 0; i < runs; ++i) {
        sum += samples[i];
    }
    qsort(samples, runs, sizeof(*samples), compare_double);
    const double median = runs % 2 == 0
                              ? (samples[runs / 2 - 1] + samples[runs / 2]) / 2.0
                              : samples[runs / 2];

    if (*reference_count == UINT64_MAX) {
        *reference_count = count;
    } else if (count != *reference_count) {
        fprintf(stderr, "%s produced nnz=%" PRIu64 ", expected=%" PRIu64 "\n",
                name, (uint64_t)count, (uint64_t)*reference_count);
        exit(EXIT_FAILURE);
    }

    printf("%-38s nnz=%-8" PRIu64 " median=%10.3f ms mean=%10.3f ms "
           "min=%10.3f ms max=%10.3f ms\n",
           name, (uint64_t)count, median, sum / (double)runs,
           samples[0], samples[runs - 1]);
    fflush(stdout);
    free(samples);
}

static GrB_Matrix load_matrix(const char *path) {
    FILE *file = fopen(path, "r");
    if (file == NULL) {
        perror(path);
        exit(EXIT_FAILURE);
    }
    GrB_Matrix matrix = GrB_NULL;
    const double start = now_seconds();
    OK(LAGraph_MMRead(&matrix, file, msg));
    fclose(file);
    OK(GxB_Matrix_Option_set(matrix, GxB_FORMAT, GxB_BY_ROW));
    OK(GrB_Matrix_wait(matrix, GrB_MATERIALIZE));
    GrB_Index count = 0;
    OK(GrB_Matrix_nvals(&count, matrix));
    printf("loaded %-12s nnz=%-10" PRIu64 " in %.3f s\n",
           path, (uint64_t)count, now_seconds() - start);
    fflush(stdout);
    return matrix;
}

static uint64_t parse_u64(const char *text, const char *name) {
    char *end = NULL;
    const unsigned long long value = strtoull(text, &end, 10);
    if (text[0] == '\0' || end == NULL || *end != '\0') {
        fprintf(stderr, "invalid %s: %s\n", name, text);
        exit(EXIT_FAILURE);
    }
    return (uint64_t)value;
}

int main(int argc, char **argv) {
    if (argc < 3 || argc > 6) {
        fprintf(stderr,
                "usage: %s MATRIX_DIR ZERO_BASED_VERTEX [warmups] [runs] [threads]\n",
                argv[0]);
        return EXIT_FAILURE;
    }
    const char *dir = argv[1];
    const GrB_Index vertex = (GrB_Index)parse_u64(argv[2], "vertex");
    const size_t warmups = (size_t)(argc > 3 ? parse_u64(argv[3], "warmups") : 2);
    const size_t runs = (size_t)(argc > 4 ? parse_u64(argv[4], "runs") : 5);
    const int threads = (int)(argc > 5 ? parse_u64(argv[5], "threads") : 1);
    if (runs == 0) {
        fprintf(stderr, "runs must be greater than zero\n");
        return EXIT_FAILURE;
    }

    OK(LAGraph_Init(msg));
    OK(GxB_Global_Option_set(GxB_NTHREADS, threads));

    char path[4096];
#define LOAD(variable, index)                                                  \
    do {                                                                       \
        snprintf(path, sizeof(path), "%s/%d.txt", dir, index);                \
        variable = load_matrix(path);                                          \
    } while (0)
    LOAD(editor, 5);
    LOAD(creator, 2);
    LOAD(predecessor, 9);
    LOAD(coauthor, 6);
#undef LOAD

    OK(GrB_Matrix_nrows(&n, creator));
    if (vertex >= n) {
        fprintf(stderr, "vertex %" PRIu64 " is outside [0, %" PRIu64 ")\n",
                (uint64_t)vertex, (uint64_t)n);
        return EXIT_FAILURE;
    }
    OK(GrB_Matrix_new(&bound_matrix, GrB_BOOL, n, n));
    OK(GxB_Matrix_Option_set(bound_matrix, GxB_FORMAT, GxB_BY_ROW));
    OK(GrB_Matrix_setElement_BOOL(bound_matrix, true, vertex, vertex));
    OK(GrB_Matrix_wait(bound_matrix, GrB_MATERIALIZE));
    OK(GrB_Vector_new(&bound_vector, GrB_BOOL, n));
    OK(GrB_Vector_setElement_BOOL(bound_vector, true, vertex));
    OK(GrB_Vector_wait(bound_vector, GrB_MATERIALIZE));

    printf("dimension=%" PRIu64 ", vertex=%" PRIu64
           ", warmups=%zu, runs=%zu, threads=%d\n\n",
           (uint64_t)n, (uint64_t)vertex, warmups, runs, threads);

    GrB_Index q17_count = UINT64_MAX;
    puts("con-any/17 equivalent plans:");
    benchmark("D x ((E|C) x (P|Co))", q17_unbound_product_first,
              warmups, runs, &q17_count);
    benchmark("(D x (E|C)) x (P|Co)", q17_bound_first,
              warmups, runs, &q17_count);
    benchmark("((D x E)|(D x C)) x (P|Co)", q17_distributed_matrix,
              warmups, runs, &q17_count);
    benchmark("fully distributed matrix", q17_fully_distributed_matrix,
              warmups, runs, &q17_count);
    benchmark("fully distributed vector", q17_fully_distributed_vector,
              warmups, runs, &q17_count);

    GrB_Index q19_count = UINT64_MAX;
    puts("\ncon-any/19 frontier plans:");
    benchmark("matrix RStar frontier", q19_frontier_matrix,
              warmups, runs, &q19_count);
    benchmark("distributed matrix RStar frontier",
              q19_distributed_frontier_matrix,
              warmups, runs, &q19_count);
    benchmark("vector RStar frontier", q19_frontier_vector,
              warmups, runs, &q19_count);

    OK(GrB_Vector_free(&bound_vector));
    OK(GrB_Matrix_free(&bound_matrix));
    OK(GrB_Matrix_free(&coauthor));
    OK(GrB_Matrix_free(&predecessor));
    OK(GrB_Matrix_free(&creator));
    OK(GrB_Matrix_free(&editor));
    OK(LAGraph_Finalize(msg));
    return EXIT_SUCCESS;
}
