# Part 2 guide (continues from Stage 5): constrained networks, analytical model, mitigation, release
Windows + WSL2 (Ubuntu 24.04) version. Everything is typed in the **Ubuntu terminal** from `~/pqfl` unless stated.

You have finished Stages 0-5. This guide is **not a diff**: it is the complete set of instructions for everything that remains.

---

## 0. What your professor asked for, and how this guide delivers it

| Professor's requirement | What you will do | Stage |
|---|---|---|
| New framing: *Quantifying and Mitigating PQ-TLS Overhead in Edge FL under Constrained and Transient Network Conditions* | Already in the new report (`PQ-TLS_Edge_FL_Report_v2.docx`) | - |
| Isolate **control plane** (handshake time, CPU, initial-window delay due to ML-DSA certificate size) from **data plane** (model payload) | New metrics `cp_total_s`, `data_total_s`, `train_total_s`, `agg_total_s`; new packet metric `hs_s2c_bursts` (server had to wait = initial-window stall); CPU time per handshake | 6, 7 |
| Constrained network with `tc netem`: loss 1-5 %, RTT 50-100 ms; show fragmentation of the FIPS 204 certificate flight causing retransmission penalties | Six network profiles (`controller/profiles.py`), initial-window sweep, loss sweep, retransmission counters | 6, 7 |
| >= 10-20 independent repeats per combination, SD, 95 % CI, tail latencies | Resumable matrix runner (`--repeats 10`, 20 for decisive cells); `analysis/stats.py` | 7, 8 |
| Step 1: analytical model of total training time (handshake term depends on resumption state, payload term on client bandwidth, loss penalty from segment fragmentation) | `analysis/model.py`, fitted and validated on held-out network profiles | 9 |
| Step 2: full matrix: persistent vs transient x resumption OFF/ON x K1/H1/H2/P1 x LAN vs high-latency/lossy | `controller/matrix.py` | 7 |
| Focus on **modelling and mitigating** fragmentation and connection dynamics | Mitigation experiments (initial window, minimum RTO, resumption, persistent, combined) compared with model predictions | 10 |
| Step 3: reproducible open-source codebase pqflwr: automated OpenSSL 3.5.x + nginx build, netns + netem instructions, CIC-IDS2017 preprocessing | `README.md`, `Makefile`, `env/`, `netem/`, `fl/prepare_data.py`, CI, tests | 11 |

**Important about your Stage 0-5 results:** they stay valuable as the *pilot study* on an ideal LAN (report section 8.1). The new matrix is re-run with the new code because (a) the new control/data-plane columns do not exist in old runs, (b) the professor wants at least 10-20 repeats, and (c) constrained networks are new. Do not delete the old results; keep them as `pilot`.

**CPU cycles:** your machine (WSL/VM) does not expose hardware counters, so you report **CPU time** (user+system seconds) of the proxies per handshake. Write this in the report's Limitations. Do not convert to cycles.

**How long will this take?** Be realistic: the full matrix is many hours (likely 1-3 days of machine time). The runner is *resumable*, you can stop with Ctrl+C and continue any time. In section 8 you can print an estimate before starting, and agree with your guide on a smaller design if needed.

---

## 1. Stage 6 - Update the code, verify the new tooling, re-measure the handshake table

### 6.1 Save your pilot work in git (5 min)
```bash
cd ~/pqfl
git status
```
- If it prints a branch name (e.g. `On branch master`), this folder is your clone of `github.com/prishsha/pqflwr`. Continue.
- If it says `not a git repository`, do this once:
```bash
cd ~ && git clone https://github.com/prishsha/pqflwr.git pqflwr_repo
cp -a ~/pqfl/. ~/pqflwr_repo/          # copies everything including your results; hidden .git stays from the clone
cd ~/pqflwr_repo && rm -rf venv && python3 -m venv venv && . venv/bin/activate && pip install -r requirements.txt 2>/dev/null || true
```
and from now on work in `~/pqflwr_repo` (wherever this guide says `~/pqfl`, use that folder).

Commit and tag the pilot:
```bash
git add -A && git commit -m "Pilot study on ideal LAN (stages 0-5)" && git tag pilot-v1
git push && git push --tags
```
GitHub asks for a login: use your username and a **personal access token** as password (GitHub -> Settings -> Developer settings -> Personal access tokens), or run `gh auth login` if you installed the GitHub CLI.

### 6.2 Apply the update (5 min)
Download `pqflwr_v2.zip` to your Windows Downloads folder, then in Ubuntu:
```bash
sudo apt-get install -y rsync unzip
rm -rf /tmp/v2 && mkdir /tmp/v2 && unzip -q /mnt/c/Users/<YourWindowsName>/Downloads/pqflwr_v2.zip -d /tmp/v2
rsync -a --exclude runs --exclude results --exclude observations --exclude data --exclude pki/certs --exclude venv /tmp/v2/pqfl/ ~/pqfl/
cd ~/pqfl && git status --short | head -40
```
`git status` now lists changed files (`M`) and new files (`??`): that is the update. Your `runs/`, `results/`, `observations/`, `data/` and certificates were not touched.

Install the extra Python packages (SciPy for confidence intervals, pytest) and run the unit tests:
```bash
. venv/bin/activate
pip install -r requirements.txt
python -m pytest -q tests                 # must print: 4 passed
```

> **DOCUMENT NOW (Observation 6.2)**
> `python3 tools/log_obs.py --stage 6 --kind setup "Updated code to v2: control/data-plane metrics, netem rate, TCP knobs, resumable matrix, statistics, analytical model. 4 unit tests pass."`
> Commit: `git add -A && git commit -m "Update to v2 toolchain (plane separation, matrix runner, stats, model)"`

### 6.3 Verify that network emulation works (this is REQUIRED now)
Everything from here on needs `tc netem`. Check:
```bash
bash env/00_check_system.sh
```
You must see `PASS netem`. If it says `FAIL netem`, stop and do **Appendix B** (build a WSL kernel with netem) before continuing; without netem you cannot do the professor's constrained-network experiments (alternative: run Stages 6-10 on a small Ubuntu 24.04 cloud VM; tell your guide).

Make sure the virtual network exists (re-create it after any WSL restart):
```bash
bash env/04_netns_up.sh
```
Now test each emulation feature by hand. Run the commands one by one and compare with the expected value.
```bash
# 1) delay: one-way 25 ms on both sides = RTT 50 ms
bash netem/set_netem.sh 25 0 0
sudo ip netns exec cli ping -c 5 10.10.0.1 | tail -2          # expect rtt avg about 50 ms

# 2) loss: 3 % on the server side (affects replies)
bash netem/set_netem.sh 0 3 0
sudo ip netns exec cli ping -c 300 -i 0.02 -q 10.10.0.1 | tail -3   # expect about 3 % packet loss (1-6 % is fine)

# 3) bandwidth: 20 Mbit/s
bash netem/set_netem.sh 0 0 20
sudo ip netns exec srv iperf3 -s -D
sudo ip netns exec cli iperf3 -c 10.10.0.1 -t 5 | tail -4      # expect about 19-20 Mbits/sec
sudo pkill iperf3

# 4) TCP knobs: initial window 4 and minimum RTO 50 ms
bash netem/tune_route.sh 4 50
sudo ip netns exec srv ip route show                           # the 10.10.0.0/24 line must show "initcwnd 4 rto_min 50ms"
# reset everything to defaults
bash netem/tune_route.sh 0 0; bash netem/set_netem.sh 0 0 0
sudo ip netns exec srv ip route show                           # no initcwnd/rto_min shown any more
```
If `tune_route.sh` prints an error, copy it here; do not continue until step 4 works.

> **DOCUMENT NOW (Observation 6.3: emulation verified)**
> Screenshot the 4 outputs -> `observations/fig_netem_checks.png` and log:
> `python3 tools/log_obs.py --stage 6 --kind verification "netem verified: RTT 25ms one-way -> ping avg <..> ms; 3% loss -> <..>% ping loss; 20 Mbit/s -> iperf3 <..> Mbit/s; route knobs initcwnd/rto_min applied and reset."`
> Report: Chapter 5 (Network emulation) and Table 2.

### 6.4 Look at the network profiles (decision, 5 min)
```bash
cat controller/profiles.py
```
The six profiles are LAN, WAN50 (RTT 50 ms, 20 Mbit/s), WAN100 (RTT 100 ms), LOSS1 (RTT 50, 1 % loss), LOSS3 (RTT 100, 3 %), LOSS5 (RTT 100, 5 %). They cover the professor's ranges. Change them only after talking to your guide.

> **DOCUMENT NOW (Observation 6.4)** `python3 tools/log_obs.py --stage 6 --kind decision "Network profiles: LAN, WAN50, WAN100, LOSS1, LOSS3, LOSS5 (see controller/profiles.py). Loss applied on server side only (server-to-client segments); 20 Mbit/s edge link."`

### 6.5 Calibration run of the new plane-separated metrics (10 min)
One transient run on a constrained profile:
```bash
sudo venv/bin/python controller/run_experiment.py --cfg H2 --clients 10 --rounds 10 --mode reconnect --stage 6 \
     --profile WAN100 --delay-ms 50 --rate-mbit 20 > /dev/null
venv/bin/python - << 'PYEOF'
import pandas as pd
d = pd.read_csv("results/runs.csv"); r = d.iloc[-1]
for c in ["profile","rtt_ms","rate_mbit","n_sessions","n_clienthello","cp_total_s","data_total_s","train_total_s","agg_total_s","epoch_total_s","logical_total_s","hs_mean_ms","hs_s2c_bursts_mean","flight_span_ms_mean","retx_total","tcpdump_dropped"]:
    print("%-22s %s" % (c, r[c]))
print("sum of parts:", r.cp_total_s + r.data_total_s + r.train_total_s + r.agg_total_s)
PYEOF
```
Checks: `n_sessions` = 10, `n_clienthello` about 100 (10 clients x 10 rounds), `cp_total_s` is clearly larger than on the LAN (round trips cost 100 ms each), `tcpdump_dropped` = 0, and "sum of parts" equals `epoch_total_s`. `data_total_s` must not be negative; if it is, copy the output here.

What the new columns mean (this is the professor's plane separation):
- `cp_total_s` = **control plane**: from "all clients start connecting" until the server has all clients registered and dispatches the first task; contains TCP connect, TLS handshake, HTTP/2+Flower registration. Summed over sessions.
- `data_total_s` = **data plane**: model download + update upload (time from dispatch to last update received, minus the slowest client's training time).
- `train_total_s`, `agg_total_s` = compute; `epoch_total_s` = all four added.

> **DOCUMENT NOW (Observation 6.5)** `python3 tools/log_obs.py --stage 6 --cfg H2 --kind verification "Calibration H2 WAN100 transient C=10 R=10: control plane <..> s, data plane <..> s, compute <..> s, total <..> s; parts sum to total."`

### 6.6 Re-measure the Stage 1 handshake table with the new code (about 1.5 hours)
This table is the **measured input of the analytical model**, and the evidence for the fragmentation/initial-window question. Keep the old file and start fresh:
```bash
mv results/stage1.csv results/stage1_pilot.csv 2>/dev/null
bash netem/set_netem.sh 0 0 0; bash netem/tune_route.sh 0 0
```
**(a) LAN baseline, full and resumed handshakes (these 8 rows feed the model)**
```bash
for c in K1 H1 H2 P1; do
  sudo venv/bin/python stage1/handshake_loop.py --cfg $c --n 300 --tag s6_lan > /dev/null
  sudo venv/bin/python stage1/handshake_loop.py --cfg $c --n 300 --resume --tag s6_lan > /dev/null
done
venv/bin/python -c "
import pandas as pd; d=pd.read_csv('results/stage1.csv'); pd.set_option('display.width',250)
print(d[['cfg','resume','n','hs_mean_ms','hs_ci95_lo_ms','hs_ci95_hi_ms','hs_p95_ms','hs_p99_ms','hs_frame_bytes_mean','hs_payload_s2c_mean','hs_segments_s2c_mean','cpu_srv_per_hs_ms','cpu_cli_per_hs_ms','n_resumed_psk']].round(3).to_string(index=False))"
```
Checks: rows with `resume=True` must have `n_resumed_psk` close to 300 (they really resumed) and a smaller `hs_payload_s2c_mean`; ML-DSA rows have a server flight of about 10 KB and 8-9 segments.

**(b) Initial-window sweep: does the certificate flight stall on a slow link? (about 30 min)**
```bash
for iw in 4 10 20; do for c in K1 H2 P1; do
  sudo venv/bin/python stage1/handshake_loop.py --cfg $c --n 200 --delay-ms 25 --rate-mbit 20 --initcwnd $iw --tag s6_iw > /dev/null
done; done
```
**(c) Loss sweep (RTT 100 ms, 20 Mbit/s)**
```bash
for l in 1 3 5; do for c in K1 H2 P1; do
  sudo venv/bin/python stage1/handshake_loop.py --cfg $c --n 200 --delay-ms 50 --loss $l --rate-mbit 20 --tag s6_loss > /dev/null
done; done
bash netem/set_netem.sh 0 0 0; bash netem/tune_route.sh 0 0
```
Look at the fragmentation evidence:
```bash
venv/bin/python -c "
import pandas as pd; d=pd.read_csv('results/stage1.csv'); pd.set_option('display.width',250)
print(d[['cfg','resume','rtt_ms','loss_pct','initcwnd','hs_mean_ms','hs_p95_ms','hs_p99_ms','hs_payload_s2c_mean','hs_segments_s2c_mean','hs_s2c_bursts_mean','flight_span_ms_mean','retx_total','server_tcp_retrans_delta']].round(2).to_string(index=False))"
```
How to read it (your supervisor wants *measured* evidence, not assumed thresholds):
- `hs_s2c_bursts_mean` = how many bursts the server flight was sent in. 1.0 means the whole flight went out at once. About 2.0 means the server had to wait for the client's acknowledgements (initial-window stall) = one extra RTT.
- `flight_span_ms_mean` close to the RTT or more means the same.
- Compare H2/P1 (about 10 KB flight) with K1 (about 1 KB) at `initcwnd` 4, 10, 20. The model (Eq. 5) predicts: an extra round trip for H2/P1 when `initcwnd` is below about 8, none at 10 or 20. **Report what you measure, even if it disagrees.**
- `retx_total` and `server_tcp_retrans_delta` show retransmissions under loss; ML-DSA flights have more segments, so more can be hit.
- A few handshakes taking about 1000 ms under loss are real TCP behaviour (lost SYN-ACK: the initial retransmission timeout is 1 s). Keep them: they are the tail latency the professor wants reported.

> **DOCUMENT NOW (Stage 6 evidence)**
> - Table 8 of the report (section 8.4): config, profile, IW, server flight (B), segments, bursts, extra RTT?, retransmissions.
> - Table 6 (handshake tails): p50/p95/p99 from the sweeps.
> - Observations (one per finding):
> ```bash
> python3 tools/log_obs.py --stage 6 --cfg H2 --kind measurement "initcwnd=4, RTT 50 ms: server flight <..> B in <..> segments, bursts <..>, handshake <..> ms vs <..> ms at initcwnd=10 -> extra RTT yes/no."
> python3 tools/log_obs.py --stage 6 --cfg H2 --kind measurement "Loss 3 %, RTT 100 ms: p95 <..> ms, p99 <..> ms, retransmissions <..> (K1: <..>)."
> python3 tools/log_obs.py --stage 6 --kind measurement "CPU time per handshake (server/client, ms): K1 <..>/<..>, H1 <..>/<..>, H2 <..>/<..>, P1 <..>/<..>."
> python3 tools/log_obs.py --stage 6 --cfg H2 --kind anomaly "<anything surprising, e.g. no extra RTT even at initcwnd 4>"
> ```
> - Commit: `git add -A && git commit -m "Stage 6: tooling verified, handshake table re-measured with CPU and CI"`
> - **Show the Stage 6 table to your guide before the long matrix.** If the fragmentation effect is absent at default settings, that is itself a finding; the model and the initial-window sweep explain when it appears.

---

## 2. Stage 7 - The full factorial matrix (>= 10 repeats per cell)

### 7.1 What will be run
Factors (professor's Step 2): connection type (native = persistent, reconnect = transient) x resumption (off, on) x configuration (K1, H1, H2, P1, plus PLAIN as baseline) x network profile (6). Core size: **C = 10 clients, R = 10 rounds**. Resumption ON with persistent connections cannot help (there is no reconnection); it is run anyway as a control and should show no effect.

### 7.2 Plan first (dry run, prints the number of runs and a rough time)
```bash
sudo venv/bin/python controller/matrix.py --stage 7 --clients 10 --rounds 10 --repeats 10 --dry-run
```
It prints `cells`, `runs still missing`, and a rough hour estimate (very approximate; your first real hour tells the truth). If the estimate is more than you can afford, **agree with your guide** on one of: C = 5 instead of 10 (fewer processes per session, much faster transient runs); dropping the WAN50 profile (`--profiles LAN WAN100 LOSS1 LOSS3 LOSS5`); starting with `--cfgs PLAIN K1 H2 P1` (H1 later). Write the decision in the observation log.

### 7.3 Run it (inside tmux so it survives disconnects)
```bash
tmux new -s matrix
cd ~/pqfl
sudo venv/bin/python controller/matrix.py --stage 7 --clients 10 --rounds 10 --repeats 10 2>&1 | tee -a results/matrix_stdout.log
# detach: Ctrl+B then D     come back: tmux attach -t matrix
```
- The runner shuffles all runs (spreads noise evenly), prints one line per run, and writes failures to `results/failed.log`.
- **Stop any time with Ctrl+C. Run the same command again: it counts what is done and continues.**
- While it runs: keep Windows awake and plugged in, close other apps. If Windows slept, the runs around that time are suspect: note the time and look for outliers later.
- After the first 30-60 minutes, check progress with the sanity tool (open a second terminal):
```bash
cd ~/pqfl && . venv/bin/activate && python tools/check_runs.py --stage 7 --min-runs 1
```
It lists every finished cell and flags problems: handshakes not matching expectation (native = C, transient = C x R; **if your Stage 0 measurement showed a different number for native mode, edit the `exp_hs` line in `tools/check_runs.py` accordingly**), resumption not happening, resumed handshakes with resumption OFF, loss profiles without retransmissions, dropped packets, F1 differences.

### 7.4 Decisive cells to 20 repeats (after the core matrix, professor: 10-20)
```bash
sudo venv/bin/python controller/matrix.py --stage 7 --clients 10 --rounds 10 --repeats 20 \
     --cfgs PLAIN K1 H2 P1 --profiles WAN100 LOSS3 LOSS5 --modes reconnect --resumes off on
```

### 7.5 Scaling cells (clients and rounds; for the crossover analysis)
Choose a few profiles, not all (cost). Persistent mode is cheap; transient mode with many rounds is expensive:
```bash
sudo venv/bin/python controller/matrix.py --stage 7 --clients 5 20 --rounds 10 --repeats 10 --profiles LAN WAN100 LOSS3 --resumes off
sudo venv/bin/python controller/matrix.py --stage 7 --clients 10 --rounds 50 100 --repeats 10 --profiles LAN WAN100 LOSS3 --modes native --resumes off
sudo venv/bin/python controller/matrix.py --stage 7 --clients 10 --rounds 50 --repeats 10 --profiles WAN100 LOSS3 --modes reconnect --resumes off on
```
(If the dry run says the last line takes too long, reduce repeats to 10 and drop `LOSS3` from it, and say so in the report.)

### 7.6 Final checks and commit
```bash
python tools/check_runs.py --stage 7 | tail -30       # every cell should say "ok"; read each issue
ls runs | wc -l; cat results/failed.log | head        # failed runs are simply missing; rerun the matrix command to fill them
git add -A && git commit -m "Stage 7: full factorial matrix (raw results)" && git push
```
Raw `runs/` (pcaps) are in `.gitignore` and are not pushed; zip them for your own backup: `zip -rq evidence_stage7.zip runs results observations`.

> **DOCUMENT NOW (Stage 7)**
> ```bash
> python3 tools/log_obs.py --stage 7 --kind decision "Matrix: C=<..>, R=<..>, profiles <..>, repeats <..> (20 for <..>); modes native+reconnect; resume off+on; random order; resumable runner."
> python3 tools/log_obs.py --stage 7 --kind verification "check_runs.py: <n> cells ok, issues: <..>."
> python3 tools/log_obs.py --stage 7 --kind anomaly "<failed runs, invalid runs (dropped packets), outliers, Windows sleep events>"
> python3 tools/log_obs.py --stage 7 --kind measurement "Native mode handshakes per run: <..> (C=10). Transient: <..> (C x R = 100). Resumed with resumption ON: <..>."
> ```
> Report: chapter 6 (matrix actually executed, number of repeats per cell) and 8.2.

---

## 3. Stage 8 - Statistics: SD, 95 % CI, tails, tests (30 min)
```bash
. venv/bin/activate
python analysis/stats.py --stage 7
```
Outputs:
- `results/stats_cells.csv`: for every cell (profile, mode, resume, config, C, R): `n_runs`, and for epoch time, control plane, data plane, training, aggregation, handshake time, CPU, retransmissions: `_mean`, `_sd`, `_ci_lo`, `_ci_hi` (95 % CI, Student t), `_p50`, `_p95`, `_p99`; plus **pooled individual-handshake tails** `hs_p50_ms`, `hs_p95_ms`, `hs_p99_ms`, `hs_max_ms`.
- `results/stats_vs_K1.csv`: each configuration against K1 in the same condition: difference, 95 % CI of the difference, % difference, Mann-Whitney p-value, Cliff's delta (effect size), `significant_95`.
- `results/plots/epoch_<mode>_res<..>_C<..>_R<..>.png`: left: epoch time with 95 % CI bars per profile and config; right: stacked control/data/compute decomposition.
The script prints a warning if some cell has fewer than 10 runs (run the matrix again).

How to read and report:
- "Significant" means the 95 % CI of the difference to K1 excludes 0. Also read `cliffs_delta` (|d| < 0.15 negligible, 0.15-0.33 small, 0.33-0.47 medium, > 0.47 large) and the Mann-Whitney p-value (do not claim a difference if only one of the two tests agrees: say so).
- p95/p99 over **runs** describe the spread of whole-training times; the pooled handshake p95/p99 describe single-connection tails. Report both and say which is which.

> **DOCUMENT NOW (Stage 8)**
> - Fill Table 4 (decomposition), Table 5 (mean, SD, CI, p95, p99), Table 6 (handshake tails), Table 7 (difference to K1) of the report; paste the decomposition plots as Figure (a)/(b).
> ```bash
> python3 tools/log_obs.py --stage 8 --kind measurement "LAN: H2 vs K1 total time <..> s (CI <..>..<..>), control plane share <..> %. LOSS3: H2 vs K1 <..> s (CI <..>), significant yes/no."
> python3 tools/log_obs.py --stage 8 --kind measurement "Share of control plane / data plane / compute in total time, transient mode LOSS3 K1: <..>/<..>/<..> %."
> python3 tools/log_obs.py --stage 8 --kind decision "Claims limited to cells where CI excludes zero AND Mann-Whitney p < 0.05."
> ```
> - Commit: `git add -A && git commit -m "Stage 8: statistics (CI, tails, tests vs K1)" && git push`

---

## 4. Stage 9 - The analytical model: fit, validate, predict (1 hour)
```bash
python analysis/model.py --stage 7
python analysis/crossover.py --stage 7
```
**What it does** (report chapter 4, Eq. 1-10): reads your measured inputs (Stage 1 LAN table in `results/stage1.csv`, PLAIN baseline compute time, link settings of each run), fits seven free parameters by non-negative least squares, and writes:
- `results/model_params.json`: fitted parameters and fit quality.
- `results/model_fit_cells.csv`: per cell measured vs predicted control plane, data plane, total.
- `results/model_cv.csv`: **leave-one-profile-out validation**: the model is refitted without one network profile and must predict it.
- `results/model_predictions.csv`: predicted inflation (vs K1 and vs PLAIN) for all profiles, C in {5,10,20}, R in {10,50,100}, both modes, resumption off/on.
- `results/crossover.csv` and the printed "threshold agreement": measured versus predicted crossing of 1 %, 5 %, 10 %.
- `results/plots/model_pred_vs_meas.png`: predicted vs measured scatter (points should lie near the diagonal).

**Fitted parameters and their meaning** (put in Table 9):

| Parameter | Meaning |
|---|---|
| `kappa_reg` | extra round trips of connection set-up and Flower registration (about a few RTTs) |
| `tau_cp` | expected stall (s) when a handshake segment is lost (expected of the order of the minimum RTO, 0.2 s) |
| `kappa_pay_pers`, `kappa_pay_trans` | round trips per round for the payload transfer on warm (persistent) vs cold (transient) connections |
| `theta_ser`, `theta_tls` | processing cost per MB (proxy/serialisation, extra TLS cost) |
| `tau_data` | expected stall (s) when a payload segment is lost |

**How to judge the model (honestly):**
- Read `fit_quality`: MAPE (mean error in %), RMSE (s), R^2 for control plane, data plane and total. A total-time MAPE below about 10-15 % with R^2 close to 1 is good; larger errors are *findings*: look at `model_fit_cells.csv` and find which profile/config is badly predicted, and write why (for example loss on the client-to-server direction not modelled).
- MAPE of a component that is tiny (data plane on the LAN) can look huge (100 %+) while the absolute error is a few milliseconds. Report RMSE in seconds alongside.
- Read `model_cv.csv`: error when predicting a profile the model never saw. This is the real test; also try holding out the most extreme profile (LOSS5), it is in the table.
- Compare `meas` and `pred` for `hs_s2c_bursts`: the model says an extra RTT appears only when the flight exceeds IW x MSS (about 14 KB at IW=10). Your Stage 6 sweep tells whether that held.

**Break-even/crossover (Eq. 9 and 10):**
- Persistent connections: overhead should *shrink* as rounds grow (overhead above the threshold only for R below R*).
- Transient connections: overhead does *not* shrink with R and instead grows with RTT and loss.
Check both claims against `crossover.csv` (columns `meas_*` and `pred_*`) and state agreement or disagreement.

> **DOCUMENT NOW (Stage 9)**
> - Table 9 (parameters), Table 10 (validation: in-sample and leave-one-profile-out), Table 11 (crossover), Figure (c) predicted vs measured, Figure (d) predicted overhead versus RTT and loss.
> ```bash
> python3 tools/log_obs.py --stage 9 --kind measurement "Model fit: control plane MAPE <..> %, data plane <..> %, total <..> % (R2 <..>). Parameters: kappa_reg <..>, tau_cp <..> s, kappa_pay pers/trans <..>/<..>, tau_data <..> s."
> python3 tools/log_obs.py --stage 9 --kind measurement "Leave-one-profile-out total MAPE: LAN <..>, WAN50 <..>, WAN100 <..>, LOSS1 <..>, LOSS3 <..>, LOSS5 <..> %."
> python3 tools/log_obs.py --stage 9 --kind measurement "Crossover: measured and predicted agree in <..> % of cells at theta 1/5/10 %."
> python3 tools/log_obs.py --stage 9 --kind anomaly "<largest model errors and your explanation>"
> ```
> - Commit: `git add -A && git commit -m "Stage 9: analytical model fitted and validated" && git push`

---

## 5. Stage 10 - Mitigation experiments (modelling and mitigating fragmentation and connection dynamics)
Mitigations: **(M1)** persistent vs transient and **(M2)** resumption are already inside Stage 7. **(M3)** larger initial window, **(M4)** lower minimum RTO, **(M5)** combined are new. Run them on the hardest conditions (high RTT / loss), transient mode, for K1, H2 and P1 (so that the effect on the large certificate flight is visible against K1).

```bash
tmux attach -t matrix || tmux new -s matrix
cd ~/pqfl
# M3: initial congestion window (default 10 is the Stage 7 baseline)
for iw in 4 20 32; do
  sudo venv/bin/python controller/matrix.py --stage 10 --cfgs K1 H2 P1 --modes reconnect --resumes off \
       --profiles WAN100 LOSS3 --clients 10 --rounds 10 --repeats 10 --initcwnd $iw
done
# M4: minimum retransmission timeout (default 200 ms is the Stage 7 baseline)
for rto in 100 50; do
  sudo venv/bin/python controller/matrix.py --stage 10 --cfgs K1 H2 P1 --modes reconnect --resumes off \
       --profiles LOSS3 LOSS5 --clients 10 --rounds 10 --repeats 10 --rto-min-ms $rto
done
# M5: combined (resumption ON + initcwnd 32 + rto_min 50 ms)
sudo venv/bin/python controller/matrix.py --stage 10 --cfgs K1 H2 P1 --modes reconnect --resumes on \
     --profiles WAN100 LOSS3 LOSS5 --clients 10 --rounds 10 --repeats 10 --initcwnd 32 --rto-min-ms 50
```
Then compare with the baseline and with the model prediction:
```bash
python analysis/mitigation.py --base-stage 7 --mit-stage 10
```
Outputs: `results/mitigation.csv` (each mitigation vs the baseline of the same condition: mean difference, 95 % CI, %, significance) and `results/mitigation_model_check.csv` (predicted vs measured epoch time for the TCP-level mitigations, with error %).

Interpretation guide:
- **Initial window:** helps only if the flight did not fit (bursts > 1 at the default). If bursts were already 1, expect no gain; that confirms the model.
- **Minimum RTO:** expected to reduce the tail (p95/p99) mainly under loss, because a lost handshake segment waits for the timer. Check the pooled handshake p99 with `python analysis/stats.py --stage 10` (it reads the stage-10 runs separately).
- **Resumption:** removes the certificate flight but not the key-share (PSK-DHE); read the Stage 1 `resume=True` rows.
- **Combined:** compare with the sum of single effects.
- **Key question for the conclusion (RQ5):** is resumption alone enough, or is something else needed? Answer only from numbers.

> **DOCUMENT NOW (Stage 10)**
> Table 12 of the report from `mitigation.csv`, and observations such as:
> ```bash
> python3 tools/log_obs.py --stage 10 --kind measurement "LOSS3, H2 transient: baseline <..> s; initcwnd 20: <..> s (<..> %, CI <..>); rto_min 50 ms: <..> s (<..> %); resumption on: <..> s; combined: <..> s. K1 same: <..>."
> python3 tools/log_obs.py --stage 10 --kind measurement "Model predicted initcwnd/rto effect <..> %, measured <..> % (err <..> %)."
> python3 tools/log_obs.py --stage 10 --kind decision "Recommended configuration for edge FL: <..> because <numbers>."
> ```
> Commit: `git add -A && git commit -m "Stage 10: mitigation experiments" && git push`

---

## 6. Stage 11 - Open-source release of pqflwr (professor's Step 3)

### 11.1 Repository contents (already prepared in the update)
`README.md` (overview, quick start, repo layout, result columns, limitations), `Makefile` (one-command targets), `requirements.txt` (pinned), `env/` (automated builds of OpenSSL 3.5.x and nginx, netns), `netem/` (netem and TCP-knob scripts), `fl/prepare_data.py` (CIC-IDS2017 preprocessing, also `--synthetic`), `tests/` and `.github/workflows/ci.yml` (CI), `LICENSE` (MIT), `CITATION.cff`, `docs/` (architecture, timeline, flow figures).

### 11.2 Add the final results and your own text
```bash
git add results/stats_cells.csv results/stats_vs_K1.csv results/model_params.json results/model_cv.csv \
        results/model_fit_cells.csv results/model_predictions.csv results/crossover.csv results/mitigation.csv \
        results/stage1.csv results/plots docs
git add -A
```
(Raw `runs/` and pcaps stay out of git; offer them as a release attachment or archive, e.g. Zenodo.)
Open `README.md`, replace "pqflwr authors" in `CITATION.cff` with your names, and add one short results paragraph with the headline numbers from your own tables.

### 11.3 Prove reproducibility on a clean checkout
```bash
cd ~ && rm -rf pqflwr_clean && git clone https://github.com/prishsha/pqflwr.git pqflwr_clean && cd pqflwr_clean
python3 -m venv venv && . venv/bin/activate && pip install -r requirements.txt
python -m pytest -q tests                                  # 4 passed
python fl/prepare_data.py --synthetic
python controller/run_experiment.py --cfg K1 --clients 3 --rounds 2 --local-test --stage ci
for f in env/*.sh netem/*.sh pki/*.sh *.sh; do bash -n $f && echo "syntax ok: $f"; done
```
For a stronger test, create a second WSL distro (`wsl --install -d Ubuntu-24.04 --name pqtest` or a cloud VM), clone the repo and follow the README quick start from scratch up to `bash stage0.sh`. Write down every step that needed a fix, and fix the README.
On GitHub open the **Actions** tab: the `ci` workflow must be green (unit tests + FL smoke test).

### 11.4 Tag the release
```bash
cd ~/pqfl
git add -A && git commit -m "Release: documentation, results tables, README" 
git tag v1.0 && git push && git push --tags
```
On GitHub: Releases -> Draft a new release -> choose `v1.0` -> attach `evidence_stage7.zip` if small enough. Set the repository description and topics (post-quantum, tls, federated-learning, flower, intrusion-detection).

> **DOCUMENT NOW (Stage 11)** `python3 tools/log_obs.py --stage 11 --kind verification "Clean clone: tests pass, smoke test passes, CI green; v1.0 tagged at <commit>."` Report chapter 7: the repository layout and reproduction workflow are already written; add the commit hash and release URL.

---

## 7. Fill the report (`PQ-TLS_Edge_FL_Report_v2.docx`)
| Report chapter | Fill with |
|---|---|
| 8.1 Pilot | Your Stage 0-5 tables and plots (keep: they are the ideal-LAN baseline) |
| 8.2 Decomposition | Table 4 + stacked plots (Stage 8) |
| 8.3 Statistics | Tables 5, 6, 7 (Stage 8) |
| 8.4 Fragmentation | Table 8 from Stage 6 sweeps |
| 8.5 Model | Tables 9, 10 + predicted vs measured plot (Stage 9) |
| 8.6 Crossover | Table 11 from `crossover.csv` |
| 8.7 Mitigation | Table 12 from `mitigation.csv` |
| 8.8 Discussion | Answer RQ1-RQ6 from numbers; state where the model failed |
| 9 Conclusion | The mitigation recommendation, limitations, future work |
| Chapter 5/6 | Replace any item that you changed (for example profiles or repeats) |
| Limitations | WSL2 VM, one host, server-side loss only, CPU time not cycles, Flower 1.13.1 classic API, small MLP |

**Final checklist before you send it to your guide**
- [ ] every cell of the matrix has >= 10 runs (20 for decisive cells): `python tools/check_runs.py --stage 7`
- [ ] all tables report mean, SD, 95 % CI, p95, p99
- [ ] control plane and data plane reported separately in every main table/plot
- [ ] fragmentation claim backed by bursts, flight span, retransmissions (Stage 6 table)
- [ ] model validated on held-out profiles; failures explained
- [ ] mitigations compared with the baseline of the same condition, with CIs
- [ ] repo public, CI green, release tagged, README reproduces from a clean clone
- [ ] observation log (`observations/OBSERVATIONS.md`) has entries for every stage

---

## Appendix A: Troubleshooting (new items; the old table still applies)
| Symptom | Fix |
|---|---|
| `ERROR: network emulation (netem) is not available` | Do Appendix B, or run Stages 6-10 on a cloud Ubuntu VM |
| `route tuning failed` | Run `bash env/04_netns_up.sh` again; check `sudo ip netns exec srv ip route show`; if the route shows `proto kernel` with a different source, paste it here |
| matrix runner prints `FAILED` for many runs | Read `results/failed.log` (last lines of the error); typical: leftover processes -> `sudo pkill nginx; sudo pkill -f fl/server.py; sudo pkill -f fl/client.py` and rerun the same command |
| A transient run is extremely slow with LOSS5 | Expected for a few runs (SYN retransmission 1 s, RTO). If a single run takes more than 10 minutes, Ctrl+C the matrix, rerun; the failed run is simply repeated |
| `stats.py`: KeyError for a column | You are reading old (pilot) rows: use `--stage 7`; old runs lack the new columns |
| `model.py`: "no such cfg" or empty | `results/stage1.csv` must contain the LAN rows (delay 0, loss 0) for K1/H1/H2/P1 full and resumed (section 6.6 a) |
| Model error is huge on data plane in LAN | Percent error of a tiny quantity; look at RMSE in seconds |
| `data_total_s` slightly negative in some runs | Timer noise in tiny rounds; keep the data, report it; if many are negative tell me |
| Windows slept during a run | Mark the interval; delete suspect runs (`runs/<id>` and its row in `results/runs.csv`) and rerun the matrix command |
| `git push` rejected | `git pull --rebase` then `git push` |

## Appendix B: Build a WSL2 kernel with netem (only if `FAIL netem`)
About 30-60 minutes, ~10 GB disk.
```bash
sudo apt-get install -y build-essential flex bison dwarves libssl-dev libelf-dev bc git
cd ~ && uname -r
git clone --depth 1 https://github.com/microsoft/WSL2-Linux-Kernel.git && cd WSL2-Linux-Kernel
./scripts/config --file Microsoft/config-wsl -e NET_SCH_NETEM -e NET_SCHED
make KCONFIG_CONFIG=Microsoft/config-wsl olddefconfig
make -j4 KCONFIG_CONFIG=Microsoft/config-wsl
mkdir -p /mnt/c/wsl-kernel && cp arch/x86/boot/bzImage /mnt/c/wsl-kernel/bzImage
```
In Windows, edit `C:\Users\<YourWindowsName>\.wslconfig` and add under `[wsl2]`:
```
kernel=C:\\wsl-kernel\\bzImage
```
Then PowerShell: `wsl --shutdown`; reopen Ubuntu; `uname -r` should show the new kernel; run `bash env/00_check_system.sh` and `bash env/04_netns_up.sh`. If it does not boot, delete the `kernel=` line, `wsl --shutdown`, and use a cloud VM for the netem stages. In the report state the kernel version used.
