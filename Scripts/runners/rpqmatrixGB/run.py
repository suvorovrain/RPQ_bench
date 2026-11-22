from ..matrix import run_matrix
def run(s):
    run_matrix(s, gb=True)


if __name__ == "__main__":
    from ..workflow import main

    main(default_engine='rpqmatrixGB')
