name='server'; 
timings=(0 1 2 3 4 5 6 7 8 9 10 20 30 40 50 60 100 200 350 700 1000 3000 5000 8000 12000);

# name='test2';
# timings=(0);

# name='apache'; 
# timings=(0 100 200 300 400 500 600 700 800 900);

# name='gnome'; 
# timings=(0 20 40 60 80 100 120 140 160 180);

echo "Will take: "$((${#timings[@]}));
mkdir -p ../dumps/$name/;
for i in `seq 0 $((${#timings[@]}-1))`; do
    if [ $i == 0 ]; then
        sleeping=$((timings[$i]))
    else
        sleeping=$((timings[$i]-timings[$i-1]));
    fi;
    echo "Sleeping: " $sleeping "Name: " $i;
    sleep $sleeping;
    echo "[+] Making snapshot..."
    echo "stop" | nc localhost 2222 -q100;
    echo "savevm sample$i" | nc localhost 2222 -q100;
    echo "cont" | nc localhost 2222 -q100;
done;

echo "stop" | nc localhost 2222 -q100;
for i in `seq 0 $((${#timings[@]}-1))`; do
    echo "loadvm sample$i" | nc localhost 2222 -q1;
    kcore=$PWD/../dumps/$name/sample$i
    echo "dump-guest-memory -p $kcore" | nc localhost 2222 -q100;
    chmod 644 $kcore
done;

echo "info snapshots" | nc localhost 2222 -q100;
