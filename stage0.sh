#!/bin/bash
# STAGE 0: how many TCP connections / TLS handshakes does a Flower run really make?
cd "$(dirname "$0")"; PY="sudo venv/bin/python"
for i in 1 2 3; do $PY controller/run_experiment.py --cfg K1 --clients 5 --rounds 10 --mode native --stage 0 --repeat $i | grep -E "RUN|n_syn|n_streams|n_clienthello|n_rst|expected_cxr|hs_mean_ms|tcpdump_dropped"; done
$PY controller/run_experiment.py --cfg K1 --clients 5 --rounds 10 --mode reconnect --stage 0 | grep -E "RUN|n_syn|n_streams|n_clienthello|n_rst|expected_cxr|hs_mean_ms|tcpdump_dropped"
$PY controller/run_experiment.py --cfg PLAIN --clients 5 --rounds 10 --mode native --stage 0 | grep -E "RUN|n_syn|n_streams|n_rst|expected_cxr"
echo; echo "Summary table:"
venv/bin/python - << 'PYEOF'
import pandas as pd
d = pd.read_csv("results/runs.csv"); d = d[d.stage.astype(str) == "0"]
print(d[["run_id","cfg","mode","clients","rounds","n_syn","n_streams","n_clienthello","n_rst","expected_cxr"]].to_string(index=False))
PYEOF
