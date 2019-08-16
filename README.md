## Introduction

This repository contains the artifacts and the software developed for the paper Back to the Whiteboard: a Principled Approach for the Assessment and Design of Memory Forensic Techniques [1], available [here](https://www.usenix.org/system/files/sec19fall_pagani_prepub.pdf).

## Overview

In this paper we argue that memory forensics lacks a systematic way to compare, extract and study its techniques (plugins). To fill this gap we built a graph of kernel structures, where nodes represents kernel structures and edges are pointers from one to another, and we proposed a set of metrics which can be used to evaluate "how well" a technique performs. Moreover, in this paper we present different ways in which our framework can be used: extract new techniques to list processes, evaluate existing ones and find the "best" metric for a given task.

The core of this project is a Clang plugin that resolves where kernel abstract data types (i.e `list_head`) point ([clang/](clang/)), a GDB Python3 script that explore and traverse kernel structures ([src/](src/)) and a set of scripts to build and explore the graph ([graph-src/](graph-src/)).

## Prerequisites

On a Debian system `apt-get install git build-essential cmake ninja-build bear python3` should install most of the dependencies.

Manual installation is required only for the python library `graph-tool`: https://git.skewed.de/count0/graph-tool/wikis/installation-instructions

## Clang Plugin

First of all, download and build `clang` version 9 (which contains `asm-goto` support) and compile the clang plugin with the following commands:
```
cd clang/;
bash download-clang9.sh;
cd plugin/;
make
```

To test if everything was correctly compiled, add the root directory of this project to your PATH and run:
```
$ clang-struct ./clang/test.c

{"entry":"struct A.siblings","head":"struct A.children","loc":"./clang/test.c:17:5"}
```

## Kernel compilation

The script `make_kernel.sh` takes care of:

* compiling the kernel with gcc (and creating a compilation database with Bear)
* creating `.deb` packages of the kernel
* run the clang plugin over the kernel sources using the compilation database
* extract a number of other information which are needed for the exploration.

Since at the moment some information are hard-coded (more on this in TODO), only the following kernel version is "officially" supported:
```
wget https://cdn.kernel.org/pub/linux/kernel/v4.x/linux-4.14.78.tar.gz
tar xf linux-4.14.78.tar.gz;
cd linux-4.14.78

# create a .config file..

bash ../make_kernel.sh
```

Don't forget to create a .config file (`make defconfig; make kvmconfig`) or supply your own before running the script!

## Install the kernel in QEMU

To install the kernel Debian packages, you can use the following Debian image as a starting point (credentials `root:root` and `user:user`):

```
cd images;
wget http://crazyivan.s3.eurecom.fr:8888/kernel_graph/debian-testing.img.tar.gz
tar xvf debian-testing.img.tar.gz
```

Then run the QEMU machine and copy the packages:
```
bash run-qemu.sh
scp -P 2223 linux-image-*.deb root@localhost:~/
```

Finally, as root in the QEMU machine the kernel can be installed with the following commands:
```
dpkg -i linux*
apt-get remove linux-image-4.19.0-5-amd64 # to make sure we boot our kernel
reboot
```

If the network does not work after the reboot, update `/etc/network/interfaces`.

## Exploration

The exploration engine loads and explore a QEMU snapshot. The following command will take a snapshot named `sample0`:
```
echo -e "savevm sample0" | nc -N localhost 2222
```

To start the real exploration:
```
cd src/
gdb -q --batch -ex "py SNAME='sample0'; KDIR='../linux-XXX/'" -x locate_struct.py
```

The result of this script is saved in the file `explorations/sample0` along with some logging information in `logs/sample0`.

## Graph Creation

We are finally almost ready to create the graph! If you don't care about the weights, you can just run:

```
cd graph-src/
python3 create_graph.py --no-weights  ../explorations/sample0
```

This will save the resulting graph in `graphs/sample0` and write some logging information in `logs/sample0.graph`.

Otherwise, read the following sections to create the different weights and then run the `create_graph.py` script without `--no-weights`.

### Atomicity

To extract the atomicity weight a valid Volatility profile must be created:
```
cd volatility/tools/linux;
make -C "../../../linux-4.14/" M="$PWD" CONFIG_DEBUG_INFO=y
dwarfdump -di module.ko > module.dwarf
zip linux4.14.zip module.dwarf ../../../linux-4.14/System.map
cp linux4.14.zip ../../volatility/plugins/overlays/linux/
```

Then, the kernel mappings can be extracted with the provided `linux_dump_kmap` plugin:
```
python volatility/vol.py --plugins=$PWD/plugins/ -f ../dumps/sample0 --profile=Linuxlinux4_14x64 linux_dump_kmap &> ../weights/sample0.kmap
```

### Stability

To be meaningful, the stability weight needs multiple graph created from subsequent snapshots of the same machine, so you should run the exploration and graph creation scripts multiple times.
After you do so, the stability weight can be extracted with:
```
cd graph-src
python3 create_heatmap.py
```

### Generality

The generality weight is provided as is under `weights/offsets.db`. The scripts to download the 85 Ubuntu kernels and extract the structure layouts will come soon!

### TODO
- Improve the Clang plugin: it should be possible to extract the points-to information about red black trees and `hlist_head` as well. Moreover, to cover more `list_head`s, can we "transform" the macro "list_for_each_entry" in a function and add the logic to analyze its arguments in the plugin?
- At this moment, everything is represented as a Struct but this does not fit well global kernel pointers or global arrays. Add some more classes to represent these cases can make the code definitely better.

### Contacts

If you have any idea on how this graph can be used, or if you are looking for some (we have many!) please get in touch!

Mail: python -c "print 'pa%s%seurecom.%s' % ('gani', '@', 'fr')"

Twitter: @pagabuc

## Publications

[1] Pagani, Fabio, and Davide Balzarotti. "Back to the Whiteboard: a Principled Approach for the Assessment and Design of Memory Forensic Techniques." 28th Usenix Security Symposium (Usenix Security 19)
