from ..config import ROOT
from ..runtime import require


def run(s):
    build=s.runtime/"build"
    exe=s.folder/"build/larpq-bench"
    s.run(["gcc","-O3",ROOT/"Scripts/runners/larpq/driver.c","-o",exe,
           "-IDatabases/larpq/include","-Ivendor/GraphBLAS/Include",
           f"-L{build}/larpq/experimental",f"-L{build}/larpq/src","-Lvendor/GraphBLAS/build",
           f"-Wl,-rpath,{build}/larpq/experimental:{build}/larpq/src:{ROOT}/vendor/GraphBLAS/build",
           "-llagraphx","-llagraph","-lgraphblas","-fopenmp"])
    output=s.run([exe,s.data/"matrix/graph.dat",s.query_dir/"larpq.tsv",s.manifest["vertices"],
                  len(s.manifest["labels"]),"--bench",s.args.runs,s.args.warmups])
    queries = {q["id"]: q for q in s.queries}
    samples = {qid: [] for qid in queries}
    verified = set()
    for line in output.splitlines():
        if line.startswith("TIMING;"):
            _, qid, iteration, ms, count = line.split(";")
            require(int(iteration) == len(samples[qid]) and int(count) == queries[qid]["count"], line)
            samples[qid].append(float(ms))
        else:
            qid, values = line.split(";", 1)
            require(qid not in verified, f"Duplicate LA-RPQ endpoints for {qid}")
            s.check(queries[qid], list(map(int, values.split(","))) if values else [])
            verified.add(qid)
    require(verified == queries.keys(), "Missing LA-RPQ endpoint rows")
    for qid, q in queries.items():
        s.add(q, samples[qid], "native_nfa_execute_materialize", "count_every_sample_endpoint_set_last")


if __name__ == "__main__":
    from ..workflow import main

    main(default_engine='larpq')
