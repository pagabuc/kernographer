name="server"
count=`ls ../dumps/$name/* | grep -v ".kmap" | wc -l`
echo "Starting to locate structs for "$count" samples"
count=$((count-1))
mkdir -p ../logs/$name
mkdir -p ../experiments/$name

seq 0 $count | parallel -j 4 --workdir $PWD "echo AA {}; gdb --batch -q -ex \"py SNAME='$name'; SID={}; KDIR='../clang-kernel/clang-kernel-build/kernel-ubuntu2/linux-hwe-4.8.0/'\"  -x ./locate_struct.py;"

# #Iterative way
# for i in `seq 0 $count`; do
#     unbuffer gdb --batch -q -ex "py SNAME='$name'; SID=$i; KDIR='../clang-kernel/clang-kernel-build/kernel-ubuntu2/linux-hwe-4.8.0/'"  -x ./locate_struct.py;
# done;
