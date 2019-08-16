# wget http://llvm.org/releases/8.0.0/llvm-8.0.0.src.tar.xz; tar xvf llvm-8.0.0.src.tar.xz
# (cd llvm-8.0.0.src &&
#     (cd tools && wget http://llvm.org/releases/8.0.0/cfe-8.0.0.src.tar.xz && tar xvf cfe-8.0.0.src.tar.xz && mv cfe-8.0.0.src clang) &&
#     (cd projects && wget http://llvm.org/releases/8.0.0/compiler-rt-8.0.0.src.tar.xz && tar xvf compiler-rt-8.0.0.src.tar.xz && mv compiler-rt-8.0.0.src compiler-rt)
# )

echo "[+] Downloading llvm, clang and compiler-rt..."
git clone https://github.com/llvm/llvm-project.git
(cd llvm-project && git checkout release/9.x)

mv llvm-project/llvm llvm/
mv llvm-project/clang/ llvm/tools/
mv llvm-project/compiler-rt llvm/projects/
rm -rf llvm-project/


echo "[~] Building..."
mkdir llvm-build;
(cd llvm-build &&
     CC=clang CXX=clang++ cmake -G "Ninja" -DCMAKE_BUILD_TYPE="RelWithDebInfo"  \
       -DLLVM_TARGETS_TO_BUILD=X86        \
       -DLLVM_INCLUDE_DOCS=OFF            \
       -DLLVM_ENABLE_SPHINX=OFF           \
       -DLLVM_PARALLEL_LINK_JOBS=2        \
       -DLLVM_ENABLE_ASSERTIONS=ON        \
       -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
       ../llvm/ 
     ninja;
)

