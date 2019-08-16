try:
    import gdb
    basic_types = set([gdb.TYPE_CODE_INT, gdb.TYPE_CODE_FLT, gdb.TYPE_CODE_VOID, gdb.TYPE_CODE_CHAR])
except:
    pass

import ctypes
import logging
from enum import Enum
import re
from elftools.elf.elffile import ELFFile
import logging

NR_CPUS=4

def is_void(t):
    t = strip_typedefs_fast(t)
    return t.code == gdb.TYPE_CODE_VOID

def is_union(t):
    t = strip_typedefs_fast(t)
    return t.code == gdb.TYPE_CODE_UNION

def is_int(t):
    t = strip_typedefs_fast(t)
    return t.code == gdb.TYPE_CODE_INT

def is_void_pointer(t):
    t = strip_typedefs_fast(t)
    return t.code == gdb.TYPE_CODE_PTR and is_void(t.target())

def is_pointer(t):
    t = strip_typedefs_fast(t)
    return t.code == gdb.TYPE_CODE_PTR

def is_pointer_of_pointer(t):
    t = strip_typedefs_fast(t)
    if t.code == gdb.TYPE_CODE_PTR:
        t2 = strip_typedefs_fast(t.target())
        if t2.code == gdb.TYPE_CODE_PTR:
            return True
    return False

def is_array(t):
    t = strip_typedefs_fast(t)
    return t.code == gdb.TYPE_CODE_ARRAY

def is_struct(t):
    t = strip_typedefs_fast(t)
    return t.code == gdb.TYPE_CODE_STRUCT

def is_union(t):
    t = strip_typedefs_fast(t)
    return t.code == gdb.TYPE_CODE_UNION

def is_function(t):
    t = strip_typedefs_fast(t)
    return t.code == gdb.TYPE_CODE_FUNC

def is_char(t):
    t = strip_typedefs_fast(t)
    return "char" in str(t) and not is_pointer(t)

def is_array_of_char(t):
    t = strip_typedefs_fast(t)
    return is_array(t) and is_char(t.target())

def is_array_of_char_pointer(t):
    t = strip_typedefs_fast(t)
    return is_array(t) and is_char_pointer(t.target())

def is_char_pointer(t):
    t = strip_typedefs_fast(t)
    return is_pointer(t) and is_char(t.target())

def is_struct_pointer(t):
    t = strip_typedefs_fast(t)
    return is_pointer(t) and is_struct(t.target())

def is_function_pointer(t):
    t = strip_typedefs_fast(t)
    return is_pointer(t) and is_function(t.target())

def is_type_size_zero(t):
    t = strip_typedefs_fast(t)
    return t.sizeof == 0

def is_array_of_struct_pointer(t):
    t = strip_typedefs_fast(t)
    return is_array(t) and is_struct_pointer(t.target())

def is_array_of_struct(t):
    t = strip_typedefs_fast(t)
    return is_array(t) and is_struct(t.target())

# Derefs as long as the dereference return a ptr.
def resolve_type_ptr(t, named=False):
    if named:
        t = strip_typedefs_until_named(t)
    else:
        t = strip_typedefs_fast(t)

    while t.code == gdb.TYPE_CODE_PTR or t.code == gdb.TYPE_CODE_ARRAY:
        if named:
            t = strip_typedefs_until_named(t.target())
        else:
            t = strip_typedefs_fast(t.target())
    return t

def dereference(v):
    try:
        d = v.dereference()
        d.fetch_lazy()
    except gdb.MemoryError:
        return None
    return d

# gdb.dereference is slow, so we keep a cache of valid pages.
dereferenceable_cache = set()
not_dereferenceable_cache = set()
def is_dereferenceable(value):
    if value == None:
        return False

    if not is_pointer(value.type):
        return False

    page = gdb_value_to_int(value) & ~0xfff
    if page == 0:
        return False

    if page in dereferenceable_cache:
        return True
    if page in not_dereferenceable_cache:
        return False

    if is_void_pointer(value.type):
        is_deref = is_dereferenceable_void(value)
    else:
        is_deref = dereference(value) != None

    if is_deref:
        dereferenceable_cache.add(page)
    else:
        not_dereferenceable_cache.add(page)

    return is_deref

def is_dereferenceable_void(value):
    charptr_type = gdb.lookup_type("char").pointer()
    try:
        v = value.cast(charptr_type).dereference()
        v.fetch_lazy()
    except Exception as err:
        return False
    return True

def is_fetchable(value):
    try:
        value.fetch_lazy()
    except Exception as err:
        logging.debug('is_fetchable: %s %s ' % (value.type, err))
        return False
    return True

def gdb_value_to_c_string(v):
    try:
        return v.string('utf-8', errors='ignore')
    except (gdb.MemoryError, gdb.error):
        return ''

long_type = None

def gdb_value_to_int(addr):
    global long_type
    if long_type is None:
        long_type = gdb.lookup_type("u64")
    try:
        return ctypes.c_uint64(addr.cast(long_type)).value
    except gdb.MemoryError:
        return -1

def gdb_value_to_str(value):
    try:
        return '%s' % value
    except gdb.MemoryError:
        return "INVALID (gdb.MemoryError)"

def find_offset(t, name, offset=0, array_index=-1):
    for n, f in t.items():
        # print("checking ", n, f, f.type, array_index, (offset+f.bitpos)/8)
        if n == name:
            if array_index != -1 and is_array(f.type):
                target = f.type.target().sizeof
                return int((offset+f.bitpos/8)+(target*array_index))
            else:
                return int((offset+f.bitpos)/8)

        if is_struct(f.type) or is_union(f.type):
            o = find_offset(f.type, name, offset=offset+f.bitpos)
            if o >= 0:
                return o

    return -1

def deep_iter_items(v):
    for n, f in v.type.items():
        field_value = v[f]

        if is_struct(field_value.type):
            for i in deep_iter_items(field_value):
                yield i

        elif is_array(field_value.type) and not is_type_size_zero(resolve_type_ptr(field_value.type)):
            _, upper = strip_typedefs_fast(field_value.type).range()
            for j in range(0, upper+1):
                if is_struct(field_value[j].type):
                    for i in deep_iter_items(field_value[j]):
                        yield i

        else:
            yield v, n, field_value

def deep_items_anon(v, prev_n=None, prev_f=None):
    for n, f in v.type.items():
        # logging.debug("deep items anon %s %s %s" % (v.type, n,f))
        field_value = v[f]
        t = field_value.type

        # If this field is a union, contained in a struct with only one
        # field (the union itself), we return the struct.
        # This hack was done to preserve spinlock_t.
        if is_union(t) and len(v.type.items()) == 1 and prev_f is not None:
            yield prev_n, prev_f
            return

        # If this field is an anonymous and unnamed structure, we traverse it.
        if is_struct(t) and t.tag is None and str(t) == "struct {...}":
            for i in deep_items_anon(field_value, n, field_value):
                yield i
        else:
            yield n, field_value

def walk_array(name, array):
    if str(resolve_type_ptr(array.type)) == "struct idr_layer":
        return

    _, upper = strip_typedefs_fast(array.type).range()
    logging.debug("[+] Walking array '%s' with length: %d" % (name, upper + 1))

    for i in range(upper+1):
        value = array[i]
        if is_array_of_struct(value.type) or is_array_of_struct_pointer(value.type):
            for k in walk_array("%s[%d]" % (name, i), value):
                yield k
        yield ("%s[%d]" % (name, i), value)

decl_file_cache = {}

def get_decl_file(t):
    stype = str(t).split(" ")[-1]
    try:
        return decl_file_cache[stype]
    except KeyError:
        pass

    filename = ""
    for d in [gdb.SYMBOL_STRUCT_DOMAIN, gdb.SYMBOL_VAR_DOMAIN]:
        symbol = gdb.lookup_symbol(stype, domain=d)[0]
        if symbol:
            filename = symbol.symtab.filename

    decl_file_cache[stype] = filename
    return filename

def strip_typedefs_fast(t):
    if t.code in basic_types:
        return t

    while(t.code == gdb.TYPE_CODE_TYPEDEF):
        t = t.strip_typedefs()

    return t.unqualified()

def strip_typedefs_until_named(t):
    if t.code in basic_types:
        return t

    prevt = t
    while t.code == gdb.TYPE_CODE_TYPEDEF:
        t = t.strip_typedefs()
        if str(t) == "struct {...}" or str(t) == "union {...}":
            break
        prevt = t

    return prevt.unqualified()

PERCPU_FIELDS = [("struct mount", "mnt_pcp"), ("struct kmem_cache", "cpu_slab"),
                 ("struct workqueue_struct", "cpu_pwqs"), ("struct hd_struct", "dkstats"),
                 ("struct zone", "pageset"), ("struct ipv6_devstat", "ipv6"),
                 ("struct pglist_data", "per_cpu_nodestats"), ("struct rcu_state", "rda"),
                 ("struct srcu_struct", "per_cpu_ref"), ("struct netns_core", "inuse"),
                 ("struct netns_ct", "pcpu_lists"), ("struct netns_ct", "stat"),
                 ("struct flow_cache", "percpu"), ("struct neigh_table", "stats"),
                 ("struct srcu_struct", "per_cpu_ref"), ("struct netns_mib", "tcp_statistics"),
                 ("struct netns_mib", "ip_statistics"), ("struct netns_mib", "net_statistics"),
                 ("struct netns_mib", "udp_statistics"), ("struct netns_mib", "udplite_statistics"),
                 ("struct netns_mib", "icmp_statistics"), ("struct netns_mib", "udplite_statistics"),
                 ("struct netns_mib", "udp_stats_in6"), ("struct netns_mib", "udplite_stats_in6"),
                 ("struct netns_mib", "ipv6_statistics"), ("struct netns_mib", "icmpv6_statistics"),
                 ("struct trace_buffer", "data"), ("struct kmem_cache", "cpu_cache"),
                 ("struct pmu","pmu_cpu_context")]

GLOBAL_HASHTABLES = {"pid_hash": (4096, "struct upid", "pid_chain", ""),
                     "mm_slots_hash": (1024, "struct mm_slot", "hash", "mm/khugepaged.c:72"),
                     "unix_socket_table": (512, "struct sock_common", "skc_node", ""),
                     "mountpoint_hashtable": (4096, "struct mountpoint", "m_hash", ""),
                     "mount_hashtable": (4096, "struct mount", "mnt_hash", ""),
                     "inode_hashtable": (131072, "struct inode", "i_hash", ""),
                     "dentry_hashtable": (262143, "struct dentry", "d_hash", ""),
                     "posix_timers_hashtable":(512, "struct k_itimer", "t_hash", ""),
                     "unbound_pool_hash":(64, "struct worker_pool", "hash_node",""),
}

PTR_OF_PTR_FIELDS = {("struct fdtable", "fd"): (0, "max_fds"),
                     ("struct neigh_hash_table", "hash_buckets"): (1, "hash_shift"),
                     ("struct tty_driver", "ttys"): (0, "num"),
                     ("struct neigh_table","phash_buckets"): (2, 0xf),
                     ("struct task_group", "se"): (2, NR_CPUS),
                     ("struct task_group", "cfs_rq"): (2, NR_CPUS)
}

def is_percpu_field(s, f):
    return (s.ty, f.name) in PERCPU_FIELDS

def is_ptr_of_ptr_field(s, f):
    return (s.ty, f.name) in PERCPU_FIELDS

def cast_ptr_of_ptr(s, f, struct, field):
    size = get_ptr_of_ptr_size(s, f, struct)
    t = field.type.target().array(size - 1)
    logging.debug("[+] Manually casting PTR_OF_PTR: %s" % t)
    return field.dereference().cast(t)

def get_ptr_of_ptr_size(s, f, struct):
    size_type, size_field = PTR_OF_PTR_FIELDS[(s.ty, f.name)]

    if size_type == 2:
        return size_field
    elif size_type == 1:
        return 1 << gdb_value_to_int(struct[size_field])
    elif size_type == 0:
        return gdb_value_to_int(struct[size_field])

def is_valid_struct(gdb_struct):
    # For now we don't explore radix_tree_node, because it only adds a
    # lot of list_head.
    if str(gdb_struct.type) == "struct radix_tree_node":
        return False

    if is_type_size_zero(gdb_struct.type):
        logging.debug("struct.type has size 0, invalid")
        return False

    if is_struct(gdb_struct.type) and not is_fetchable(gdb_struct):
        return False

    score = 0
    for struct, name, field in deep_iter_items(gdb_struct):  # Loop on the fields of the struct
        struct_type = str(strip_typedefs_until_named(struct.type))

        if struct_type == "struct sigaction" and (name == "sa_restorer" or name == "sa_handler"):
            c = gdb_value_to_int(field)
            if 0x0 <= c <= 0x7fffffffffff: # Points in userspace
                score+=1
            else:
                score-=1

        elif is_function_pointer(field.type) and struct_type != "struct callback_head":
            c = gdb_value_to_int(field)
            if not (points_inside_text_section(c) or points_inside_module_area(c)) :
                logging.debug("Found an invalid function pointer: 0x%016x" % c)
                return False

        elif struct_type == "struct spinlock":
            c = field["rlock"]["raw_lock"]["val"]["counter"]
            if c > 100 or c < 0:
                logging.debug("Found a corrupted spinlock with value: %d" % c)
                return False

        elif struct_type == "struct list_head":
            if not is_valid_list_head(struct):
                logging.debug("Found a corrupted list_head: invalid struct")
                return False
            score += 1                

        elif (str(struct.type), name) in PERCPU_FIELDS:
            if (gdb_value_to_int(field)) < 0x80000:
                score += 1
            else:
                score -= 1

        elif is_pointer(field.type):
            c = gdb_value_to_int(field)
            if (c != 0 and
                ((is_struct_pointer(field.type) or is_char_pointer(field.type)) and points_inside_text_section(c))):
                logging.debug("Field %s.%s points inside text section" % (field.type, name))
                return False

            if c == 0 or is_dereferenceable(field):
                score += 1
            else:
                score -= 1

    return score >= 0

def is_valid_list_head(struct):
    try:
        n = gdb_value_to_int(struct["next"])
        p = gdb_value_to_int(struct["prev"])
    except gdb.error:
        return False

    if is_zero_list(struct) or (n == 0x1ffffffff) or (n >> 48) == 0xdead or (p >> 48) == 0xdead:
        return True

    return is_dereferenceable(struct["next"]) and is_dereferenceable(struct["prev"])

def is_empty_hlist(v):
    first = gdb_value_to_int(v["first"])
    if first == 0:
        return True
    # WHYYY?
    return gdb_value_to_int(v['first']['next']) == 0

def is_empty_list(v):
    vnext = gdb_value_to_int(v["next"])
    return gdb_value_to_int(v.address) == vnext

def is_zero_list(v):
    vnext = gdb_value_to_int(v["next"])
    vprev = gdb_value_to_int(v["prev"])
    return vnext == vprev == 0

def is_singular_list(v):
    vnext = gdb_value_to_int(v["next"])
    vprev = gdb_value_to_int(v["prev"])
    return vnext == vprev

def points_inside_module_area(c):
    return (c == 0 or 0xffffffffa0000000 <= c <= 0xfffffffffeffffff) # modules area

executable_sections = set()

def load_executable_sections(KDIR):
    elffile = ELFFile(open("%s/vmlinux" % KDIR, "rb"))
    for s in elffile.iter_sections():
        if s.header['sh_flags'] == 6:
            start = s.header['sh_addr']
            size = s.header['sh_size']
            executable_sections.add((start, start+size))
            logging.debug("Adding executable sections: %s %x %x" % (s.name, start, size))

def points_inside_text_section(c):
    return c == 0 or any(s <= c <= e for (s,e) in executable_sections)

def lookup_type(ty, filename):
    symtab = get_symtab(filename)
    if symtab:
        block = symtab.global_block()
        struct_type_ptr = gdb.lookup_type(ty, block=block).pointer()
    else:
        struct_type_ptr = gdb.lookup_type(ty).pointer()
    return struct_type_ptr

symtab_cache = {}
def get_symtab(filename):
    if filename == "":
        return None

    if filename in symtab_cache:
        return symtab_cache[filename]

    try:
        sal = gdb.decode_line(filename)[1][0]
    except gdb.error:
        symtab_cache[filename] = None
        return None

    symtab = sal.symtab
    symtab_cache[filename] = symtab
    return symtab

# Taken from kernel linux/utils.py
def offset_of(typeobj, field):
    element = gdb.Value(0).cast(typeobj)
    return int(str(element[field].address).split()[0], 16)

# Taken from kernel linux/utils.py
def container_of(ptr, typeobj, member):
    global long_type
    if long_type is None:
        long_type = gdb.lookup_type("u64")
    return (ptr.cast(long_type) -
            offset_of(typeobj, member)).cast(typeobj)

def custom_container_of(ptr, typeobj, offset):
    global long_type
    if long_type is None:
        long_type = gdb.lookup_type("u64")

    return (ptr.cast(long_type) - offset).cast(typeobj)
