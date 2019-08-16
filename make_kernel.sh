
if [[ ! -d "arch" ]]; then
    echo "This does not seem a kernel source folder.."
    exit -1;    
fi

rm -rf linux-*.deb linux-*.changes;

echo "[+] Cleaning the kernel..."
make clean -j4;

echo "[+] Configure DEBUG_INFO=y and RANDOMIZE_BASE=n"
./scripts/config --set-val CONFIG_DEBUG_INFO y
./scripts/config --set-val CONFIG_RANDOMIZE_BASE n
make olddefconfig

echo "[+] Building the kernel..."
time bear make -j8 &> ./log;

echo "[+] Building .deb..."
make bindeb-pkg;
mv ../linux-*.deb ../linux-*.changes .

python3 ../run_clang.py

echo "[+] Extracting System.map.line_numbers and percpu_globals.txt"
nm ./vmlinux  -l > System.map.line_numbers
grep -Rn "DEFINE_PER_CPU\|DECLARE_PER_CPU_PAGE_ALIGNED\|DECLARE_PER_CPU_SHARED_ALIGNED\|DEFINE_PER_CPU_ALIGNED" --include=\*.{c,h} | grep struct > ./percpu_globals.txt

