from utils import *
import logging
from enum import Enum, IntEnum
import pickle

# TODO: to handle PTR_ARRAY_OF_PTR we should create a Struct containing an array field.

class Node(Enum):
    # i.e task_struct.children
    ROOT = 0
    # Intermediate nodes are those nodes which are pointed by a root node, i.e. task_struct.siblings
    INTER = 1
    # i.e. task_struct.tasks
    NORM = 2

a = -1
def auto():
    global a
    a+=1
    return 2**a

class FieldAttr(IntEnum):
    NODEREF = auto()

    PTR = auto()
    PTR_NODEREF = PTR | NODEREF

    STRUCT = auto()

    STRUCT_PTR = auto() | PTR
    STRUCT_PTR_NODEREF = STRUCT_PTR | NODEREF

    CHAR_PTR = auto() | PTR
    CHAR_PTR_NODEREF = CHAR_PTR | NODEREF

    VOID_PTR = auto()
    VOID_PTR_NODEREF = VOID_PTR | NODEREF

    FUNC_PTR = auto() | PTR
    FUNC_PTR_NODEREF = FUNC_PTR | NODEREF

    PTR_OF_PTR = auto() | PTR
    PTR_OF_PTR_NODEREF = auto() | NODEREF

    ARRAY = auto()
    ARRAY_OF_STRUCT = auto() | ARRAY
    ARRAY_OF_STRUCT_PTR = auto() | ARRAY
    ARRAY_OF_CHAR = auto()
    ARRAY_OF_CHAR_PTR = auto() | ARRAY

    PTR_ARRAY_OF_PTR = auto() | ARRAY
    STRUCT_PTR_PERCPU = auto() | ARRAY
    STRUCT_PTR_PERCPU_NODEREF = auto() | NODEREF

    OTHER = auto()

# The pte_type is useful to disambiguate where this fields points.
# Eg:
#
# struct A{
#   struct B{
#   }
# }
# # typedef struct B B_t
# struct C{
#   B_t * d;
# }
# When building the graph, we need to know that d is pointing to the
# struct B vertex and not to the struct A one (those struct are at the
# same address).

class Field:

    def __init__(self, name, v, address=0, debug=False):
        self.attr = Field.get_field_attr(v.type, v)
        if address != 0:
            self.addr = address
        else:
            self.addr = gdb_value_to_int(v.address)

        ts = strip_typedefs_until_named(v.type)
        self.ty = str(ts)
        self.name = name
        self.array_elements = []
        self.s = ""
        self.pte_type = str(resolve_type_ptr(v.type, named=True))
        self.size = int(v.type.sizeof)

        if (self.is_array_of_char_ptr()):
            _, upper = strip_typedefs_fast(v.type).range()
            self.s = []
            for i in range(0, upper+1):
                self.array_elements.append(gdb_value_to_int(v[i]))
                self.s.append(gdb_value_to_c_string(v[i]))

        elif (self.is_char_ptr() or self.is_array_of_char()):
            self.s = gdb_value_to_c_string(v)

        if (self.is_ptr() or ts.code == gdb.TYPE_CODE_INT):
            self.value = gdb_value_to_int(v)
        else:
            self.value = ""
            #     self.value = gdb_value_to_str(v).encode('utf-8')

        if debug:
            logging.debug("Creating %s" % self)

    def __repr__(self):
        r = "Field : [{}] 0x{:016x} {} {} ".format(self.attr.name, self.addr, self.ty, self.name)
        if self.is_ptr_array_of_ptr() or self.is_percpu():
            r += '%s ' % hex(self.value)

        if self.is_array():
            r += '[%s]' % ', '.join(hex(x) for x in self.array_elements)
        elif self.is_ptr():
            r += "0x%016x" % self.value

        if self.is_char_ptr() or self.is_array_of_char():
            r += " '%s'" % self.s
        elif self.is_array_of_char_ptr():
            r += '[%s]' % ', '.join(s for s in self.s)
        elif self.is_other():
            r += "%s" % (self.value)

        return r

    @staticmethod
    def get_field_attr(t, v):
        if is_array_of_struct(t):
            return FieldAttr.ARRAY_OF_STRUCT

        if is_array_of_struct_pointer(t):
            return FieldAttr.ARRAY_OF_STRUCT_PTR

        if is_array_of_char(t):
            return FieldAttr.ARRAY_OF_CHAR

        if is_array_of_char_pointer(t):
            return FieldAttr.ARRAY_OF_CHAR_PTR

        if is_struct(t):
            return FieldAttr.STRUCT

        if is_function_pointer(t):
            is_deref = is_dereferenceable(v)
            if is_deref:
                return FieldAttr.FUNC_PTR
            else:
                return FieldAttr.FUNC_PTR_NODEREF

        if is_pointer_of_pointer(t):
            is_deref = is_dereferenceable(v)
            if is_deref:
                return FieldAttr.PTR_OF_PTR
            else:
                return FieldAttr.PTR_OF_PTR_NODEREF

        if is_struct_pointer(t):
            is_deref = is_dereferenceable(v)
            if is_deref:
                return FieldAttr.STRUCT_PTR
            else:
                return FieldAttr.STRUCT_PTR_NODEREF

        if is_void_pointer(t):
            if is_dereferenceable_void(v):
                return FieldAttr.VOID_PTR
            else:
                return FieldAttr.VOID_PTR_NODEREF

        if is_char_pointer(t):
            is_deref = is_dereferenceable(v)
            if is_deref:
                return FieldAttr.CHAR_PTR
            else:
                return FieldAttr.CHAR_PTR_NODEREF

        if is_pointer(t):
            is_deref = is_dereferenceable(v)
            if is_deref:
                return FieldAttr.PTR
            else:
                return FieldAttr.PTR_NODEREF

        return FieldAttr.OTHER

    def set_percpu(self):
        if self.value == 0:
            self.attr = FieldAttr.STRUCT_PTR_PERCPU_NODEREF
        else:
            self.attr = FieldAttr.STRUCT_PTR_PERCPU

    def set_ptr_array_of_ptr(self, value):
        self.attr = FieldAttr.PTR_ARRAY_OF_PTR

    def is_ptr_array_of_ptr(self):
        return bool(self.attr == FieldAttr.STRUCT_PTR_PERCPU or
                    self.attr == FieldAttr.PTR_ARRAY_OF_PTR)

    def add_percpu_ptr(self, e):
        assert(self.attr == FieldAttr.STRUCT_PTR_PERCPU)
        self.array_elements.append(e)

    def add_array_element(self, e, check=True):
        if check:
            assert(self.is_array_of_struct() or
                   self.is_array_of_struct_ptr() or
                   self.is_ptr_array_of_ptr() or
                   self.is_percpu())

        if not isinstance(e, int):
            e = gdb_value_to_int(e)

        self.array_elements.append(e)

    def get_array_name_index(self, i):
        return "%s[%d]" % (self.name, i)

    def get_array_elements(self):
        for i, e in enumerate(self.array_elements):
            yield self.get_array_name_index(i), e

    def is_struct(self):
        return bool(self.attr == FieldAttr.STRUCT)

    def is_other(self):
        return bool(self.attr == FieldAttr.OTHER)

    def is_percpu(self):
        return bool(self.attr == FieldAttr.STRUCT_PTR_PERCPU or
                    self.attr == FieldAttr.STRUCT_PTR_PERCPU_NODEREF)

    def is_deref(self):
        return bool((self.attr & FieldAttr.PTR or self.is_ptr_array_of_ptr()) and
                    not(self.attr & FieldAttr.NODEREF))

    def is_ptr(self):
        return bool(self.attr & FieldAttr.PTR)

    def is_array(self):
        return bool(self.attr & FieldAttr.ARRAY)

    def is_char_ptr(self):
        return bool(self.attr == FieldAttr.CHAR_PTR or
                    self.attr == FieldAttr.CHAR_PTR_NODEREF)

    def is_void_ptr(self):
        return bool(self.attr == FieldAttr.VOID_PTR or
                    self.attr == FieldAttr.VOID_PTR_NODEREF)

    def is_funct_ptr(self):
        return bool(self.attr == FieldAttr.FUNC_PTR or self.attr == FieldAttr.FUNC_PTR_NODEREF)

    def is_ptr_ptr(self):
        return bool(self.attr == FieldAttr.PTR_OF_PTR or self.attr == FieldAttr.PTR_OF_PTR_NODEREF)

    def is_struct_ptr(self):
        return bool(self.attr == FieldAttr.STRUCT_PTR or self.attr == FieldAttr.STRUCT_PTR_NODEREF)

    def is_array_of_struct(self):
        return self.attr == FieldAttr.ARRAY_OF_STRUCT

    def is_array_of_struct_ptr(self):
        return self.attr == FieldAttr.ARRAY_OF_STRUCT_PTR

    def is_array_of_char(self):
        return self.attr == FieldAttr.ARRAY_OF_CHAR

    def is_array_of_char_ptr(self):
        return self.attr == FieldAttr.ARRAY_OF_CHAR_PTR

    def might_infer_ptr(self):
        return self.is_other() and type(self.value) == int and self.value > 0xffff800000000000


class Struct:

    def __init__(self, addr, ty, name, global_root=False, global_container=False):
        if isinstance(addr, int):
            self.addr = addr
        else:
            self.addr = gdb_value_to_int(addr)

        self.ty = str(strip_typedefs_until_named(ty))
        self.name = name
        self.filename = get_decl_file(ty)
        self.size = int(ty.sizeof)
        self.fields = list()
        self.global_root = global_root
        self.global_container = global_container

    def addField(self, name, value):
        f = Field(name, value)
        self.fields.append(f)
        return f

    def is_global_root(self):
        return self.global_root

    def is_global_container(self):
        return self.global_container

    def is_global(self):
        return self.global_root or self.global_container

    def __getitem__(self, name):
        assert(type(name) == str)
        for x in self.fields:
            if x.name == name:
                return x
        return None

    def __contains__(self, name):
        return self.__getitem__(name) is not None

    def __repr__(self):
        g = ""
        if self.global_root:
            g = "GLOBAL ROOT"
        elif self.global_container:
            g = "GLOBAL CONTAINER"
        r = "Struct : 0x%016x %s %s (%s) (size: %s) %s\n" % ((self.addr, self.ty,
                                                              self.name, self.filename, self.size, g))
        for i in self.fields:
            r += "%s\n" % i
        r = r[:-1]
        r += "\n"
        return r

    def __eq__(self, other):
        return (self.addr == other.addr) and (self.ty == other.ty)

    def __lt__(self, other):
        return (self.addr <= other.addr)

    def __hash__(self):
        return hash(str(self.addr) + self.ty)

    def __iter__(self):
        for i in self.fields:
            yield i


class Sample:
    def __init__(self, path):
        self.sample_file = open(path, 'wb+')
        self.counter = 0

    def dump_struct(self, struct):
        pickle.dump(struct, self.sample_file)
        self.counter += 1

    @staticmethod
    def load(path):
        structs = set()
        f = open(path, "rb")
        while True:
            try:
                s = pickle.load(f, encoding='utf-8')
                structs.add(s)
            except EOFError:
                break
        return structs

    def __del__(self):
        self.sample_file.close()
