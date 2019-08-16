import functools
import itertools
from collections import defaultdict
import time
import sys
import logging

##################################################################################
# This RAM contains the outer struct at every inner struct address.
# In this way we create a node only for the outer struct, and every
# other struct which points inside the outer will have an edge towards the outer.
##################################################################################

def is_contained(s2, s1):
    for f in s1:
        if f.is_array_of_struct() and f.pte_type == s2.ty and s2.addr in f.array_elements:
            return True

        if f.is_struct() and f.addr == s2.addr and f.ty == s2.ty:
            return True

        if f.pte_type == 'union {...}' and (f.addr <= s2.addr <= (f.addr + f.size)):
            return True
                                    
    return False

def sort_struct(s1, s2):
    if s1.addr < s2.addr:
        return -1
    if s1.addr > s2.addr:
        return 1

    # So they start from the same address..
    if s1.size > s2.size:
        return -1

    if s2.size > s1.size:
        return 1
    
    # .. and they have the same size
    
    a = s1.fields[0].is_struct()
    b = s2.fields[0].is_struct()
    
    if a == True and b == False:
        return -1
    if a == False and b == True:
        return 1

    # .. and both the first field are structures
    
    a = s1.fields[0].is_array_of_struct()
    b = s2.fields[0].is_array_of_struct()

    if a == True and b == False:
        return -1
    if a == False and b == True:
        return 1

    # ..and none of them is an array of structures
    if s2.ty == s1.fields[0].ty:
        return -1
    
    if s1.ty == s2.fields[0].ty:
        return 1
    
    # .. and their are not inner structures? Glitch!
    
    return 1
    
def delete_structs(RAM, sample, structs):
    for s in structs:
        logging.debug("Deleting: %s" % s)
            
    for addr in RAM.keys():
        RAM[addr] = [s for s in RAM[addr] if s not in structs]

    for addr in list(RAM.keys()):
        if (len(RAM[addr]) == 0) or (len(RAM[addr]) == 1 and RAM[addr][0].addr != addr):
            del RAM[addr]
            
    for i in reversed(range(len(sample))):
        if sample[i] in structs:
            del sample[i]
        
structs_cache = {}
def find_struct_iter(sample, addr, ty):
    if len(structs_cache):
        return structs_cache.get((addr, ty), None)
    
    for s in sample:
        structs_cache[(s.addr, s.ty)] = s

    return structs_cache.get((addr, ty), None)

def count_valid_struct_ptr(sample, s):
    count = 0
    for f in s:
        if f.is_struct_ptr() and f.is_deref():
            if find_struct_iter(sample, f.value, f.pte_type):
                count+=1
            else:
                count-=1
                
        if f.is_array_of_struct_ptr():
            for e in f.array_elements:
                if e == 0:
                    continue
                if find_struct_iter(sample, e, f.pte_type):
                    count+=1
                else:
                    count-=1
    return count


def load_ram(sample):
    sample = list(sample)
    sample.sort(key=functools.cmp_to_key(sort_struct))
    
    RAM = defaultdict(list)
    
    sample = [s for s in sample if s.addr > 0xffff880000000000]
    
    # We begin by loading into RAM 
    for s in sample:
        RAM[s.addr].append(s)
            
    # Now we expand outer structures at inner addresses
    struct_addrs = set(RAM.keys())
    for s in sample[::-1]:
        for addr in range(s.addr+1, s.addr+s.size):
            if addr in struct_addrs:
                RAM[addr] = [s] + RAM[addr]

    # Finding exploration glitches
    glitches = set()
    for structs in list(RAM.values()):
        if len(structs) == 1:
            continue
        
        for i, s1 in enumerate(structs):
            for s2 in structs[i+1:]:                
                if is_contained(s2, s1):
                    break
                glitches.add(s2.addr)
    
    to_delete = set()
    for addr in glitches:
        for outlier in find_outlier(RAM, sample, addr):
            to_delete.add(outlier)
            
    delete_structs(RAM, sample, to_delete)
    
    return dict(RAM), sample

# Given a RAM entry, check if it makes sense (in terms of nested structures) or not.
def is_consistent(structs):
    for a, b in zip(structs, structs[1:]):
        if not is_contained(b, a):
            return False
    return True

# If there are only two structures in the RAM entry at address `addr`, then we check which one contains more valid structure pointer.
# If there are more than 2, then we find the best (again in terms of number of valid pointers) combinations of structures.
def find_outlier(RAM, sample, addr):
    structs = list(RAM[addr])
    if len(structs) == 2:
        a, b  = structs
        if count_valid_struct_ptr(sample, a) >= count_valid_struct_ptr(sample, b):
            return [b]
        else:
            return [a]

    combinations = []
    for i in range(1, len(structs))[::-1]:
        for comb in itertools.combinations(structs, i):
            if is_consistent(comb):
                tot_valid = sum([count_valid_struct_ptr(sample, s) for s in comb])
                combinations.append((tot_valid, len(comb), comb))

    best_combinations = sorted(combinations, reverse=True)[0][2]
    return set(structs) - set(best_combinations)

def get_outer_struct(RAM, addr):
    try:
        return RAM[addr][0]
    except (KeyError, IndexError):
        return None

def get_struct(RAM, addr, ty):
    try:
        return [s for s in RAM[addr] if s.ty == ty][0]
    except (KeyError, IndexError):    
        return None

def get_all_outer_structs(RAM):
    all_structs = set()
    for i in RAM:
        all_structs.add(RAM[i][0])
    return all_structs
