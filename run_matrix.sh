#!/bin/bash
# Usage: sudo-less.   bash run_matrix.sh <stage> <mode> <resume on|off> "<cfgs>" "<clients>" "<rounds>" <repeats> [delay_ms] [loss]
# Example: bash run_matrix.sh 3 native off "K1 H1 H2 P1" "5 10 20" "10 50 100" 3
cd "$(dirname "$0")"; PY="sudo venv/bin/python"
STAGE=$1; MODE=$2; RES=$3; CFGS=$4; CLS=$5; RDS=$6; REP=$7; DELAY=${8:-0}; LOSS=${9:-0}
for r in $(seq 1 $REP); do
  # random order inside each repeat (spreads cloud noise evenly over configurations)
  for cell in $(for c in $CFGS; do for n in $CLS; do for R in $RDS; do echo "$c,$n,$R"; done; done; done | shuf); do
    IFS=, read cfg n R <<< "$cell"
    echo ">>> repeat $r : $cfg C=$n R=$R mode=$MODE resume=$RES delay=$DELAY loss=$LOSS"
    $PY controller/run_experiment.py --cfg $cfg --clients $n --rounds $R --mode $MODE --resume $RES --repeat $r \
        --stage $STAGE --delay-ms $DELAY --loss $LOSS > /dev/null || echo "!!! run failed: $cell (see runs/ folder)"
  done
done
echo "finished. Results appended to results/runs.csv"
