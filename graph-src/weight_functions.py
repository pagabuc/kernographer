import pickle
from os.path import join as joinpath
from os.path import isfile
import sys
import logging

class Weights():
    
    def __init__(self, sample_name, weights_path="../weights"):
        offsets_path = joinpath(weights_path, "offsets.db")
        heatmap_path = joinpath(weights_path, "heatmap.db")
        kmap_path = joinpath(weights_path, "%s.kmap" % sample_name)                

        for i in [offsets_path, heatmap_path, kmap_path]:
            if not isfile(i):
                print ("[-] Missing %s" % i)
                sys.exit(-1)
        
        self.setup_offsets_weight(offsets_path)
        self.setup_heatmap_weight(heatmap_path)
        self.setup_atomicity_weight(kmap_path)

    def setup_offsets_weight(self, offsets_path):
        print("[+] Loading %s" % offsets_path)
        with open(offsets_path, 'rb') as f:
            self.offsets_db = pickle.load(f, encoding='utf-8')
        
    def setup_heatmap_weight(self, heatmap_path):
        print("[+] Loading %s" % heatmap_path)
        with open(heatmap_path, 'rb') as f:
            self.heatmap_db = pickle.load(f, encoding='utf-8')

    def setup_atomicity_weight(self, kmap_path):
        print("[+] Loading %s" % kmap_path)
        self.kmap_db = dict()
        with open(kmap_path, 'r') as f:
            for l in f:
                if l.startswith("0x"):
                    l = l.strip()
                    vaddr, paddr = l.split()
                    self.kmap_db[int(vaddr, 16)] = int(paddr, 16)

    def offset_weight(self, struct, edge_name):
        if struct.ty in self.offsets_db:
            if edge_name in self.offsets_db[struct.ty]:
                return self.offsets_db[struct.ty][edge_name]

        logging.error("offset_weight %s %s not found" % (struct.ty, edge_name))
        return [[]]
            
    def heatmap_weight(self, label, edge_name):
        l = '%s %s' % (label, edge_name)
        try:
            return self.heatmap_db[l]
        except KeyError:
            return -1

    def mask_2kb(self, addr):
        return addr & ~(0xfff)

    def mask_2mb(self, addr):
        return addr & ~(0x1fffff)

    # Return the physical address of addr, *not* page aligned
    def translate(self, addr):
        a = self.mask_2kb(addr)
        try:
            return self.kmap_db[a] + (addr & 0xfff)
        except KeyError:
            pass
        
        a = self.mask_2mb(addr)
        try:
            return self.kmap_db[a] + (addr & 0x1fffff)
        except KeyError:
            pass

        # Userspace addresses
        return 0
    
    # Returns the distance in page units
    def atomicity_weight(self, fr, to):
        f = self.translate(fr)
        t = self.translate(to)
        r = (abs(t - f) >> 12) + 1
        return r
