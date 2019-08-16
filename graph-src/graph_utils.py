from multiprocessing import Pool, Queue
from graph_tool.all import *
from itertools import repeat, product
import time

def get_string_metrics_path(G, p):
    aw = calculate_aw(G, p)
    ctg = calculate_ctg(G, p)
    mtg = calculate_mtg(G, p)
    mct = calculate_mct(G, p)
    kc = calculate_kc(G, p)
    correct,_ = is_path_correct(G, p)
    return "%d %s aw: %.8f ctg: %.8f mtg: %.8f mct: %.8f kc: %d correct: %s" % (len(p), stringify_path(G, p),
                                                                                aw, ctg, mtg, mct, kc, correct)
def get_type_from_vertex(G, v):
    if "_array_of_ptr" in G.vp.label[v]:
        return "_array_of_ptr"

    label = G.vp.label[v]
    if G.vp.global_root[v]:
        label += '.%s' % G.vp.name[v]

    return ' '.join(label.split(" ")[1:])

def label_edge(G, e):
    label = G.ep.label[e]
    if "[" in label:
        a = label.index("[")
        b = label.index("]")
        label = label[:a] + label[b+1:]
    return label

def get_aw_in_seconds(G, e):
    return (G.ep.atomicity_weight[e] - 1) * ratio

def template(G, p):
    temp = dict()
    for e in p:
        s, d = e
        el = label_edge(G, e)
        ts = get_type_from_vertex(G, s)
        td = get_type_from_vertex(G, d)
        aws = get_aw_in_seconds(G, e)
        hw = G.ep.heatmap_weight[e]
        if hw == 700.0:
            continue
        try:
            temp[(ts, el, td)].append((aws, hw))
        except KeyError:
            temp[(ts, el, td)] = [(aws, hw)]

    # averaging
    for k,v in temp.items():
        timings = [t[0] for t in v]
        heatmaps = [t[1] for t in v]

        avg_timings = sum(timings)/len(timings)
        avg_heatmaps = sum(heatmaps)/len(heatmaps)

        temp[k] = (avg_timings, avg_heatmaps)

    for k,v in temp.items():
        print(k,v)

def count_edges_path(G, vlist):
    count = 1
    for v1,v2 in zip(vlist, vlist[1:]):
        edges = G.edge(v1, v2, all_edges=True)
        count *= len(edges)
        # print([G.ep.label[e] for e in edges])
    return count

def vlist_to_elist(G, vlist, curr = None):
    if curr == None:
        curr = []

    for v1,v2 in zip(vlist, vlist[1:]):
        edges = G.edge(v1, v2, all_edges=True)
        if len(edges) == 1:
            curr.append(edges[0])
        else:
            for e in edges:
                i = vlist.index(v2)
                for a in vlist_to_elist(G, vlist[i:], curr+[e]):
                    yield a
            return
    yield curr

def find_paths(G, source, target, weight_name):
    print("[%s] Entering: %s -> %s" % (weight_name, source, target), flush=True)
    start = time.time()
    fr = G.vertex(source)
    to = G.vertex(target)
    c = 0
    if weight_name == "no_weight":
        weights = None
    else:
        weights = G.edge_properties[weight_name]
    for p in graph_tool.topology.all_shortest_paths(G, fr, to, weights=weights):
        QUEUE.put((source, target, [int(i) for i in p]))
        c+=1
    end = time.time()
    print("[%s] Result %s -> %s found: %d took: %.2f s" % (weight_name, fr, to, c, end - start), flush=True)
    return

QUEUE = None
def find_shortest_paths(G, source, target, weight_name):
    global QUEUE
    QUEUE= Queue()
    nproc=2
    try:
        target = [int(i) for i in target]
    except TypeError:
        target = repeat(int(target))

    try:
        source = [int(i) for i in source]
    except TypeError:
        source = repeat(int(source))

    # print("Starting a pool with %d processes" % nproc, flush=True)
    pool = Pool(processes=nproc)
    both = isinstance(source,list) and isinstance(target,list)
    if not both:
        pool.starmap(find_paths, zip(repeat(G), source, target, repeat(weight_name)))
    else:
        print(len(source), len(target))
        for s in source:
            print("starmapping %d" % s)
            pool.starmap(find_paths, zip(repeat(G), repeat(s), target, repeat(weight_name)))
    print("[+] Closing pool..")
    pool.close()

    results = []
    while QUEUE.qsize() != 0:
        results.append(QUEUE.get())
    return results


def __explore_list(G, elem, field_next, root_vertex):
    while True:
        edge_elem, elem = follow_field(G, elem, field_next)
        if not edge_elem or elem == root_vertex:
            break
        yield edge_elem, elem

def explore_list(G, root, first_field_next, field_next):
    edge_elem, elem = follow_field(G, root, first_field_next)
    if not elem:
        return
    yield edge_elem, elem
    for edge_elem, elem in __explore_list(G, elem, field_next, root):
        yield edge_elem, elem

def explore_list_global_variable(G, gv_name, first_field_next, field_next):
    gv = graph_tool.util.find_vertex(G, G.vp.name, gv_name)[0]
    return explore_list(G, gv, first_field_next, field_next)

def get_nodes_path(p):
    s = set()
    for e in p:
        a,b = e
        s.add(a)
        s.add(b)
    return s

def get_out_targets(v):
    for e in v.out_edges():
        yield e, e.target()

def get_out_edges_name(G, v):
    for e in v.out_edges():
        yield G.ep.label[e]

def dump_out_edges(G, v):
    for e in v.out_edges():
        print("  %s->%s" % (G.ep.label[e], G.vp.label[e.target()]))

def same_edge(G, e1, e2):
    return ((e1.target() == e2.target()) and (e1.source() == e2.source()) and
            (G.ep.atomicity_weight[e1] == G.ep.atomicity_weight[e2]) and
            (G.ep.offset_weight[e1] == G.ep.offset_weight[e2]) and
            (G.ep.heatmap_weight[e1] == G.ep.heatmap_weight[e2]))

def remove_duplicate_edges(G):
    to_remove_edges = set()
    for v in G.vertices():
        edges = list(v.out_edges())
        uniq = set()
        for j in range(0,len(edges)):
            e1 = edges[j]
            for e2 in uniq:
                if same_edge(G, e1, e2):
                    break
            else:
                uniq.add(e1)
                continue

        to_remove_edges.update(set(edges)-uniq)

    print("[+] FILTERING DUPLICATE EDGES :%d" % len(to_remove_edges))
    efilt = G.new_edge_property("bool", vals=True)

    for e in to_remove_edges:
        efilt[e] = False
    return GraphView(G, efilt=efilt)

def follow_field(G, s, name):
    if not s:
        return None, None
    for e in s.out_edges():
        if G.ep.label[e] == name:
            return e, e.target()
    return None, None

def delete_path(G, path):
    for e in path:
        G.remove_edge(e)

def label_vertex(G, v):
    return '%s' % G.vp.label[v] + ('.%s' % G.vp.name[v] if G.vp.global_root[v] else '')

def stringify_path(G, path, weight_name="no_weight"):
    return convert_path(G, path, weight_name)[0]

def visualize_path(G, path):
    efilt = G.new_edge_property('bool')
    vfilt = G.new_vertex_property('bool')
    for e in path:
        efilt[e] = True
    for p in get_nodes_path(path):
        vfilt[p] = True

    gv = GraphView(G, efilt=efilt, vfilt=vfilt)
    v_size = gv.new_vertex_property('int')
    for p in get_nodes_path(path):
        v_size[p] = 6

    root = path[0].source()
    v_size[root] = 8
    gv.vp.label[root] += '.%s' % gv.vp.name[root]

    pos = graph_tool.draw.arf_layout(gv, max_iter=2000, d=0.9)
    vprops = {'text' : gv.vp.label, 'text_position': "centered", 'font_size':v_size, 'size': 4}
    eprops = {'text' : gv.ep.label, 'font_size':4, 'text_distance': 3}
    graph_tool.draw.graph_draw(gv, vprops=vprops, eprops=eprops, pos=pos, output="/tmp/a.pdf")

def convert_path(G, path, weight_name):
    spath = ""
    weights = []
    previous_to = None
    for e in path:
        fr, to = e

        if previous_to and fr != previous_to:
            tail = previous_to
            spath += label_vertex(G, tail)
            spath += '\n'

        previous_to = to

        spath += label_vertex(G, fr)
        spath += ' -%s' % G.ep.label[e]

        if weight_name == "no_weight":
            spath += '-> '
            continue

        w = G.ep[weight_name][e]
        if weight_name == "offset_weight":
            weights = intersect_ow(weights, w)
        else:
            spath += ' %s' % (w)
            weights.append(w)

        spath += '-> '

    tail = path[-1].target()
    spath += label_vertex(G, tail)
    return spath, weights

def my_load_graph(graph_path):
    return graph_tool.load_graph(graph_path, fmt='gt')

#ratio = 62 / (2**31 >> 12)
ratio = 17 / (2**31 >> 12)

def calculate_aw(G, path):
    vertices = get_nodes_path(path)
    pages = [G.vp.physical_addr[v] >> 12 for v in vertices]
    return (max(pages) - min(pages)) * ratio

def calculate_ctg(G, path):
    edges = [G.ep.atomicity_weight[e] for e in path]
    return sum(edges) * ratio

def calculate_mtg(G, path):
    edges = [G.ep.atomicity_weight[e] for e in path]
    return max(edges) * ratio

def calculate_mtg_pages(G, path):
    edges = [G.ep.atomicity_weight[e] for e in path]
    return max(edges)

def calculate_kc(G, path):
    ow = []
    for e in path:
        # print(G.ep.label[e], G.ep.offset_weight[e])
        ow = intersect_ow(ow, G.ep.offset_weight[e])
        # print(ow)
    return len(ow[0])

timings=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 100, 200, 350, 700, 1000, 3000, 5000, 8000, 12000]

# w = 1 means it never changed
# w = 25 means it changed after the first snapshot
def convert_heatmap_weight(w):
    idx = len(timings) - w
    return timings[idx]

def calculate_mct(G, path):
    return min([G.ep.heatmap_weight[e] for e in path])

from collections import defaultdict

def is_edge_correct(G, e):
    gap = get_aw_in_seconds(G, e)
    changed = G.ep.heatmap_weight[e]
    return gap <= changed

def is_path_correct(G, path):
    correct = True
    unstable = defaultdict(int)
    not_correct_edges = []
    for e in path:
        if not is_edge_correct(G, e):
            unstable[G.ep.label[e]] += 1
            not_correct_edges.append(e)
            correct = False

    # for k,v in unstable.items():
    #     print("[-] %s\t%s" % (k,v))
    return correct, not_correct_edges

def intersect_ow(current_ow, new_ow):
    if current_ow == []:
        return new_ow

    if new_ow == []:
        return []

    if type(current_ow[0]) is not list:
        current_ow = [current_ow]

    if type(new_ow[0]) is not list:
        new_ow = [new_ow]

    best = []
    for a,b in product(current_ow, new_ow):
        tmp = list(set(a) & set(b))
        if best == []:
            best.append(tmp)

        elif len(tmp) > len(best[0]):
            best = [tmp]

        elif len(tmp) == len(best[0]):
            best.append(tmp)

    return best

def get_inner_struct_ow(W, RAM, target_struct, field_name=""):
    if W is None:
        return None
    return get_inner_struct_ow_and_label(W, RAM, target_struct, field_name)[0]

def get_inner_struct_label(W, RAM, target_struct):
    return get_inner_struct_ow_and_label(W, RAM, target_struct)[1]

def get_inner_struct_ow_and_label(W, RAM, target_struct, target_field_name=""):
    structs = RAM[target_struct.addr]
    ow = []
    global_found = True
    label = ''

    if len(structs) == 1 or structs[0] == target_struct:
        if target_field_name != "" and W is not None:
            return W.offset_weight(target_struct, target_field_name), ''
        else:
            return [list(range(85))], ''

    for s1, s2 in zip(structs, structs[1:]):
        found = False
        for f in s1:
            union = False
            if f.is_array_of_struct() and s2.addr in f.array_elements:
                i = f.array_elements.index(s2.addr)
                field_name = '%s[%d]' % (f.name, i)
            elif f.is_struct() and f.addr == s2.addr:
                field_name = f.name
            elif f.ty == "union {...}" and f.addr == s2.addr:
                field_name = f.name
                union = True
            else:
                continue

            if field_name == "":
                label += "{union}."
            else:
                label += '%s.' % field_name

            # For unions we do an over approximation, often fields that were present before are included. e.g: dentry.d_lru
            if s1.is_global_container() or union or W is None:
                s1_ow = list(range(85))
            else:
                s1_ow = W.offset_weight(s1, field_name)

            ow = intersect_ow(ow, s1_ow)

        if s2 == target_struct:
            break

    if target_field_name != "" and W is not None:
        ow = intersect_ow(ow, W.offset_weight(target_struct, target_field_name))

    return ow, label
