from pathlib import Path
from ..config import ROOT
from ..runtime import require
def run(s):
    # Isolated instrumented copy: upstream source remains unchanged. Its old
    # timer truncates to integer microseconds then applies an incorrect scale.
    source=(ROOT/"Databases/ring-rpq/src/query-index-basic.cpp").read_text()
    source=source.replace('#include <iostream>','#include <iostream>\n#include <iomanip>')
    original='cout << q << ";" << query_output.size() << ";" << (uint64_t) (total_time * 1000000000ULL) << endl;'
    require(source.count(original)==1, "Pinned Ring timer source no longer matches")
    source=source.replace(original,'cout << q << ";" << query_output.size() << ";" << std::setprecision(12) << std::chrono::duration<double, std::milli>(stop-start).count() << endl;')
    cpp=s.folder/"build/ring-bench.cpp";cpp.write_text(source)
    sdsl=s.runtime/"tools/sdsl-install";binary=s.folder/"build/ring-bench"
    s.run(["g++","-O3","-DNDEBUG","-std=c++11","-fpermissive","-msse4.2",cpp,"-o",binary,
           f"-I{ROOT}/Databases/ring-rpq/src",f"-I{ROOT}/Databases/ring-rpq/nfa/include",f"-I{sdsl}/include",
           f"-L{sdsl}/lib","-lsdsl","-ldivsufsort","-ldivsufsort64",s.runtime/"build/ring/nfa/libnfa.a"])
    s.result["build_note"]="Standalone -O3 driver; existing pinned SDSL and nfa static library reused"
    lines=(s.query_dir/"ring.tsv").read_text().splitlines()
    repeated=s.folder/"ring-repeated.tsv"
    repeated.write_text("\n".join(line for line in lines for _ in range(s.args.runs+s.args.warmups)))
    dataset = s.data / "matrix/graph.dat"
    if not Path(str(dataset) + ".nTriples").is_file():
        s.run([s.runtime / "build/ring/build-index-basic", dataset])
    output = s.run([binary, dataset, repeated])
    values=[]
    for line in output.splitlines():
        parts=line.split(";")
        if len(parts)==3 and parts[0].isdigit():values.append(parts)
    block=s.args.runs+s.args.warmups;require(len(values)==len(s.queries)*block, "Incomplete Ring samples")
    require([int(row[0]) for row in values] == list(range(1, len(values) + 1)),
            "Ring did not return one row in order for each submitted query")
    for index,q in enumerate(s.queries):
        rows=values[index*block:(index+1)*block]
        require(all(int(row[1])==q["count"] for row in rows), f"Wrong Ring result count for {q['id']}")
        s.add(q,[float(row[2]) for row in rows[s.args.warmups:]],"native_ring_query")


if __name__ == "__main__":
    from ..workflow import main

    main(default_engine='ring')
