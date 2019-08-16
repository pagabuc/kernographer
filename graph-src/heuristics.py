import sys
from graph_tool.all import *
from itertools import zip_longest

sys.path.append("../graphs/")
from graph_utils import *

def walk_neighbour(G, n):
    return follow_field(G, n, "dev")

# RQ
def rq_root_task_group_pslist(G):
    edges = []
    root_task_group = graph_tool.util.find_vertex(G, G.vp.name, "root_task_group")[0]
    e, array = follow_field(G, root_task_group, "cfs_rq")
    edges.append(e)
    for e, rq in get_out_targets(array):
        edges.append(e)
        e, task = follow_field(G, rq, "curr")
        if e:
            edges.append(e)
    return edges

def rq_runqueues_pslist(G):
    edges = []
    runqueues = graph_tool.util.find_vertex(G, G.vp.name, "runqueues")[0]
    first = True
    for e, rq in get_out_targets(runqueues):
        if first:
            edges.append(e)
            first = False
        e, task = follow_field(G, rq, "curr")
        if e:
            edges.append(e)
    return edges

# CGROUP

def cgroup_cgrp_dfl_root_pslist(G):
    edges = []
    for e, cgrp_cset_link in explore_list_global_variable(G, "cgrp_dfl_root", "cgrp.cset_links.next", "cset_link.next"):
        e, css_set = follow_field(G, cgrp_cset_link, "cset")
        if e:
            edges.append(e)
            for e_task, task in explore_list(G, css_set, "tasks.next", "cg_list.next"):
                edges.append(e_task)
    return edges

def cgroup_css_set_table_pslist(G):
    edges = []
    css_set_table = graph_tool.util.find_vertex(G, G.vp.name, "css_set_table")[0]
    for e_css_set, css_set in list(get_out_targets(css_set_table)):
        edges.append(e_css_set)
        first_css_set = css_set
        while True:
            for e_task, task in explore_list(G, css_set, "tasks.next", "cg_list.next"):
                edges.append(e_task)
            e, css_set = follow_field(G, css_set, "hlist.next")
            if not css_set or css_set == first_css_set:
                break
            edges.append(e)
    return edges


# def root_task_group_pslist(G):
#     edges = []
#     root_task_group = graph_tool.util.find_vertex(G, G.vp.name, "root_task_group")[0]
#     e, cgroup_root = follow_field(G, root_task_group, "css.cgroup")
#     edges.append(e)
#     for e, css_set in explore_list(G, cgroup_root, "cgrp.e_csets[1].next", "e_cset_node[1].next"):
#         edges.append(e)
#         for e_task, task in explore_list(G, css_set, "tasks.next", "cg_list.next"):
#             edges.append(e_task)
#     return edges

# MM

# def mm_mm_slot_hash_pslist(G):
#     edges = []
#     mm_structs = set()
#     tasks = set()
#     mm_slots_hash = graph_tool.util.find_vertex(G, G.vp.name, "mm_slots_hash")[0]

#     for e, mm_slot in get_out_targets(mm_slots_hash):
#         edges.append(e)
#         e, mm_struct = follow_field(G, mm_slot, "mm")
#         e, vm_area_struct = follow_field(G, mm_struct, "mmap")
#         mm_structs.add(mm_struct)
#         for e, vm_area_struct in _walk_rb(G, e, vm_area_struct, "rb"):
#             edges.append(e)
#             mm_struct_edge, mm_struct = follow_field(G, vm_area_struct, "vm_mm")
#             # if mm_struct in mm_structs:
#             #     continue
#             mm_structs.add(mm_struct)
#             task_edge, task = follow_field(G, mm_struct, "owner")
#             edges.append(task_edge)
#             print(G.vp.label[task])
#             tasks.add(task)
#     print(len(tasks))

def mm_dentry_hashtable_pslist(G):
    edges = []
    first = True
    mm_structs = set()
    dentry_hashtable = graph_tool.util.find_vertex(G, G.vp.name, "dentry_hashtable")[0]
    for hlist_bl_head_edge, hlist_bl_head  in list(get_out_targets(dentry_hashtable)):
        if first:
            edges.append(hlist_bl_head_edge)
            first = False

        e, dentry = follow_field(G, hlist_bl_head, "first")
        edges.append(e)
        e, inode = follow_field(G, dentry, "d_inode")
        if not e:
            continue
        edges.append(e)
        # Walking
        e, vm_area_struct = follow_field(G, inode, "i_data.i_mmap.rb_node")
        for e, vm_area_struct in _walk_rb(G, e, vm_area_struct, "rb"):
            edges.append(e)
            mm_struct_edge, mm_struct = follow_field(G, vm_area_struct, "vm_mm")

            if mm_struct in mm_structs:
                continue
            mm_structs.add(mm_struct)
            edges.append(mm_struct_edge)
            task_edge, task = follow_field(G, mm_struct, "owner")
            edges.append(task_edge)
    return edges


def mm_inode_hashtable_pslist(G):
    edges = []
    hlist_heads = set()
    inode_hashtable = graph_tool.util.find_vertex(G, G.vp.name, "inode_hashtable")[0]
    first = True
    mm_structs = set()

    for hlist_head_edge, hlist_head  in list(get_out_targets(inode_hashtable)):

        if hlist_head in hlist_heads:
            continue
        hlist_heads.add(hlist_head)

        if first:
            edges.append(hlist_head_edge)
            first = False

        e, inode = follow_field(G, hlist_head, "first")
        edges.append(e)
        e, vm_area_struct = follow_field(G, inode, "i_data.i_mmap.rb_node")

        for e, vm_area_struct in _walk_rb(G, e, vm_area_struct, "rb"):
            edges.append(e)
            mm_struct_edge, mm_struct = follow_field(G, vm_area_struct, "vm_mm")

            if mm_struct in mm_structs:
                continue
            mm_structs.add(mm_struct)
            edges.append(mm_struct_edge)
            task_edge, task = follow_field(G, mm_struct, "owner")
            edges.append(task_edge)

    return edges

def wq_workqueues_pslist(G):
    workers = set()
    edges = []
    for e, workqueue_struct in explore_list_global_variable(G, "workqueues", "next", "list.next"):
        edges.append(e)
        e, worker = follow_field(G, workqueue_struct, "rescuer")
        if e and worker not in workers:
            edges.append(e)
            e, task = follow_field(G, worker, "task")
            edges.append(e)
        workers.add(worker)

        for e, pool_workqueue in explore_list(G, workqueue_struct, "pwqs.next", "pwqs_node.next"):
            edges.append(e)
            e, worker_pool = follow_field(G, pool_workqueue, "pool")
            edges.append(e)
            for e, worker in explore_list(G, worker_pool, "workers.next", "node.next"):
                edges.append(e)
                if worker in workers:
                    continue
                workers.add(worker)

                e, task = follow_field(G, worker, "task")
                edges.append(e)


    return edges

# linux_arp
def arp(G):
    edges = []
    neigh_tables = graph_tool.util.find_vertex(G, G.vp.name, "neigh_tables")[0]
    for e, ntable in get_out_targets(neigh_tables):
        edges.append(e)
        nht_edge, nht = follow_field(G, ntable, "nht")
        edges.append(nht_edge)
        buckets_edge, buckets = follow_field(G, nht, "hash_buckets")
        if not buckets:
            continue
        edges.append(buckets_edge)
        for edge_name in get_out_edges_name(G, buckets):
            for neighbour_edge, neighbour in explore_list(G, buckets, edge_name, "next"):
                edges.append(neighbour_edge)
                dev_edge, dev = follow_field(G, neighbour, "dev")
                if dev_edge:
                    edges.append(dev_edge)
    return edges

# linux_check_tty
def tty_check(G):
    edges = []
    for e, tty_driver in explore_list_global_variable(G, "tty_drivers", "next", "tty_drivers.next"):
        edges.append(e)
        ttys_edge, ttys = follow_field(G, tty_driver, "ttys")
        if not ttys_edge:
            continue
        edges.append(ttys_edge)
        for tty_edge, tty in get_out_targets(ttys):
            edges.append(tty_edge)
    return edges

output = []
def yield_resource(G, t, output = []):
    if (not t[1]) or (t[1] in [x[1] for x in output]):
        return []
    output += [t]
    if "struct pci_dev" in G.vp.label[t[1]]:
        yield_resource(G, follow_field(G, t[1], "resource[0].sibling"), output)
    else:
        yield_resource(G, follow_field(G, t[1], "child"), output)
        yield_resource(G, follow_field(G, t[1], "sibling"), output)
    return output

def iomem(G):
    edges = []
    gv = graph_tool.util.find_vertex(G, G.vp.name, "iomem_resource")[0]
    e, r = follow_field(G, gv, "child")
    edges.append(e)
    for t in yield_resource(G, (e, r)):
        e, r = t
        edges.append(e)
    return edges

def _walk_rb(G, e, vma, rb_field_name):
    if not vma:
        return

    yield e, vma

    e, new_vma = follow_field(G, vma, "%s.rb_left" % rb_field_name)
    for e, new_vma in _walk_rb(G, e, new_vma, rb_field_name):
        yield e, new_vma

    e, new_vma = follow_field(G, vma, "%s.rb_right" % rb_field_name)
    for e, new_vma in _walk_rb(G, e, new_vma, rb_field_name):
        yield e, new_vma

def proc_maps_rb(G):
    edges = []
    for task_edge, task in tasks(G):
        e, mm_struct = follow_field(G, task, "mm")
        if e:
            edges.append(e)
            e, rb_node = follow_field(G, mm_struct, "mm_rb.rb_node")
            for e, vma in _walk_rb(G, e, rb_node, "vm_rb"):
                edges.append(e)

        if task_edge:
            edges.append(task_edge)
    return edges

def proc_maps(G):
    edges = []
    for task_edge, task in tasks(G):
        e, mm_struct = follow_field(G, task, "mm")
        if e:
            edges.append(e)
            for e, vma in explore_list(G, mm_struct, "mmap", "vm_next"):
                edges.append(e)

        if task_edge:
            edges.append(task_edge)
    return edges

def explore_parents(G, mount):
    e, mnt_parent = follow_field(G, mount, "mnt_parent")
    if mnt_parent:
        yield e, mnt_parent
        e, mnt_parent_parent = follow_field(G, mnt_parent, "mnt_parent")
        if mnt_parent_parent:
            yield e, mnt_parent_parent

def do_get_path(G, rdentry, rmnt, dentry, vfsmnt):
    edges = []
    e, inode = follow_field(G, dentry, "d_inode")
    if not inode:
        return []
    edges.append(e)

    while (dentry != rdentry or vfsmnt != rmnt):
        e1, vfsmnt_mnt_root = follow_field(G, vfsmnt, "mnt.mnt_root")
        e2, dentry_dparent = follow_field(G, dentry, "d_parent")
        if not vfsmnt_mnt_root or not dentry_dparent:
            break
        edges.append(e1)
        edges.append(e2)

        if (dentry == vfsmnt_mnt_root or dentry == dentry_dparent):
            e, vfsmnt_mnt_parent = follow_field(G, vfsmnt, "mnt_parent")
            if(vfsmnt == vfsmnt_mnt_parent):
                break
            edges.append(e)

            e1, dentry = follow_field(G, vfsmnt, "mnt_mountpoint")
            e2, vfsmnt = follow_field(G, vfsmnt, "mnt_parent")
            if not dentry or not vfsmnt:
                break
            edges.append(e1)
            edges.append(e2)
            continue

        e, parent = follow_field(G, dentry, "d_parent")
        dentry = parent
        if not dentry:
            break
        edges.append(e)

    return edges

def mount(G):
    edges = []

    fs_types = set()
    for e, fs in explore_list_global_variable(G, "file_systems", "file_systems", "next"):
        edges.append(e)
        fs_types.add(fs)

    mount_hashtable = graph_tool.util.find_vertex(G, G.vp.name, "mount_hashtable")[0]
    all_mnts = set()

    for edge_name in list(get_out_edges_name(G, mount_hashtable)):
        e, hlist_head = follow_field(G, mount_hashtable, edge_name)
        edges.append(e)
        for e, mount in explore_list(G, hlist_head, "first", "mnt_hash.next"):
            edges.append(e)
            all_mnts.add(mount)
            for e, mnt in explore_parents(G, mount):
                edges.append(e)
                all_mnts.add(mnt)

    child_mnts = set()
    for mount in all_mnts:
        for e, mnt in explore_list(G, mount, "mnt_child.next", "mnt_child.next"):
            if mnt in child_mnts:
                break

            edges.append(e)
            child_mnts.add(mnt)
            for e, mnt_p in explore_parents(G, mnt):
                edges.append(e)
                child_mnts.add(mnt_p)
    all_mnts.update(child_mnts)

    list_mnts = set()
    for mount in all_mnts:
        for e, mnt in explore_list(G, mount, "mnt_list.next", "mnt_list.next"):
            if mnt in list_mnts:
                break

            edges.append(e)
            list_mnts.add(mnt)
            for e, mnt_p in explore_parents(G, mnt):
                edges.append(e)
                list_mnts.add(mnt_p)
    all_mnts.update(list_mnts)

    seen = set()
    for mnt in all_mnts:
        e1, mnt_sb = follow_field(G, mnt, "mnt.mnt_sb")
        if not mnt_sb or mnt_sb in seen:
            continue

        e2, s_root = follow_field(G, mnt_sb, "s_root")
        e3, mnt_parent = follow_field(G, mnt, "mnt_parent")
        e4, mnt_root = follow_field(G, mnt, "mnt.mnt_root")
        if not (s_root and mnt_parent and mnt_root):
            continue

        edges+=[e1,e2,e3,e4]
        edges+=do_get_path(G, s_root, mnt_parent, mnt_root, mnt)

        seen.add(mnt_sb)

    return edges

# linux_check_modules
def check_modules(G):
    edges = []
    module_kset_ptr = graph_tool.util.find_vertex(G, G.vp.name, "module_kset")[0]
    e, module_kset = follow_field(G, module_kset_ptr, "module_kset")
    edges.append(e)
    e, kobj = follow_field(G, module_kset, "list.next")
    edges.append(e)
    while True:
        label = G.vp.label[kobj]
        if "struct kobject" in label:
            e, next_kobj = follow_field(G, kobj, "entry.next")
        elif "struct module_kobject" in label:
            e, next_kobj = follow_field(G, kobj, "kobj.entry.next")
        elif "struct module" in label:
            e, next_kobj = follow_field(G, kobj, "mkobj.kobj.entry.next")

        edges.append(e)
        if next_kobj == module_kset:
            break

        kobj = next_kobj

    return edges

def _walk_sb(G, dentry_param):
    edges = []
    for e, dentry in explore_list(G, dentry_param, "d_subdirs.next", "d_child.next"):

        if dentry == dentry_param:
            return []

        if e:
            edges.append(e)
            inode_edge, inode = follow_field(G, dentry, "d_inode")
            if inode_edge:
                edges.append(inode_edge)

            edges+=_walk_sb(G, dentry)

    return edges

def _get_sbs(G):
    mount_path = mount(G)
    mount_nodes = get_nodes_path(mount_path)
    sbs = [v for v in mount_nodes if "struct super_block" in G.vp.label[v]]
    return mount_path, sbs

def walk_sbs(G):
    path, sbs = _get_sbs(G)
    edges = path

    for sb in sbs:
        e, s_root = follow_field(G, sb, "s_root")
        if e:
            edges.append(e)
            edges+=_walk_sb(G, s_root)

    return edges

def find_file(G):
    edges = walk_sbs(G)
    return edges


def lsof(G):
    edges = []
    for task_edge, task in tasks(G):
        e, files = follow_field(G, task, "files")
        if not files:
            continue
        edges.append(e)

        e, fdt = follow_field(G, files, "fdt")
        if not fdt:
            continue
        edges.append(e)

        # In some cases the fdt pointer points to the field fdtab inside the same files_struct
        if fdt == files:
            e, array_file_ptr = follow_field(G, files, "fdtab.fd")
        else:
            e, array_file_ptr = follow_field(G, fdt, "fd")

        if array_file_ptr is None:
            continue

        edges.append(e)

        if len(list(get_out_edges_name(G, array_file_ptr))) == 0:
            continue

        # print("%s %d" % (G.vp.label[task], len(list(get_out_edges_name(G, array_file_ptr)))))

        e, fs_struct = follow_field(G, task, "fs")
        if not fs_struct:
            continue

        edges.append(e)

        for e, filp in get_out_targets(array_file_ptr):
            # print(G.vp.label[filp])
            # dump_out_edges(G, filp)
            edges.append(e)
            e1, rdentry = follow_field(G, fs_struct, "root.dentry")
            e2, rmnt = follow_field(G, fs_struct, "root.mnt")
            e3, dentry = follow_field(G, filp, "f_path.dentry")
            e4, vfsmnt = follow_field(G, filp, "f_path.mnt")
            if not(e1 and e2 and e3 and e4):
                continue

            edges+=[e1,e2,e3,e4]
            edges+=do_get_path(G, rdentry, rmnt, dentry, vfsmnt)

        if task_edge:
            edges.append(task_edge)
    # print(len(edges))
    return edges

# linux_lsmod
def lsmod(G):
    edges = []
    for e, module in explore_list_global_variable(G, "modules", "next", "list.next"):
        edges.append(e)
    return edges

#linux_ifconfig
def ifconfig(G):
    edges = []
    for e, net in explore_list_global_variable(G, "net_namespace_list", "next", "list"):
        edges.append(e)
        for e, net_dev in explore_list(G, net, "dev_base_head.next", "dev_list.next"):
            edges.append(e)
            e, in_dev = follow_field(G, net_dev, "ip_ptr")
            if not in_dev:
                continue
            edges.append(e)
            for e, ifa in explore_list(G, in_dev, "ifa_list", "ifa_next"):
                if not ifa:
                    continue
                edges.append(e)
    return edges

def tasks(G):
    ps = list(pslist(G))
    tasks = [t.source() for t in ps]
    tasks.append(ps[-1].target())
    return zip_longest(ps, tasks)

def check_creds(G):
    edges = pslist(G)
    for task_edge, task in tasks(G):
        e, cred = follow_field(G, task, "cred")
        if not e:
            continue
        edges.append(e)
    return edges

def threads(G):
    edges = pslist(G)
    for task_edge, task in tasks(G):
        threads = []
        while task not in threads:
            threads.append(task)
            e, task = follow_field(G, task, "thread_group.next")
            if not e:
                break
            edges.append(e)
    return edges

# linux_pslist
def pslist(G):
    edges = []
    for e, task in explore_list_global_variable(G, "init_task", "tasks.next", "tasks.next"):
        edges.append(e)
    return edges

# linux_check_afinfo
def check_afinfo(G):
    check = ["tcp6_seq_afinfo", "tcp4_seq_afinfo", "udplite6_seq_afinfo",
             "udp6_seq_afinfo", "udplite4_seq_afinfo", "udp4_seq_afinfo"]
    edges = lsmod(G)
    for gvname in check:
        v = graph_tool.util.find_vertex(G, G.vp.name, gvname)[0]
        e, seq_fops = follow_field(G, v, "seq_fops")
        if not seq_fops:
            continue
        edges.append(e)
    return edges


# linux_psxview
def pidhashtable(G):
    pid_hash = graph_tool.util.find_vertex(G, G.vp.name, "pid_hash")[0]
    path = []
    first = True
    for edge_name in list(get_out_edges_name(G, pid_hash)):
        hlist_head_edge, hlist_head = follow_field(G, pid_hash, edge_name)
        if first:
            path.append(hlist_head_edge)
            first = False

        for pid_edge, pid in explore_list(G, hlist_head, "first", "pid_chain.next"):
           if not pid:
               continue
           path.append(pid_edge)
           task_edge, task = follow_field(G, pid, "tasks[0].first")
           if not task:
               continue
           path.append(task_edge)
    return path


def _do_walk_proc_current(G, proc_root):
    edges = []
    e, node = follow_field(G, proc_root, "subdir.rb_node")
    for e, pde in _walk_rb(G, e, node, "subdir_node"):
        edges.append(e)
        fops_edge, fops = follow_field(G, pde, "proc_fops")
        if fops_edge:
            edges.append(fops_edge)

        edges+=_do_walk_proc_current(G, pde)

    return edges


def check_file_cache(G):
    edges = find_file(G)
    for n in get_nodes_path(edges):
        if "struct inode" in G.vp.label[n]:
            e, i_fop = follow_field(G, n, "i_fop")
            edges.append(e)
    return edges


def check_open_files_fop(G):
    return lsof(G)

def check_proc_fop(G):
    edges = pslist(G)
    seen_pids = set()
    for _, task in tasks(G):
        e, nsp = follow_field(G, task, "nsproxy")
        if not e:
            continue
        edges.append(e)

        e, pidns = follow_field(G, nsp, "pid_ns_for_children")

        if pidns in seen_pids:
            continue

        seen_pids.add(pidns)

        if not e:
            continue
        edges.append(e)

        e, mount = follow_field(G, pidns, "proc_mnt")
        if not e:
            continue
        edges.append(e)

    return edges

def check_proc_net_fops(G):
    edges = []
    for e, net in explore_list_global_variable(G, "net_namespace_list", "next", "list.next"):
        edges.append(e)
        proc_net_edge, proc_net = follow_field(G, net, "proc_net")
        if proc_net_edge:
            edges.append(proc_net_edge)
            edges+=_do_walk_proc_current(G, proc_net)
    return edges

def check_proc_root_fops(G):
    edges = []
    proc_root = graph_tool.util.find_vertex(G, G.vp.name, "proc_root")[0]

    e, proc_fops = follow_field(G, proc_root, "proc_fops")
    if e:
        edges.append(e)

    edges += _do_walk_proc_current(G, proc_root)
    return edges

def check_fops(G):
    edges = lsmod(G)
    funcs = [check_open_files_fop, check_proc_fop, check_proc_root_fops, check_proc_net_fops, check_file_cache]
    for func in funcs:
        edges += func(G)

    return edges
