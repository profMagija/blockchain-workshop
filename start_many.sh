#!/bin/bash

trap "trap - SIGTERM && kill -- -$$" SIGINT SIGTERM EXIT

python -m bcws --host 127.0.0.1 --port "11120" blockchain --nd --ds &

for i in 1 2 3 4 5 6
do
    python -m bcws --host 127.0.0.1 --port "1112$i" --peer 127.0.0.1:11120 blockchain &
    sleep 1
done

wait