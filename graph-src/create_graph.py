import sys
import os
from os.path import normpath
import logging
import argparse

sys.path.append(os.path.abspath("../src/"))
sys.path.append(os.path.abspath("../graphs/"))
from mytypes import Sample, Struct, Field
from weight_functions import Weights
from graph_tool.all import *
from ram import *
from graph_utils import *

NR_CPUS = 4
KERNEL_COUNT = 85

def label_struct(s):
    return '%s %s' % (hex(s.addr), s.ty)

def create_edge(G, W, RAM, struct, pte_struct, field_name):
    fr_label = label_struct(get_outer_struct(RAM, struct.addr))
    to_label = label_struct(get_outer_struct(RAM, pte_struct.addr))
    fr = label_to_vertex[fr_label]
    to = label_to_vertex[to_label]

    e = G.add_edge(fr, to)
    label = get_inner_struct_label(W, RAM, struct)
    G.ep.label[e] = label + field_name

    if W is None:
        return

    aw = W.atomicity_weight(struct.addr, pte_struct.addr)
    hw = W.heatmap_weight(label_struct(struct), field_name)

    if struct.is_global_container():
        ptr_ow = [list(range(KERNEL_COUNT))]
    else:
        ptr_ow = get_inner_struct_ow(W, RAM, struct, field_name)

    if pte_struct.is_global_container():
        pte_ow = [list(range(KERNEL_COUNT))]
    else:
        pte_ow = get_inner_struct_ow(W, RAM, pte_struct)

    ow = intersect_ow(ptr_ow, pte_ow)

    G.ep.atomicity_weight[e] = aw
    G.ep.heatmap_weight[e] = hw
    G.ep.offset_weight[e] = ow

def create_custom_edge(G, W, RAM, fr_label, to_label, fr_addr, to_addr, field_name, edge_label, heatmap_fr, ow):
    fr = label_to_vertex[fr_label]
    to = label_to_vertex[to_label]
    e = G.add_edge(fr, to)
    G.ep.label[e] = edge_label

    if W is None:
        return

    aw = W.atomicity_weight(fr_addr, to_addr)
    hw = W.heatmap_weight(heatmap_fr, field_name)

    G.ep.atomicity_weight[e] = aw
    G.ep.heatmap_weight[e] = hw
    G.ep.offset_weight[e] = ow

# Used to quickly locate a vertex given a label (graph_tool is O(V))
label_to_vertex = {}

def create_edges(G, W, RAM, addr, already_processed):
    structs = RAM[addr]
    for struct in structs:
        if struct in already_processed:
            continue

        for field in struct:
            if field.might_infer_ptr() or (field.is_void_ptr() and field.is_deref()):
                t = get_outer_struct(RAM, field.value)
                if t:
                    create_edge(G, W, RAM, struct, t, field.name)

            elif field.is_ptr_array_of_ptr() and field.is_deref(): # percpu, struct fdtable.fd
                fr_label = label_struct(structs[0])
                fr_addr = structs[0].addr
                to_label = '%s_%s_array_of_ptr' % (hex(struct.addr), hex(field.value))
                to_addr = field.value
                edge_label = get_inner_struct_label(W, RAM, struct) + field.name
                heatmap_fr = label_struct(struct)
                ow = get_inner_struct_ow(W, RAM, struct, field.name)
                create_custom_edge(G, W, RAM, fr_label, to_label, fr_addr, to_addr,
                                   field.name, edge_label, heatmap_fr, ow)

                fr_label = heatmap_fr = to_label
                for name, to_addr in field.get_array_elements():
                    t = get_struct(RAM, to_addr, field.pte_type)
                    if t:
                        fr_addr = field.value
                        to_label = label_struct(get_outer_struct(RAM, to_addr))
                        ow = get_inner_struct_ow(W, RAM, t)
                        field_name = edge_label = name
                        create_custom_edge(G, W, RAM, fr_label, to_label, fr_addr, to_addr,
                                           field_name, edge_label, heatmap_fr, ow)

            elif field.is_array_of_struct_ptr():
                for name, addr in field.get_array_elements():
                    t = get_struct(RAM, addr, field.pte_type)
                    if t:
                        create_edge(G, W, RAM, struct, t, name)

            elif field.is_struct_ptr() and field.is_deref():
                t = get_struct(RAM, field.value, field.pte_type)
                if t:
                    create_edge(G, W, RAM, struct, t, field.name)

def create_vertex(G, label, paddr):
    v = G.add_vertex()
    G.vp.label[v] = label
    if paddr is not None:
        G.vp.physical_addr[v] = paddr
    label_to_vertex[label] = v

def create_graph(sample, RAM, W):
    print("[+] Creating graph...")
    G = Graph()

    # Vertex properties
    G.vp["global_root"] = G.new_vertex_property("bool")
    G.vp["label"] = G.new_vertex_property("string")
    G.vp["name"] = G.new_vertex_property("string")
    G.vp["physical_addr"] = G.new_vertex_property("unsigned long")

    # Edge properties
    G.ep["atomicity_weight"] = G.new_edge_property("unsigned long")
    G.ep["heatmap_weight"] = G.new_edge_property("unsigned long")
    G.ep["offset_weight"] = G.new_edge_property("object")
    G.ep["label"] = G.new_edge_property("string")

    print("[+] Adding vertices..")
    for s in get_all_outer_structs(RAM):
        label = label_struct(s)
        paddr = W.translate(s.addr) if W is not None else None
        create_vertex(G, label, paddr)

    for s in sample:
        for f in s:
            if not f.is_ptr_array_of_ptr():
                continue
            label = "%s_%s_array_of_ptr" % (hex(s.addr), hex(f.value))
            if label not in label_to_vertex:
                paddr = W.translate(f.value) if W is not None else None
                create_vertex(G, label, paddr)

    print("[+] Adding edges..")
    already_processed = set()
    for addr in RAM:
        structs = RAM[addr]
        create_edges(G, W, RAM, addr, already_processed)
        already_processed.update(structs)

    print("Setting global_roots..")
    for s in sample:
        if s.is_global():
            try:
                v = label_to_vertex[label_struct(s)]
            except KeyError:
                # logging.debug("ARGH: %s" % s)
                continue

            if v.out_degree() > 0:
                G.vp.global_root[v] = True
                G.vp.name[v] = s.name
            else:
                G.vp.global_root[v] = False

    return G

def main(sample_path, no_weights):

    sample_name = normpath(sample_path).split(os.sep)[-1]

    log_file = "../logs/%s.graph" % (sample_name)
    print("[+] Logging in %s" % log_file)
    logging.basicConfig(format='%(levelname)s : %(message)s',
                        stream=open(log_file, "w"),
                        level=logging.DEBUG)

    if no_weights:
        W = None
    else:
        W = Weights(sample_name)

    print("[+] Reading sample from %s" % sample_path)
    sample = Sample.load(sample_path)
    RAM, sample = load_ram(sample)

    G = create_graph(sample, RAM, W)

    out_file = os.path.join("../graphs/", sample_name)
    print("[+] Saving graph in %s" % out_file)
    G.save(out_file, fmt='gt')

    start = time.time()
    print("[+] %s" % G)
    for e in G.edges():
        s = e.source()
        t = e.target()
        aw = G.ep.atomicity_weight[e]
        ow = G.ep.offset_weight[e]
        hw = G.ep.heatmap_weight[e]
        source = "%s%s" % (G.vp.label[s], "." + G.vp.name[s] if G.vp.name[s] else "")
        target = "%s%s" % (G.vp.label[t], "." + G.vp.name[t] if G.vp.name[t] else "")
        logging.debug("%s --%s--> %s (aw: %d ow: %s hw: %d)" % (source, G.ep.label[e], target, aw, ow, hw))
    end = time.time()
    print("Printing graph took %d seconds"  % (end - start))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-weights', action='store_true', help="shows output")
    parser.add_argument("sample")

    args = parser.parse_args()

    print(args.no_weights)
    print(args.sample)

    main(args.sample, args.no_weights)
