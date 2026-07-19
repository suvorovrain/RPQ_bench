MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
LIBPATH := $(MAKEFILE_DIR)vendor
GRAPH_BLAS_PATH := $(LIBPATH)/GraphBLAS
LAGRAPH_PATH := $(LIBPATH)/LAGraph
BUILD := $(GRAPH_BLAS_PATH)/build
LAGRAPH_BUILD := $(LAGRAPH_PATH)/build
JOBS := $(shell nproc)

la: graphblas lagraph

graphblas: $(BUILD)
	cmake -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
	      -DCMAKE_BUILD_TYPE=Release \
	      -G Ninja -S $(GRAPH_BLAS_PATH) -B $(BUILD)
	cmake --build $(BUILD) --parallel $(JOBS)

lagraph: build $(LAGRAPH_BUILD)
	cmake -DGraphBLAS_DIR=$(BUILD) \
	      -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
	      -DCMAKE_BUILD_TYPE=Release -G Ninja -S $(LAGRAPH_PATH) -B $(LAGRAPH_BUILD)
	cmake --build $(LAGRAPH_BUILD) --parallel $(JOBS)

$(BUILD) $(LAGRAPH_BUILD):
	mkdir -p $@

clean:
	rm -rf $(BUILD) $(LAGRAPH_BUILD)

.PHONY: la graphblas lagraph clean
