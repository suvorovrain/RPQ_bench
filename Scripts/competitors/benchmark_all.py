#!/usr/bin/env python3
"""100 warm query measurements for the 15 competitors on the shared Basic4.

Loads/imports each graph once, runs engines sequentially, checks answers outside
timers, saves every sample. Pathrex is RPQMatrix/pang-hybrid only. Different native,
embedded and network timing boundaries are recorded, never hidden.
"""
import argparse
from collections import defaultdict
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import time
from datetime import datetime, timezone

import smoke_250k as sm
from prepare_basic import prepare

ROOT=sm.ROOT
ENGINES=["larpq","rpqmatrix","rpqmatrixGB","pathrex","ring","duckdb","kuzu",
         "jena","postgres","millenniumdb","blazegraph","virtuoso","neo4j","memgraph","falkordb"]
def require(condition, message):
    if not condition:
        raise ValueError(message)


NETWORK={"postgres","millenniumdb","blazegraph","virtuoso","neo4j","memgraph","falkordb"}


def execution_fingerprint():
    """Prevent --resume from mixing answers/timings from different executions."""
    files = list((ROOT / "Scripts/competitors").glob("*.py"))
    files += list((ROOT / "Scripts/competitors").glob("*.c"))
    files += list((ROOT / "Scripts/competitors").glob("*.java"))
    files += [sm.DATA / "csv/edges.csv", sm.DATA / "manifest.json",
              sm.DATA.parent / "pathrex/vertices.txt", sm.DATA.parent / "pathrex/edges.txt"]
    files += [ROOT / name for name in (
        "Databases/pathrex/target/release/pathrex",
        "Databases/rpq-matrix/build/baseline_query",
        "Databases/rpq-matrix_GB/build/baselineGB_query",
        "Results/competitors_250k/build/larpq-smoke",
        "Results/competitors_250k/build/millenniumdb/bin/mdb",
        "Results/competitors_250k/build/ring/query-index-basic",
    )]
    hashes = {}
    for path in files:
        digest = None
        if path.is_file():
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
        hashes[str(path.relative_to(ROOT))] = digest
    packages = {}
    for name in ("duckdb", "kuzu", "neo4j", "psycopg", "redis"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {"files_sha256": hashes, "python_packages": packages}


def validate_resume(prior, current):
    for key in ("runs", "warmups", "queries", "pathrex_optimizer", "dataset_edges", "dataset_vertices", "source_sha256", "runtime_lock", "execution_fingerprint", "host", "hostname", "cpu_count", "cpu_affinity", "omp_threads", "omp_env"):
        if prior.get(key) != current[key]:
            raise ValueError(f"Cannot resume: {key} differs from saved metadata")
    if not set(current["engines"]).issubset(prior["engines"]):
        raise ValueError("Cannot resume engines absent from saved metadata")


class Benchmark(sm.Smoke):
    def __init__(self,engine,args):
        self.engine=engine;self.args=args;self.folder=args.output
        self.result={"engine":engine,"started":time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                     "checks":[],"commands":[],"measurements":{},"runs":args.runs,"warmups":args.warmups,
                     "optimizer":"pang-hybrid" if engine=="pathrex" else None}
        self.container=None
        self.log=(self.folder/"logs"/f"{engine}.log").open("w")

    def query(self,q,execute):
        scope="client_roundtrip_execute_fetch" if self.engine in NETWORK else "embedded_execute_fetch"
        samples=[]
        for iteration in range(-self.args.warmups,self.args.runs):
            start=time.perf_counter_ns();values=execute();elapsed=(time.perf_counter_ns()-start)/1e6
            if sorted(set(values))!=q["targets"]:
                raise RuntimeError(f"Wrong endpoint set: {self.engine}/q{q['id']}/run{iteration}")
            if iteration>=0:samples.append(elapsed)
        self.add(q,samples,scope,"endpoint_set")
        return values

    def add(self,q,samples,scope,verification="count_only",extra=None):
        if len(samples)!=self.args.runs or any(not (0<x<float("inf")) for x in samples):
            raise RuntimeError(f"Invalid/incomplete timings: {self.engine}/q{q['id']}")
        self.result["measurements"][q["id"]]={"id":q["id"],"pattern":q["pattern"],
            "expected_count":q["count"],"samples_ms":samples,"scope":scope,"verification":verification,
            "status":"pass",**(extra or {})}
        print(f"  {self.engine} q{q['id']}: {len(samples)} measured runs",flush=True)

    def finish(self):
        if self.container:
            inspect=subprocess.run(["docker","inspect",self.container],capture_output=True,text=True)
            if inspect.returncode==0:self.result["container_state_before_stop"]=json.loads(inspect.stdout)[0]["State"]
            subprocess.run(["docker","logs",self.container],stdout=self.log,stderr=self.log)
            subprocess.run(["docker","stop","-t","5",self.container],stdout=self.log,stderr=self.log)
            subprocess.run(["docker","rm",self.container],stdout=self.log,stderr=self.log)
        self.result["executable_sha256"]={}
        for command in self.result["commands"]:
            binary=Path(command[0])
            if binary.is_file() and os.access(binary,os.X_OK):
                self.result["executable_sha256"][str(binary)]=hashlib.sha256(binary.read_bytes()).hexdigest()
        self.log.close()
        (self.folder/f"{self.engine}.json").write_text(json.dumps(self.result,indent=2)+"\n")
        print(self.engine,self.result.get("status"),self.result.get("error",""),flush=True)


def build_larpq(s):
    build=sm.OUT/"build"
    exe=s.folder/"build/larpq-bench"
    s.run(["gcc","-O3",ROOT/"Scripts/competitors/larpq_smoke.c","-o",exe,
           "-IDatabases/larpq/include","-Ivendor/GraphBLAS/Include",
           f"-L{build}/larpq/experimental",f"-L{build}/larpq/src","-Lvendor/GraphBLAS/build",
           f"-Wl,-rpath,{build}/larpq/experimental:{build}/larpq/src:{ROOT}/vendor/GraphBLAS/build",
           "-llagraphx","-llagraph","-lgraphblas","-fopenmp"])
    output=s.run([exe,sm.DATA/"matrix/graph.dat",sm.QUERY_DIR/"larpq.tsv",sm.MANIFEST["vertices"],
                  len(sm.MANIFEST["labels"]),"--bench",s.args.runs,s.args.warmups])
    parse_timing(s,output,"native_nfa_execute_materialize")
    for line in output.splitlines():
        if line.startswith("TIMING;"):continue
        qid,values=line.split(";",1)
        s.check(next(q for q in sm.QUERIES if q["id"]==qid),list(map(int,values.split(","))) if values else [])


def parse_timing(s,output,scope):
    samples=defaultdict(list)
    qs={q["id"]:q for q in sm.QUERIES}
    for line in output.splitlines():
        if not line.startswith("TIMING;"):continue
        _,qid,iteration,ms,count=line.split(";")
        require(int(iteration)==len(samples[qid]), f"Out-of-order timing: {line}")
        require(int(count)==qs[qid]["count"], f"Wrong result count: {line}")
        samples[qid].append(float(ms))
    for q in sm.QUERIES:s.add(q,samples[q["id"]],scope)


def matrices(s):
    gb=s.engine=="rpqmatrixGB"
    dat=sm.DATA/("matrix-gb/graph.dat" if gb else "matrix/graph.dat")
    if not gb and not Path(str(dat)+".baseline-64").exists():
        raise RuntimeError("Build dataset index with the smoke runner first")
    binary=ROOT/("Databases/rpq-matrix_GB/build/baselineGB_query" if gb else "Databases/rpq-matrix/build/baseline_query")
    output=s.run([binary,dat,sm.QUERY_DIR/"matrix.tsv",len(sm.MANIFEST["labels"]),sm.MANIFEST["edges"],s.args.runs,s.args.warmups])
    samples=defaultdict(list);qs={q["id"]:q for q in sm.QUERIES}
    for line in output.splitlines():
        parts=line.split(";")
        if len(parts)!=3 or parts[0] not in qs:continue
        qid,count,ns=parts
        require(int(count)==qs[qid]["count"], f"Wrong result count: {line}")
        samples[qid].append(int(ns)/1e6)
    for q in sm.QUERIES:
        times=samples[q["id"]];require(len(times)==s.args.warmups+s.args.runs, f"Incomplete matrix samples for {q['id']}")
        s.add(q,times[s.args.warmups:],"native_matrix_solver")


def pathrex(s):
    output=s.folder/"pathrex-native.json"
    s.run([ROOT/"Databases/pathrex/target/release/pathrex","bench","-g",sm.DATA.parent/"pathrex",
           "-q",sm.QUERY_DIR/"pathrex.txt","--base-iri","http://example.org/","-a","rpqmatrix",
           "-p","pang-hybrid","--runs",s.args.runs,"--warm-up-runs",s.args.warmups,"-o",output])
    native=json.loads(output.read_text());raw=json.loads(output.with_suffix(".runs.json").read_text())
    answers={q["query_id"]:q["algorithms"]["rpqmatrix"] for q in native["results"]}
    data={q["query_id"]:q["algorithms"]["rpqmatrix"] for q in raw["results"]}
    for q in sm.QUERIES:
        answer=answers[q["id"]];require(answer["status"]=="ok" and answer["result_count"]==q["count"], f"Wrong Pathrex answer: {answer}")
        samples=data[q["id"]]
        s.add(q,[x/1e6 for x in samples["total_ns"]],"native_evaluator_prepare_execute",
              extra={"ffi_only_samples_ms":[x/1e6 for x in samples["ffi_only_ns"]],
                     "ffi_note":f"Native CLI separately runs {s.args.runs} ffi-only iterations; auxiliary, not main chart"})


def ring(s):
    # Isolated instrumented copy: upstream source remains unchanged. Its old
    # timer truncates to integer microseconds then applies an incorrect scale.
    source=(ROOT/"Databases/ring-rpq/src/query-index-basic.cpp").read_text()
    source=source.replace('#include <iostream>','#include <iostream>\n#include <iomanip>')
    original='cout << q << ";" << query_output.size() << ";" << (uint64_t) (total_time * 1000000000ULL) << endl;'
    require(source.count(original)==1, "Pinned Ring timer source no longer matches")
    source=source.replace(original,'cout << q << ";" << query_output.size() << ";" << std::setprecision(12) << std::chrono::duration<double, std::milli>(stop-start).count() << endl;')
    cpp=s.folder/"build/ring-bench.cpp";cpp.write_text(source)
    sdsl=sm.OUT/"tools/sdsl-install";binary=s.folder/"build/ring-bench"
    s.run(["g++","-O3","-DNDEBUG","-std=c++11","-fpermissive","-msse4.2",cpp,"-o",binary,
           f"-I{ROOT}/Databases/ring-rpq/src",f"-I{ROOT}/Databases/ring-rpq/nfa/include",f"-I{sdsl}/include",
           f"-L{sdsl}/lib","-lsdsl","-ldivsufsort","-ldivsufsort64",sm.OUT/"build/ring/nfa/libnfa.a"])
    s.result["build_note"]="Standalone -O3 driver; existing pinned SDSL and nfa static library reused"
    lines=(sm.QUERY_DIR/"ring.tsv").read_text().splitlines()
    repeated=s.folder/"ring-repeated.tsv"
    repeated.write_text("\n".join(line for line in lines for _ in range(s.args.runs+s.args.warmups)))
    output=s.run([binary,sm.DATA/"matrix/graph.dat",repeated])
    values=[]
    for line in output.splitlines():
        parts=line.split(";")
        if len(parts)==3 and parts[0].isdigit():values.append(parts)
    block=s.args.runs+s.args.warmups;require(len(values)==len(sm.QUERIES)*block, "Incomplete Ring samples")
    for index,q in enumerate(sm.QUERIES):
        rows=values[index*block:(index+1)*block]
        require(all(int(row[1])==q["count"] for row in rows), f"Wrong Ring result count for {q['id']}")
        s.add(q,[float(row[2]) for row in rows[s.args.warmups:]],"native_ring_query")


def jena(s):
    folder=s.folder.relative_to(ROOT);docker_folder=Path("/work")/folder
    inputs=s.folder/"jena-queries.tsv"
    inputs.write_text("".join(q["id"]+"\t"+",".join(map(str,q["targets"]))+"\t"+q["sparql"].replace("\n"," ")+"\n" for q in sm.QUERIES))
    classes=docker_folder/"build"
    sm.java_command(s,["javac","-proc:none","-cp","/tools/apache-jena-6.2.0/lib/*","-d",classes,
                       "/work/Scripts/competitors/JenaBench.java"])
    output=sm.java_command(s,["java","-Xmx768m","-cp",f"/tools/apache-jena-6.2.0/lib/*:{classes}",
        "JenaBench","/input/rdf/graph.nt",docker_folder/"jena-tdb",docker_folder/inputs.name,
        "/work/Datasets/rpqbench_250k/pathrex/vertices.txt",s.args.runs,s.args.warmups],timeout=180)
    parse_timing(s,output,"in_jvm_tdb_parse_execute_fetch")
    for value in s.result["measurements"].values():value["verification"]="endpoint_set_every_run"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"Results/competitors_bench_250k"/time.strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--runs",type=int,default=100)
    parser.add_argument("--warmups",type=int,default=10)
    parser.add_argument("--engines",nargs="+",choices=ENGINES,default=ENGINES)
    parser.add_argument("--resume",action="store_true")
    args=parser.parse_args();args.output=args.output.resolve()
    if args.runs<1 or args.warmups<0:parser.error("Invalid run count")
    try:
        args.output.relative_to(ROOT)
    except ValueError:
        parser.error("Output must be inside the repository for Docker bind mounts")
    if (args.output/"metadata.json").exists() and not args.resume:parser.error("Output exists; use a new directory or --resume")
    for name in ["logs","build"]:(args.output/name).mkdir(parents=True,exist_ok=True)
    try:
        sm.load_inputs()
    except ValueError as error:
        parser.error(str(error))
    sm.QUERIES=prepare();sm.QUERY_DIR=sm.DATA/"basic"
    lock=ROOT/"Databases/guides/runtime-lock.json"
    metadata={"date":datetime.now(timezone.utc).isoformat(),"runs":args.runs,"warmups":args.warmups,"queries":sm.QUERIES,
              "engines":args.engines,"pathrex_optimizer":"pang-hybrid","dataset_edges":sm.MANIFEST["edges"],
              "dataset_vertices":sm.MANIFEST["vertices"],"source_sha256":sm.MANIFEST["source_sha256"],
              "host":platform.platform(),"cpu_count":os.cpu_count(),"omp_threads":2,
              "hostname":platform.node(),
              "cpu_affinity":sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
              "omp_env":{key:os.environ.get(key) for key in ("OMP_PROC_BIND", "OMP_PLACES", "OMP_DYNAMIC")},
              "memory_note":"Docker 2GiB/2 CPU quota; embedded/native host process; see per-engine boundaries",
              "threads_note":"omp_threads is requested OMP_NUM_THREADS, not a measured GraphBLAS limit; ThreadScope may reset it",
              "runtime_lock":json.loads(lock.read_text()),"process_order":f"sequential engine blocks; {args.warmups} warmups per query",
              "execution_fingerprint":execution_fingerprint(),
              "timing_note":"Import/startup/graph load/index excluded. Native, JVM, embedded and network scopes differ.",
              "pathrex_note":f"{args.runs} total runs used; native CLI also collects {args.runs} separate ffi-only diagnostic runs"}
    if args.resume:
        prior=json.loads((args.output/"metadata.json").read_text())
        try:
            validate_resume(prior, metadata)
        except ValueError as error:
            parser.error(str(error))
    else:(args.output/"metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")
    functions={"larpq":build_larpq,"rpqmatrix":matrices,"rpqmatrixGB":matrices,"pathrex":pathrex,"ring":ring,"jena":jena}
    failures=[]
    for engine in args.engines:
        previous=args.output/f"{engine}.json"
        if args.resume and previous.exists() and json.loads(previous.read_text()).get("status")=="completed":
            print(engine,"already completed",flush=True);continue
        print("Starting",engine,flush=True);s=Benchmark(engine,args)
        try:
            fn=functions.get(engine) or ({"neo4j":sm.bolt,"memgraph":sm.bolt}.get(engine)) or getattr(sm,engine)
            fn(s)
            require(set(s.result["measurements"])=={q["id"] for q in sm.QUERIES}, f"Incomplete measurements: {s.result['checks']}")
            require(all(c["status"]=="pass" for c in s.result["checks"]), f"Failed checks: {s.result['checks']}")
            s.result["status"]="completed"
        except Exception as error:
            s.result.update(status="failed",error=str(error));failures.append(engine)
        finally:s.finish()
    if failures:raise SystemExit("Failed engines: "+", ".join(failures))
    print("Measurements saved:",args.output,flush=True)


if __name__=="__main__":main()
