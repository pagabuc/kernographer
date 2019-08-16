import sys
import glob
import os
import gc
import sys
import pickle
sys.path.append("../src/")
from mytypes import Sample, Field, Struct
import cProfile
import re

timings=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 100, 200, 350, 700, 1000, 3000, 5000, 8000, 12000]

def natural_sort(l): 
    convert = lambda text: int(text) if text.isdigit() else text.lower() 
    alphanum_key = lambda key: [ convert(c) for c in re.split('([0-9]+)', key) ] 
    return sorted(l, key = alphanum_key)

def label_struct(s):
    return '%s %s' % (hex(s.addr), s.ty)

def update_heatmap(sample, heatmap, sample_index):
    for s in sample:
        for f in s:
            k = []
            if f.is_array_of_struct_ptr() or f.is_array_of_struct():
                k = [('%s %s[%d]' % (label_struct(s), f.name, i), e) for i,e in enumerate(f.array_elements)]
            elif f.is_ptr_array_of_ptr() or f.is_percpu():                    
                k = [('%s %s' % (label_struct(s), f.name), f.value)]
                k += [('%s_%s_array_of_ptr %s[%d]' % (hex(s.addr), hex(f.value), f.name, i), e) for i,e in enumerate(f.array_elements)]
            elif f.is_struct_ptr() and f.is_deref():
                k = [('%s %s' % (label_struct(s), f.name),  f.value)]
            elif ((not f.is_ptr() and type(f.value) == int and f.value > 0xffff800000000000) or
                  (f.is_void_ptr() and f.is_deref())): # int and void ptr
                k = [('%s %s' % (label_struct(s), f.name), f.value)]
            else:
                continue
            
            for label, value in set(k):
                try:
                    heatmap[label] += [value]
                except KeyError:
                    if sample_index == 0:
                        heatmap[label] = [value]
                    continue
                
    return heatmap

def stability(l):
    i = 1
    while i < len(l):
        if l[i] != l[0]:
            break
        i+=1        
    return i-1

def main():
    
    sample_list = natural_sort(glob.glob("../explorations/*"))
    print(sample_list)
    
    heatmap = {}

    for i, s in enumerate(sample_list):
        print("[+] Loading %s" % s)
        sample = Sample.load(s)
        heatmap = update_heatmap(sample, heatmap, i)
        
        for k,v in heatmap.items():
            if len(v) < i+1:
                heatmap[k] = v + [0]
        del sample
        gc.collect()

    new_heatmap = {}
    for k,v in heatmap.items():
        idx = stability(v)
        new_heatmap[k] = timings[idx]

    print("Saving in ../weights/heatmap.db")
    with open('../weights/heatmap.db', "wb") as f:
        pickle.dump(new_heatmap, f)
    
    
if __name__ == "__main__":
    main()

