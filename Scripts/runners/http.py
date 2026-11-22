import json
import urllib.parse
import urllib.request

def sparql_http(url, query, **parameters):
    request = urllib.request.Request(url, data=urllib.parse.urlencode({"query": query, **parameters}).encode(),
                                    headers={"Accept":"application/sparql-results+json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def iri_ids(s):
    result = {}
    for line in (s.graph / "vertices.txt").read_text().splitlines():
        label, number = line.rsplit(maxsplit=1)
        label = label.strip("<>")
        iri = label if "://" in label else s.manifest["base_iri"] + label
        result[iri] = int(number)
    return result


def target_ids(result, ids):
    return [ids[row["t"]["value"]] for row in result["results"]["bindings"]]
