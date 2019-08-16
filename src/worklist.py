from utils import *
import logging
from mytypes import *


class Worklist:

    def __init__(self):
        # It contains triplets (name, value, global_root).
        self.worklist = []

        # shadow_worklist contains pairs of (type, struct_addr)
        # and is used to check if a struct was already visited or not.
        self.shadow_worklist = set()

    # Takes a Work object as input.  Depending on value type (struct
    # pointer, struct) it appends new work to the worklist.
    def append(self, name, value, global_root=False):
        t = value.type

        if is_void_pointer(t) or is_pointer_of_pointer(t):
            logging.debug("void * or ptr of ptr detected %s %s" % (t, name))
            return 0

        if is_struct_pointer(t) and is_dereferenceable(value):
            addr = gdb_value_to_int(value)
            ty = str(strip_typedefs_until_named(t.target()))
            value = dereference(value)

        elif is_struct(t) and is_fetchable(value):
            addr = gdb_value_to_int(value.address)
            ty = str(strip_typedefs_until_named(t))

        else:
            return 0

        if (not global_root) and (addr == 0x0 or (ty, addr) in self.shadow_worklist):
            logging.debug("Not appending..")
            return 0

        logging.debug("Appending 0x%016x : '%s' %s %s" % (addr, ty, name,
                                                          "GLOBAL" if global_root else ""))
        self.worklist.append((name, value, global_root))
        self.shadow_worklist.add((ty, addr))
        return 1
