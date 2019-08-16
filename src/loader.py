import gdb
import logging
import re
from utils import *
from mytypes import Node
from worklist import *
import sys
import functools
import os
import json

# POINTER_INFO is a dictionary where:
# keys are ('pointer struct',  'pointer field')
# items are ('pointee struct', 'pointee field')

class Loader:
    def __init__(self, KDIR):
        self.INFO_FILE = os.path.join(KDIR, "kernel_info.txt")
        # nm ./vmlinux  -l > System.map.line_number
        self.SYSTEM_MAP_FILE = os.path.join(KDIR, "System.map.line_numbers")
        self.PERCPU_GLOBALS_FILE = os.path.join(KDIR, "percpu_globals.txt")

        for f in [self.INFO_FILE, self.SYSTEM_MAP_FILE, self.PERCPU_GLOBALS_FILE]:
            if not os.path.isfile(f):
                print("[-] Missing: %s" % f)
                sys.exit(-1)

        self.WORKLIST = Worklist()
        self.POINTER_INFO = {}
        self.GLOBAL_HEADS = {}
        self.NODE_INFO = {}
        self.GLOBAL_CONTAINERS = set()
        self.PERCPU_GLOBALS = {}
        self.load_info()

    def load_info(self):
        print("[+] Loading pointer info")
        self.load_pointer_info()
        print("[+] Loading node info")
        self.load_node_info()

        print("[+] Loading percpu globals")
        self.load_percpu_global_info()
        print("[+] Loading global hashtables")
        self.load_global_hashtables()
        
        print("[+] Loading System.map")
        self.load_system_map()

        assert(len(self.NODE_INFO) == len(self.POINTER_INFO))

    def load_percpu_global_info(self):
        r = re.compile("(.*):\d*:.*\(.*,(.*)\)")
        f = open(self.PERCPU_GLOBALS_FILE, 'r')

        for line in f:
            line = line.strip()
            match = r.search(line)

            if not match or "[" in line:
                continue

            filename = match.group(1).strip()
            name = match.group(2).strip()

            if(filename, name) in self.PERCPU_GLOBALS:
                continue

            try:
                full_type = "'%s'::'%s'" % (filename, name)
                s = gdb.parse_and_eval(full_type)
            except gdb.error:
                continue

            self.PERCPU_GLOBALS[(filename, name)] = s

    def navigate_struct(self, s, fields):
        s = resolve_type_ptr(s)
        fields = [i for i in fields if "struct " not in i]

        for f in fields:
            try:
                s = resolve_type_ptr(s[f].type)
            except:
                raise AttributeError
            if is_void(s):
                raise AttributeError
        return s

    def extract_info(self, info, is_global):
        
        if not is_global:
            info = self.clean(info)

        split = info.split(".")
        try:
            if is_global:
                symbol = self.load_symbol(split[0])
                s = symbol.type
            else:
                s = gdb.lookup_type(split[0])
            s = self.navigate_struct(s, split[1:-1])
        except (gdb.error, TypeError, AttributeError):
            s = None

        if s is None or "{...}" in str(s):
            return "ERR", "ERR"
        
        return str(s), split[-1]

    # For example: struct file.private_data.struct tty_file_private.list
    # it returns:  struct tty_file_private.list

    # XXX: We should fix this in the Clang plugin, by traversing those
    # MemberExpr that contains another MemberExpr..
    def clean(self, p):
        s = p.split("struct ")
        return "struct " + s[-1]

    def load_pointer_info(self):
        logging.info("[+] Loading pointer info from: %s" % self.INFO_FILE)

        for line in open(self.INFO_FILE):
            e = json.loads(line)

            # t = e["type"]
            # t = "TYPE"
            # if 'entry_global' in e:
            #     t = "GLOBAL_ENTRY"
            # elif 'head_global' in e:
            #     t = "GLOBAL"
                
            pointer = e["head"]
            pointee = e["entry"]

            pointer_global = bool(e.get("head_global", False))
            pointee_global = bool(e.get("entry_global", False))
            
            s1, f1 = self.extract_info(pointer, pointer_global)
            s2, f2 = self.extract_info(pointee, pointee_global)

            logging.debug("[HERE] %s -> %s : %s.%s -> %s.%s" % (pointer, pointee, s1,f1,s2,f2))

            if s1 == "ERR" or s2 == "ERR":
                continue

            if s1 != "struct list_head" and s2 != "struct list_head":
                self.POINTER_INFO[(s1, f1)] = (s2, f2)

            if pointer_global and s1 == "struct list_head":
                head_name = pointer.split(".")[0]
                self.GLOBAL_HEADS[head_name] = (s2, f2)
                self.POINTER_INFO[(s2, f2)] = (s2, f2)

            if pointer_global and s1 in ["struct hlist_head", "hlist_bl_head"]:
                head_name = pointer.split(".")[0]
                head_symbol = self.load_symbol(head_name)
                if head_name not in GLOBAL_HASHTABLES and is_array_of_struct(head_symbol.type):
                    size = head_symbol.type.sizeof
                    GLOBAL_HASHTABLES[head_name] = (size, s2, f2, "")

        # Manual Pointer infos..
        # /kernel/trace/trace_events.c
        self.POINTER_INFO[("struct trace_event_class", "fields")] = ("struct ftrace_event_field", "link")
        logging.info("[+] Loaded %d pointer info" % len(self.POINTER_INFO))

    # Node.INTER is functionally useless, we just keep it to discern MISSING_INFOs in Explorer
    def load_node_info(self):
        items = list(self.POINTER_INFO.items())

        # Set all the node as Node.NORM
        for (ptr, ptr_f), (pte, pte_f) in items:
            self.NODE_INFO[(ptr, ptr_f)] = Node.NORM

        # Now if we find a root node, set it as root and the pointee
        # as intermediate
        for (ptr, ptr_f), (pte, pte_f) in items:
            if ((ptr == pte and ptr_f != pte_f) or (ptr != pte)):  # ROOTS
                self.NODE_INFO[(ptr, ptr_f)] = Node.ROOT
                self.NODE_INFO[(pte, pte_f)] = Node.INTER

        # Expand node information to pointer information.
        # If a node is intermediate, it points to itself
        for (ptr, ptr_f), info in self.NODE_INFO.items():
            if info == Node.INTER:
                self.POINTER_INFO[(ptr, ptr_f)] = (ptr, ptr_f)

        # Set all the pointee of global_heads as intermediate..
        for (pte, pte_f) in self.GLOBAL_HEADS.values():
            self.NODE_INFO[(pte, pte_f)] = Node.INTER

        # Debug
        for (s1, f1), (s2, f2) in self.POINTER_INFO.items():
            logging.debug("[POINTER_INFO]: %s.%s -> %s.%s" % (s1, f1, s2, f2))

        for (s), (s2, f2) in self.GLOBAL_HEADS.items():
            logging.debug("[GLOBAL_HEADS]: %s -> %s.%s" % (s, s2, f2))

        for (ptr, ptr_f), info in self.NODE_INFO.items():
            logging.debug("[NODE_INFO] %s.%s %s" % (ptr, ptr_f, info))

    def sort_symbols(self, e1, e2):
        s1 = e1[0]
        s2 = e2[0]

        if is_struct(s1.type):
            return -1
        if is_struct(s2.type):
            return 1
        return 0

    def load_symbol(self, name, filename=""):
        if filename != "":
            filename = filename.split(":")[0]
            s = "'%s'::'%s'" % (filename, name)
        else:
            s = name

        try:
            v = gdb.parse_and_eval(s)
        except gdb.error:
            logging.debug("[-] Failed to load symbol %s %s" % (name, filename))
            return None

        if v.is_optimized_out or not is_fetchable(v):
            logging.debug("[-] Failed to load symbol (optimized/non fetchable) %s %s" % (name, filename))
            return None

        logging.debug("[+] Loaded symbol %s %s" % (name, filename))
        return v

    def skip_symbol(self, type, name):
        return (name.startswith(("__kstrtab", "__kcrctab", "__tpstrtab", "__crc_", "__ksymtab_")) or
                type.lower() == 't' or '.' in name)

    def create_global_container(self, sym_value, sym_type, sym_name, nv):
        s = Struct(sym_value.address, sym_type,
                   sym_name, global_container=True)

        f = s.addField(sym_name, sym_value)

        if is_array_of_struct_pointer(sym_type):
            s.size = sym_type.target().sizeof * len(nv)
            for name, v in nv:
                f.add_array_element(v)

        if is_array_of_struct(sym_type):
            s.size = sym_value.type.sizeof
            for name, v in nv:
                f.add_array_element(v.address)

        return s

    def parse_system_map_line(self, line):
        line = line.strip().replace("\t", " ")
        try:
            sym_addr, sym_type, sym_name, sym_filename = line.split(" ")
        except ValueError:
            sym_addr, sym_type, sym_name = line.split(" ")
            sym_filename = ""

        return int(sym_addr, 16), sym_type, sym_name, sym_filename

    def load_system_map(self):
        f = open(self.SYSTEM_MAP_FILE, 'r')
        symbols = []

        for line in f.readlines():
            sym_addr, sym_type, sym_name, sym_filename = self.parse_system_map_line(line)

            if (self.skip_symbol(sym_type, sym_name) or sym_name in GLOBAL_HASHTABLES or
                (sym_filename, sym_name) in self.PERCPU_GLOBALS):
                continue

            sym = self.load_symbol(sym_name, sym_filename)

            if sym:
                symbols.append((sym, sym_name, sym_addr))

        symbols.sort(key=functools.cmp_to_key(self.sort_symbols))

        for sym, sym_name, sym_addr in symbols:

            sym_type = sym.type

            if is_array_of_struct(sym_type) or is_array_of_struct_pointer(sym_type):
                nv = list(walk_array(sym_name, sym))
                logging.debug("[+] Global symbol array: %s.%s" % (sym_name, str(sym_type)))
            elif is_struct(sym_type) or is_struct_pointer(sym_type):
                nv = [(sym_name, sym)]
            else:
                continue

            if int(sym.address) != sym_addr:
                print("[-] Symbol address mismatch: %s %x != %x" % (sym_name,
                                                                    sym_addr,
                                                                    int(sym.address)))

            logging.debug("[+] Succeded to load symbol %s of type %s " % (sym_name, str(sym.type)))
            is_global_work = True

            # Create the global container
            if ((is_struct_pointer(sym_type) and is_dereferenceable(sym)) or
                is_array_of_struct_pointer(sym_type) or is_array_of_struct(sym_type)):
                is_global_work = False
                s = self.create_global_container(sym, sym_type, sym_name, nv)
                self.GLOBAL_CONTAINERS.add(s)

            for name, v in nv:
                self.WORKLIST.append(name, v, is_global_work)

            f.close()

    def load_global_hashtable(self, sym, sym_name, size, pte_type, pte_field_name, filename):
        orig_sym = sym
        
        if is_struct_pointer(sym.type):
            array = sym.dereference().cast(sym.type.target().array(0, size - 1))
            sym = sym.cast(sym.type.array(0, size - 1))
        else:
            array = sym

        s = Struct(sym.address, orig_sym.type, sym_name, global_container=True)
        f = s.addField(sym_name, sym)

        pte_type = lookup_type(pte_type, filename)
        offset = find_offset(pte_type.target(), pte_field_name)

        for name, value in list(walk_array(sym_name, array)):
            elem = value["first"]
            if gdb_value_to_int(elem) == 0:
                f.add_array_element(0)
                continue

            # This add the hlist_head
            f.add_array_element(value.address)
            self.WORKLIST.append(name, value)

            while gdb_value_to_int(elem) != 0:
                pte_struct = custom_container_of(elem, pte_type, offset).dereference()
                self.WORKLIST.append('CASTED_GLOBAL_HASH_%s' % sym_name, pte_struct)
                elem = elem["next"]

        self.GLOBAL_CONTAINERS.add(s)
        logging.debug(s)

    def load_global_hashtables(self):
        logging.debug("Loading global hashtables:\n%s" % GLOBAL_HASHTABLES)

        for sym_name, (size, pte_type, pte_field_name, filename)  in GLOBAL_HASHTABLES.items():
            sym = self.load_symbol(sym_name, filename)
            if sym is not None:
                self.load_global_hashtable(sym, sym_name, size, pte_type, pte_field_name, filename)
