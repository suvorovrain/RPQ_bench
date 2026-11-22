import java.nio.file.*;
import java.util.*;
import org.apache.jena.query.*;
import org.apache.jena.riot.RDFDataMgr;
import org.apache.jena.tdb2.TDB2Factory;
import org.apache.jena.system.Txn;

/** One JVM and one TDB2 dataset for every warmup and measured execution. */
public class JenaBench {
    public static void main(String[] args) throws Exception {
        int runs=Integer.parseInt(args[4]), warmups=Integer.parseInt(args[5]);
        Dataset dataset=TDB2Factory.connectDataset(args[1]);
        try {
            Txn.executeWrite(dataset, () -> RDFDataMgr.read(dataset.getDefaultModel(), args[0]));
            Map<String,Integer> ids=new HashMap<>();
            for(String line:Files.readAllLines(Path.of(args[3]))) {
                int split=line.lastIndexOf(' ');
                String label = line.substring(0, split).replace("<", "").replace(">", "");
                ids.put(label.contains("://") ? label : args[6] + label,
                        Integer.valueOf(line.substring(split+1)));
            }
            for(String line:Files.readAllLines(Path.of(args[2]))) {
                String[] parts=line.split("\t",3);
                Set<Integer> expected=new TreeSet<>();
                for(String id:parts[1].split(",")) if(!id.isEmpty()) expected.add(Integer.valueOf(id));
                for(int iteration=-warmups;iteration<runs;iteration++) {
                    long begin=System.nanoTime();
                    Query query=QueryFactory.create(parts[2]);
                    long parsed=System.nanoTime();
                    List<String> endpoints=Txn.calculateRead(dataset, () -> {
                        List<String> values=new ArrayList<>();
                        try(QueryExecution execution=QueryExecutionFactory.create(query,dataset)) {
                            ResultSet result=execution.execSelect();
                            while(result.hasNext()) values.add(result.next().getResource("t").getURI());
                        }
                        return values;
                    });
                    long finished=System.nanoTime();
                    Set<Integer> actual=new HashSet<>();
                    for(String endpoint:endpoints) actual.add(ids.get(endpoint));
                    if(!actual.equals(expected)) throw new IllegalStateException("Wrong endpoints for "+parts[0]);
                    if(iteration>=0) System.out.printf(Locale.ROOT,"JENA;%s;%d;%.9f;%.9f;%d%n",
                            parts[0],iteration,(parsed-begin)/1e6,(finished-parsed)/1e6,actual.size());
                }
            }
        } finally { dataset.close(); }
    }
}
