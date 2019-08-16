from mytypes import *
from utils import *

# node_info is a dictionary where:
# keys are ('struct_type','field_name')
# items are the type of node (ROOT, INTERMEDIATE, NORMAL)

# TODO: get this information automatically from the clang plugin
RB_INFO = {("struct mm_struct", "mm_rb"): ("struct vm_area_struct", "vm_rb"),
           ("struct anon_vma", "rb_root"): ("struct anon_vma_chain", "rb"),
           ("struct ctl_dir", "root"): ("struct ctl_node", "node"),
           ("struct timerqueue_head", "head"): ("struct timerqueue_node", "node"),
           ("struct address_space", "i_mmap"): ("struct vm_area_struct", "shared"),
           # Node is inside an union, check this..
           ("struct eventpoll", "rbr"): ("struct epitem", "rbn"),
           ("struct proc_dir_entry", "subdir"): ("struct proc_dir_entry", "subdir_node"),
           ("struct cfs_rq", "tasks_timeline"): ("struct sched_entity", "run_node")}
                
class Explorer():
    def __init__(self,  node_info, pointer_info, global_structs_addr):
        self.node_info = node_info
        self.pointer_info = pointer_info
        self.global_structs_addr = global_structs_addr
        self.per_cpu_offsets = gdb.lookup_symbol("__per_cpu_offset")[0].value()

        for k, v in RB_INFO.items():
            assert(k not in self.pointer_info)
            self.pointer_info[k] = v
            
    def handle(self, struct_type, field_name, value, array_index):
        works = []

        if str(value.type) == "struct list_head":
            works = self.handle_list_head(struct_type, field_name, value,
                                          array_index=array_index)
        elif str(value.type) == "struct hlist_head":
            works = self.handle_hlist_head(struct_type, field_name, value)
        elif str(value.type) == "struct rb_root":
            works = self.handle_rb_tree(struct_type, field_name, value)
        elif str(value.type) == "struct rb_root_cached":
            works = self.handle_rb_tree(struct_type, field_name, value, True)
            
        if works:
            return works
        else:
            return []

    def handle_percpu_field(self, field, field_name):
        for i in range(NR_CPUS):
            offset = self.per_cpu_offsets[i]
            field_type = field.type
            long_type = gdb.lookup_type("u64")
            try:
                field_value = field.cast(long_type)
            except gdb.MemoryError:
                field_value = int(field.address) # Global percpu

            translated = (offset.cast(long_type) + field_value).cast(field_type)
            yield gdb_value_to_int(offset), "PERCPU_%d_%s" % (i, field_name), translated
        
    def handle_rb_tree(self, struct_type, field_name, field, is_rb_cached=False):
        if is_rb_cached:
            field = field["rb_root"]
            
        if gdb_value_to_int(field["rb_node"]) == 0:
            logging.debug("rb_node is zero, tree is empty")
            return

        pointee_struct_type, pointee_field_name = self.get_pointer_info(struct_type, field_name)
        if pointee_struct_type is None:
            return

        logging.debug("Walking a tree rooted at %s.%s which contains %s" % (struct_type, field_name, pointee_struct_type))
        
        nodes = [field["rb_node"]]
        struct_type_ptr = pointee_struct_type.pointer()
        for rb_node_ptr in nodes:

            pte_struct = container_of(rb_node_ptr, struct_type_ptr, pointee_field_name).dereference()
            wname = "RB_NODE_%s.%s" % (pointee_struct_type, pointee_field_name)
            yield wname, pte_struct

            for i in ["rb_right", "rb_left"]:
                rb_node = rb_node_ptr[i]
                if not is_fetchable(rb_node):
                    logging.error("Cannot fetch RB_NODE %s" % i)
                    continue

                rb_node_addr = gdb_value_to_int(rb_node.address)

                if rb_node and rb_node not in nodes:
                    logging.debug("Found a good %s" % i)
                    nodes.append(rb_node)

    def handle_global_head(self, name, struct_type, field_name):
        sym = gdb.lookup_symbol(name)[0] or gdb.lookup_global_symbol(name)
        value = sym.value()

        if is_array(sym.type):
            values = [v for _, v in walk_array(name, value)]
        else:
            values = [value]

        for v in values:
            if (is_pointer(v.type) and not is_dereferenceable(v)) or not is_valid_list_head(v):
                logging.error("invalid list_head * symbol %s" % name)
                continue
            if is_empty_list(v):
                continue

            head = gdb_value_to_int(v.address)
            n = v["next"]
            for w in self.explore_list(struct_type, field_name, head, n):
                yield w

    def check_node_info(self, t, n):
        if (t, n) in self.node_info:
            return True
        else:
            logging.error("[MISSING_INFO] Missing node info for %s.%s" % (t, n))
            return False

    def get_pointer_info(self, t, n):
        try:
            t, n = self.pointer_info[(t, n)]
            return gdb.lookup_type(t), n
        except KeyError:
            logging.error("[MISSING_INFO] Missing pointer info for %s.%s" % (t, n))
            return None, None
            
    def handle_hlist_head(self, struct_type, field_name, field):
        if is_empty_hlist(field):
            logging.debug("first or first->next is 0, list is empty")
            return

        if not self.check_node_info(struct_type, field_name):
            return

        assert(self.node_info[(struct_type, field_name)] == Node.ROOT)
        return self.explore_list(struct_type, field_name, 0, field['first'])

    def handle_list_head(self, struct_type, field_name, field, array_index=-1):
        if is_empty_list(field) or is_zero_list(field):
            logging.debug("list is empty or zero ")
            return

        if not self.check_node_info(struct_type, field_name):
            return
        
        node = self.node_info[(struct_type, field_name)]
        head = gdb_value_to_int(field.address)
        
        if node == Node.ROOT:
            return self.explore_list(struct_type, field_name, head,
                                     field["next"], array_index=array_index)
        if node == Node.NORM:
            return self.explore_list(struct_type, field_name, head,
                                     field["next"], one_step = True, array_index = array_index)
        
        logging.debug("Node.INTER, not walking.")

    def explore_list(self, struct_type, field_name, head, gdb_next,  array_index = -1, one_step = False):

        logging.debug("Exploring list from root: [0x%16x] %s.%s (i=%d)" %
                      (head, struct_type, field_name, array_index))
            
        if gdb_value_to_int(gdb_next) in self.global_structs_addr:
            logging.debug("Next points to a global structure, aborting here ")
            return
        
        visited = set([head])

        while(head != gdb_value_to_int(gdb_next)):

            struct_name = "casted_from_%s.%s" % (struct_type, field_name)            
            struct_type, field_name = self.get_pointer_info(str(struct_type), field_name)
            
            offset = find_offset(struct_type, field_name, array_index = array_index)
            
            if offset < 0:
                logging.error("[-] Field not found: %s %s" % (struct_type, field_name))
                return

            logging.debug("-> container_of gdb_next = 0x%016x offset = %d" %
                          (gdb_value_to_int(gdb_next), offset))
            
            pte_struct = custom_container_of(gdb_next, struct_type.pointer(), offset).dereference()

            logging.debug("Cast 0x%016x: '%s' '%s'" % (gdb_value_to_int(pte_struct.address),
                                                       struct_type, struct_name))
            yield struct_name, pte_struct

            if one_step:
                return

            field = pte_struct[field_name]

            if array_index >= 0 and is_array(field.type):
                gdb_next = field[array_index]["next"]
            else:
                gdb_next = field["next"]

            if not is_fetchable(gdb_next):
                logging.error("Cannot fetch next %s.%s.." % (str(pte_struct.type), field_name))
                return

            next_addr = gdb_value_to_int(gdb_next.address)
            if next_addr in visited: # LOOP ?
                return

            visited.add(next_addr)
