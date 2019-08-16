import os
import subprocess
import json
import re
import shutil
import sys

from multiprocessing import Pool

def grep_points_to(stderr):
    points_to = set()
    for x in stderr.split("\n"):
        if '"entry"' in x and '"loc"' in x:
            points_to.add(x)
    return points_to

def grep_unknown_args(stderr):
    unknown = set()    
    r = re.compile("error: unknown argument: '(.*)'")    
    for x in stderr.split("\n"):
        match = r.search(x)
        if match:
            unknown.add(match.group(1))
    return unknown

def clangify_entry(entry, unknown=None):
    args = ['clang-struct'] + entry['arguments'][1:]

    if unknown is not None:    
        args = [a for a in args if a not in unknown]

    if "-o" in args:
        i = args.index("-o")
        args = args[:i] + args[i+2:]
        
    return args

def run_subprocess(args):
    print(" ".join(args))
    p = subprocess.Popen(args, stderr=subprocess.PIPE)
    _, stderr = p.communicate()
    return p, stderr.decode()

# If the first run fails (most probably because complains about
# unknown arguments) then we try to compile the file again without
# those arguments.
def compile_entry(entry):
    args = clangify_entry(entry)
    p, stderr = run_subprocess(args)
    
    if p.returncode != 0:        
        ua = grep_unknown_args(stderr)
        args = clangify_entry(entry, ua)
        p, stderr = run_subprocess(args)
        
        # if p.returncode != 0:
        #     print("\nFailed to compile: %s" % " ".join(args))
        #     print(stderr)
    
    return grep_points_to(stderr)

def main():
    database = json.load(open("compile_commands.json"))
    points_to = set()
    print("[+] Running the clang plugin...")
    with Pool() as pool:
        for i, p in enumerate(pool.imap_unordered(compile_entry, database)):
            sys.stderr.write('\rDone %.2f%%' % ((i+1)/len(database) * 100))
            points_to.update(p)
            
    print("\n [+] Found %d info" % len(points_to))
    with open("kernel_info.txt", 'w') as f:
        for p in sorted(points_to):
            f.write(p+"\n")
            
if __name__ == "__main__":
    
    if not shutil.which("clang-struct"):
        print("[-] clang-struct not found..")
        sys.exit(-1)
        
    if not os.path.isfile("compile_commands.json"):
        print("[-] compile_commands.json not found..")        
        sys.exit(-1)
        
    main()

