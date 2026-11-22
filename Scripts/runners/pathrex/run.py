import json
from ..config import ROOT
from ..runtime import require
def run(s):
    output=s.folder/"pathrex-native.json"
    s.run([ROOT/"Databases/pathrex/target/release/pathrex","bench","-g",s.graph,
           "-q",s.query_dir/"pathrex.txt","--base-iri",s.manifest["base_iri"],"-a","rpqmatrix",
           "-p",s.options.get("optimizer", "pang-hybrid"),"--runs",s.args.runs,"--warm-up-runs",s.args.warmups,"-o",output])
    native=json.loads(output.read_text());raw=json.loads(output.with_suffix(".runs.json").read_text())
    answers={q["query_id"]:q["algorithms"]["rpqmatrix"] for q in native["results"]}
    data={q["query_id"]:q["algorithms"]["rpqmatrix"] for q in raw["results"]}
    for q in s.queries:
        answer=answers[q["id"]];require(answer["status"]=="ok" and answer["result_count"]==q["count"], f"Wrong Pathrex answer: {answer}")
        samples=data[q["id"]]
        s.add(q,[x/1e6 for x in samples["total_ns"]],"native_evaluator_prepare_execute",
              extra={"ffi_only_samples_ms":[x/1e6 for x in samples["ffi_only_ns"]],
                     "ffi_note":f"Native CLI separately runs {s.args.runs} ffi-only iterations; auxiliary, not main chart"})


if __name__ == "__main__":
    from ..workflow import main

    main(default_engine='pathrex')
