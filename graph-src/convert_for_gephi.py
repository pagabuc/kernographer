import sys
import os

sys.path.append(os.path.abspath("../src/"))
sys.path.append(os.path.abspath("../graphs/"))
sys.path.append(os.path.abspath("../tests/"))
from mytypes import Sample, Struct, Field
from graph_tool.all import *
from graph_utils import *
from heuristics import *

def visit_heuristics(G):
    heuristics = [pidhashtable, arp, tty_check, iomem, proc_maps_rb, proc_maps, mount, check_modules, lsof, lsmod, ifconfig,
                  pslist, threads, check_creds, check_afinfo, check_fops, find_file]

    edges = set()
    for e in heuristics:
        path = e(G)
        edges.update(path)

    return set(edges)

def label_struct(s):
    return '%s %s' % (hex(s.addr), s.ty)

def get_subsystem_from_filename(f):
    if f.startswith("net/") or any(i in f for i in ["include/net/", "linux/net.h", "linux/netfilter"]):
        return "net"

    if f.startswith("drivers") or any(i in f for i in ["device.h", "pci.h", "mod_devicetable.h", "include/acpi"]):
        return "devices"

    if f.startswith("fs/") or any(i in f for i in ["dcache.h", "linux/fs.h", "sysfs.h", "sysctl.h", "kernfs.h", "kernfs-internal.h", "fs_struct.h"]):
        return "fs"

    if any(i in f for i in ["sound/"]):
        return "sound"

    if any(i in f for i in ["arch/x86"]):
        return "arch"

    if "trace" in f:
        return "trace"

    if any(i in f for i in ["security/", "lsm_hooks.h"]):
        return "security"

    if any(i in f for i in ["mm_types.h", "mm.h", "vmalloc.h", "mm/", "rmap.h"]):
        return "memory"

    if any(i in f for i in ["linux/sched.h", "sched/sched.h", "cred.h", "cgroup", "pid.h"]):
        return "proc"

    if any(i in f for i in ["linux/export.h"]):
        return "export"

    if any(i in f for i in ["linux/types.h", "list_bl", "klist.h", "rbtree.h", "list_lru.h"]):
        return "types"

    return "other"


def assign_subsystem_graph(sample, G):
    label_to_vertex = {}
    for v in G.vertices():
        label = G.vp.label[v]
        label_to_vertex[label] = v

    for s in sample:
        label = label_struct(s)
        if label in label_to_vertex:
            v = label_to_vertex[label]
            G.vp.subsystem[v] = get_subsystem_from_filename(s.filename)


def main():
    if(len(sys.argv) != 3):
        print('Usage: python %s ./path/to/experiment ./path/to/graph' % sys.argv[0])
        sys.exit(-1)

    sample = Sample.load(sys.argv[1])
    G = my_load_graph(sys.argv[2])

    G.vp["subsystem"] = G.new_vertex_property("string")
    G.vp["heuristic"] = G.new_vertex_property("bool")
    G.ep["heuristic"] = G.new_edge_property("bool")

    assign_subsystem_graph(sample, G)
    vol_edges = visit_heuristics(G)

    vol_edges = [e for e in vol_edges if e is not None]
    print("Edges visited by volatility: %d" % len(vol_edges))

    for e in vol_edges:
        G.ep.heuristic[e] = 1

    for v in get_nodes_path(vol_edges):
        G.vp.heuristic[v] = 1

    del G.vp.properties[('e','offset_weight')]
    del G.vp.properties[('e','atomicity_weight')]
    del G.vp.properties[('v','physical_addr')]

    out_file = "/tmp/sample.graphml"
    print("[+] Saving graph in %s" % out_file)
    G.save(out_file, fmt='graphml')

    # for v in G.vertices():
    #     print("%s -> %s %s" % (G.vp.label[v], G.vp.subsystem[v], G.vp.heuristic[v]))

if __name__ == "__main__":
    main()
