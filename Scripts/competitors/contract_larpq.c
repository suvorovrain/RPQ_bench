/* Semantic probe of pinned LAGraph 2-rpq; synthetic graph, no timings.
 * IDs: A=0 B=1 C=2 D=3 E=4 F=5 G=6; labels p=0 q=1 z=2.
 * Source masks are fixture-only; output vertex IDs are zero-based.
 */
#include <stdio.h>
#include <stdlib.h>
#include "LAGraph.h"
#include "LAGraphX.h"
static char msg[LAGRAPH_MSG_LEN];
#define CHECK(x) do { int rc=(x); if(rc) { fprintf(stderr,"%s: %d %s\n",#x,rc,msg); exit(1); } } while(0)
typedef struct { int from, label, to; } Edge;
static Edge edges[]={{0,0,1},{0,0,2},{1,0,3},{2,0,3},{1,1,0},{2,1,0},{4,2,4},{5,0,6},{6,1,5}};
static LAGraph_Graph make_graph(int n, Edge *es, int count, int label) {
    GrB_Matrix a=NULL;
    LAGraph_Graph g=NULL;
    CHECK(GrB_Matrix_new(&a,GrB_BOOL,n,n));
    CHECK(GxB_Matrix_Option_set(a,GxB_FORMAT,GxB_BY_ROW));
    for(int i=0;i<count;i++) if(es[i].label==label)
        CHECK(GrB_Matrix_setElement_BOOL(a,true,es[i].from,es[i].to));
    CHECK(LAGraph_New(&g,&a,LAGraph_ADJACENCY_DIRECTED,msg));
    CHECK(LAGraph_Cached_AT(g,msg));
    CHECK(GxB_Matrix_Option_set(g->AT,GxB_FORMAT,GxB_BY_ROW));
    return g;
}
static void probe(const char *id,LAGraph_Graph *G,int states,Edge *trans,int nt,
                  unsigned sm,unsigned qm,unsigned fm,bool label_inverse,bool whole_inverse) {
    LAGraph_Graph R[3];
    for(int i=0;i<3;i++) R[i]=make_graph(states,trans,nt,i);
    bool il[3]={label_inverse,false,false};
    GrB_Index S[7],QS[4],QF[4]; size_t ns=0,nqs=0,nqf=0;
    for(int i=0;i<7;i++) if(sm&(1u<<i)) S[ns++]=i;
    for(int i=0;i<states;i++) {
        if(qm&(1u<<i)) QS[nqs++]=i;
        if(fm&(1u<<i)) QF[nqf++]=i;
    }
    GrB_Vector result=NULL;
    CHECK(LAGraph_2RegularPathQuery(&result,R,il,3,QS,nqs,QF,nqf,G,S,ns,whole_inverse,msg));
    printf("%s;",id); int first=1;
    for(GrB_Index i=0;i<7;i++) {
        bool value=false; int rc=GrB_Vector_extractElement_BOOL(&value,result,i);
        if(rc!=GrB_NO_VALUE && rc!=GrB_SUCCESS) CHECK(rc);
        if(value) { printf("%s%llu",first?"":",",(unsigned long long)i); first=0; }
    }
    printf("\n"); CHECK(GrB_Vector_free(&result));
    for(int i=0;i<3;i++) CHECK(LAGraph_Delete(&R[i],msg));
}
int main(void) {
    CHECK(LAGraph_Init(msg)); CHECK(LAGraph_SetNumThreads(1,2,msg));
    LAGraph_Graph G[3]; for(int i=0;i<3;i++) G[i]=make_graph(7,edges,9,i);
    Edge p[]={{0,0,1}},pp[]={{0,0,1},{1,0,2}},pqp[]={{0,0,1},{1,1,2},{2,0,3}},star[]={{0,0,0}};
    probe("con_any_p",G,2,p,1,1,1,2,false,false);
    probe("diamond_pp",G,3,pp,2,1,1,4,false,false);
    probe("repeated_edge_pqp",G,4,pqp,3,1u<<5,1,8,false,false);
    probe("zero_length_E",G,1,star,1,1u<<4,1,1,false,false);
    probe("multi_source_p",G,2,p,1,(1u<<1)|(1u<<2),1,2,false,false);
    probe("all_sources_p",G,2,p,1,127,1,2,false,false);
    probe("inverse_label_from_D",G,2,p,1,1u<<3,1,2,true,false);
    /* Whole-query inverse reverses both traversals; caller swaps QS/QF. */
    probe("whole_inverse_from_D",G,2,p,1,1u<<3,2,1,false,true);
    probe("whole_inverse_without_state_swap",G,2,p,1,1u<<3,1,2,false,true);
    for(int i=0;i<3;i++) CHECK(LAGraph_Delete(&G[i],msg));
    CHECK(LAGraph_Finalize(msg)); return 0;
}
