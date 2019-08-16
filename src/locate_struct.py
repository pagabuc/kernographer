#!/usr/bin/env python
# Run with:
# > gdb --batch -q -x locate_struct.py

# Author: Fabio Pagani <fabio.pagani@eurecom.fr>
# Author: Davide Balzarotti <davide.balzarotti@eurecom.fr>
# Creation Date: 12-09-2016

import traceback
import socket
import cProfile
import logging
import time
import gdb
import sys
import os

sys.path.append("./")
from mytypes import Sample, Struct, Field, Node
from explorer import Explorer
from loader import Loader
from qemu_gdb import *
from worklist import *
from utils import *

SNAME = str(SNAME)
KDIR = str(KDIR)
QEMU_PORT = 2222
GDB_PORT = 1234

def fixup_field(s, f):
    # The size of kmem_cache is not the one reported in the DWARF
    # symbols: the array 'node' does not contain MAX_NUMNODES (as
    # specified in the definition) but rather nr_node_ids elements
    # (free_kmem_cache_nodes).
    if s.ty == "struct kmem_cache" and f.name == "node":
        nr_node_ids = int(gdb.parse_and_eval("nr_node_ids"))
        current_size = len(f.array_elements)
        f.ty = f.ty.replace(str(current_size), str(nr_node_ids))
        f.array_elements = f.array_elements[:nr_node_ids]
        s.size -= current_size * 8
        s.size += nr_node_ids * 8
        logging.debug("Fixed '%s' in:\n%s" % (f.name, s))

    if s.ty == "struct e820_table" and f.name == "entries":
        nr_entries = s["nr_entries"].value
        entries = f.array_elements
        f.array_elements = entries[:nr_entries]
        e820_entry_size = entries[1] - entries[0]
        s.size = e820_entry_size * nr_entries
        logging.debug("Fixed '%s' in:\n%s" % (f.name, s))        

        
def fixup_struct(s):
    if s.ty == "struct task_struct":
        s.size = int(gdb.parse_and_eval("arch_task_struct_size"))

    if s.ty == "struct thread_struct" or s.ty == "struct fpu":
        s.size -= (int(gdb.parse_and_eval("init_task").type.sizeof) -
                   int(gdb.parse_and_eval("arch_task_struct_size")))
        
def walk_field(worklist, explorer, s, f, struct, field, field_name):
    to_explore = []
    if is_ptr_of_ptr_field(s, f) and f.is_deref():
        field = cast_ptr_of_ptr(s, f, struct, field)
        f.value = gdb_value_to_int(field)
        f.set_ptr_array_of_ptr()

    if f.is_array_of_struct() or f.is_array_of_struct_ptr() or f.is_ptr_array_of_ptr():
        for i, (name, v) in enumerate(walk_array(field_name, field)):
            if is_struct_pointer(v.type):
                f.add_array_element(v)
            else:
                f.add_array_element(v.address)
                to_explore.append((v, i))

            worklist.append(name, v)

    if is_percpu_field(s, f):
        f.set_percpu()
        
        if f.value == 0:
            return []

        for offset, name, v in explorer.handle_percpu_field(field, field_name):
            f.add_array_element(v)
            worklist.append(name, v)
            to_explore.append((v, -1))
            # Here we keep only the last one..
            f.value = offset

    return to_explore

def walk_struct(w, worklist, sample, explorer):
    struct_name, struct, global_root = w

    s = Struct(struct.address,
               struct.type,
               struct_name,
               global_root)
        
    fixup_struct(s)    
    
    valid = is_valid_struct(struct)
    logging.debug("Walking struct '%s' '%s' (size: %d)... @ 0x%016x (valid: %s) %s" %
                  (s.ty, s.name, s.size, s.addr, valid, "GLOBAL" if s.global_root else ""))

    
    if not valid:
        logging.debug('%s' % struct)
        return

    for field_name, field in deep_items_anon(struct):  # Loop on the fields of the struct
        if is_type_size_zero(field.type):
            logging.warning("Zero size for field: %s %s" % (field.type, field_name))
            continue

        f = s.addField(field_name, field)

        appended = worklist.append(field_name, field)

        to_explore = [(field, -1)]
        to_explore += walk_field(worklist, explorer, s, f, struct, field, field_name)

        try:
            fixup_field(s, f)
        except gdb.error:
            logging.warning("Exception while fixing '%s' in:\n%s" % (f.name, s))

        logging.debug(f)

        if not appended and len(to_explore) == 1:
            continue

        for (tf, array_index) in to_explore:
            works = explorer.handle(s.ty, f.name, tf, array_index)
            for name, v in works:
                worklist.append(name, v)

    sample.dump_struct(s)


def explore_global_percpu(explorer, worklist, addr, sym, name):
    # was_ptr is needed because we don't model array of pointers of
    # pointers (es: current_task).  We miss a step of derefs, but
    # the __per_cpu_offset is stable so it should not affect the
    # analysis.
    was_ptr = False
    if is_struct(sym.type):
        sym = sym.cast(sym.type.pointer())
    else:
        was_ptr = True

    s = Struct(addr, sym.type, name, global_container=True)
    sym_array_ptr = sym.type.array(0, NR_CPUS-1).pointer()
    field_value = gdb.Value(addr).cast(sym_array_ptr).dereference()
    f = s.addField(name, field_value)
    s.size = 8*(NR_CPUS)

    for offset, name, v in explorer.handle_percpu_field(sym, name):
        worklist.append(name, v)
        if was_ptr:
            v = v.dereference()
        f.add_array_element(v, check=False)
        
    return s
    
def explore_global_percpus(sample, explorer, worklist, global_percpus):

    addr = 0xffffffff82000000
    sorted_percpus = sorted(global_percpus.items(), key=lambda x:x[0])

    for (filename, name), sym in sorted_percpus:
        logging.debug("Loading GLOBAL_PERCPU: %s %s" % (filename, name))
        s = explore_global_percpu(explorer, worklist, addr, sym, name)        
        sample.dump_struct(s)
        logging.debug(s)
        addr += 8*(NR_CPUS)


def do_analysis(worklist, sample, explorer):
    for i, work in enumerate(worklist.worklist):
        walk_struct(work, worklist, sample, explorer)

        if i % 50000 == 0:
            tot = len(worklist.worklist)
            sys.stdout.write("processed: %d total: %d left: %d\n" % (i, tot,
                                                                     tot - i))
            sys.stdout.flush()
        
def explore_sample():
    exp_result = "../explorations/%s" % (SNAME)
    print("[+] Exploration result in %s" % exp_result)
    sample = Sample(exp_result)
    L = Loader(KDIR)

    worklist = L.WORKLIST
    global_structs_addr = set([gdb_value_to_int(v.address) for (_, v, _) in worklist.worklist])
    explorer = Explorer(L.NODE_INFO, L.POINTER_INFO, global_structs_addr)
    global_heads = L.GLOBAL_HEADS
    global_percpus = L.PERCPU_GLOBALS

    for s in L.GLOBAL_CONTAINERS:
        sample.dump_struct(s)

    explore_global_percpus(sample, explorer, worklist, global_percpus)

    for i in global_heads:
        struct_type, field_name = global_heads[i]
        for name, v in explorer.handle_global_head(i, struct_type, field_name):
            worklist.append(name, v)

    print("[+] Ready to start the exploration")
    do_analysis(worklist, sample, explorer)
    logging.info("[+] We found %d structs" % sample.counter)
    return


def create_dir(d):
    if not os.path.exists(d):
        os.makedirs(d)
    
def main():
    print("[+] Target kernel %s" % KDIR)
    
    create_dir("../logs")
    create_dir("../explorations/")
    
    log_file = "../logs/%s" % (SNAME)
    print("[+] Logging in %s" % log_file)
    logging.basicConfig(format='%(levelname)s : %(message)s',
                        stream=open(log_file, "w"),
                        level=logging.DEBUG)

    logging.debug("gdb_port = %d qemu_port = %d" % (GDB_PORT, QEMU_PORT))

    gdb.execute('add-symbol-file %s/vmlinux 0' % KDIR, to_string=True)
    gdb.execute('set architecture i386:x86-64', to_string=True)
    gdb.execute('set max-value-size unlimited', to_string=True)
    gdb.execute('maint set symbol-cache-size 4096')
    connect_gdb_remote(GDB_PORT)

    connect_qemu_monitor('localhost', QEMU_PORT)
    send_qemu_monitor(b'stop')
    send_qemu_monitor('loadvm %s' % SNAME)

    load_executable_sections(KDIR)

    print('\n------ Analyzing %s ------' % SNAME)
    start = time.time()
    explore_sample()
    print("Exploration took: %.2fs" % (time.time() - start))

    gdb.execute('disconnect')

if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print(traceback.print_exc())
        gdb.execute('disconnect')


    # cProfile.run('main()', filename="/tmp/prof%d" % SID, sort=1)

    # sym = gdb.lookup_symbol("pid_hash")[0]
    # print(is_valid_struct(a.value()))
    # sys.exit(-1)
    # t = gdb.lookup_type("struct mm_slot")
    # print(find_offset(t, "mm_node", array_index=-1))
    # v = gdb.Value(0x2345234523424).cast(t)
    # sys.exit(-1)
