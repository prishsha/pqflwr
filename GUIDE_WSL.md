# Step-by-step guide (WINDOWS + WSL2 version): PQ-TLS overhead in Federated Learning

Everything below is copy-paste. All code is already written and is inside the `pqfl/` folder you received
(the FL part was tested; the nginx / namespace / tcpdump parts need your machine, so Stage 0 is also your shake-down test).

**How to read this guide**
- Lines in grey code blocks are typed in the terminal, one block at a time.
- **DOCUMENT NOW** boxes tell you exactly what to save, screenshot and write. Do them immediately; do not wait until the end.
- If a command fails, go to section 15 (Troubleshooting) first. If still stuck, copy the full error text and bring it back to me here.

---

## 0. What you will end up with
1. An Ubuntu machine with OpenSSL 3.5.x and nginx built by you.
2. A virtual client-server network (two "network namespaces" joined by a cable, MTU 1500, optional delay and loss).
3. A Flower federated-learning job whose traffic goes through TLS proxies (K1, H1, H2, P1) or no TLS (PLAIN).
4. Captured packets, CSV results, tables and plots, plus an observation log.

**Design in one picture**
```
Flower client --plain--> client nginx --TLS 1.3 over veth--> server nginx --plain--> Flower server
(inside namespace "cli")                                       (inside namespace "srv")
```
Flower never does TLS itself. Only the two nginx programs (built with OpenSSL 3.5.x) do. That is what makes the four configurations a fair comparison.

**WSL note:** you are on Windows, so Ubuntu runs inside WSL2 (a small virtual machine managed by Windows). Everything in this guide is typed in the **Ubuntu (WSL) terminal**, not in PowerShell, except section 1. Add to your report's Limitations: "experiments ran in WSL2 on a Windows host (Hyper-V virtual machine)".

**Important honesty note for your report:** everything runs on ONE machine (client and server in separate namespaces), not two cloud machines like the reference thesis. Write this in "Limitations". It is still a valid controlled experiment if you say so.

**Two deliberate simplifications (write them in the report, section "Methodology")**
- Flower version is pinned to 1.13.1 and uses its classic `start_server` / `start_client` API. It is the simplest API that works over a real network.
- The model is a small NumPy MLP (78 -> 128 -> 64 -> 2), not PyTorch. It starts fast and has a known size (about 74 KB per direction).

---

## 1. Set up Ubuntu 24.04 in WSL2 (30-45 min)
**You need:** Windows 11 (or Windows 10 22H2), virtualization enabled in BIOS, **16 GB RAM** (WSL gets 8 GB), 40 GB free disk, power plugged in.

**1a. Install Ubuntu (Windows PowerShell as Administrator)**
```powershell
wsl --install -d Ubuntu-24.04
wsl --update
```
Restart Windows if asked. Open "Ubuntu 24.04" from the Start menu; it asks you to create a Linux username and password (remember the password; `sudo` needs it). Check it is WSL **2**:
```powershell
wsl -l -v          # VERSION must be 2.  If it says 1:  wsl --set-version Ubuntu-24.04 2
```

**1b. Give WSL 4 cores and 8 GB (Windows).** Create the file `C:\Users\<YourWindowsName>\.wslconfig` (Notepad; make sure the name does not end in .txt) with:
```
[wsl2]
memory=8GB
processors=4
swap=4GB
```
Then in PowerShell: `wsl --shutdown`, and reopen Ubuntu. Check inside Ubuntu:
```bash
nproc               # 4
free -h             # about 7-8 GB total
lsb_release -ds     # Ubuntu 24.04...
uname -r            # contains "microsoft-standard-WSL2"
```

**1c. Copy the project into Linux (Ubuntu terminal).** Put `pqfl.zip` in your Windows Downloads folder, then:
```bash
cp /mnt/c/Users/<YourWindowsName>/Downloads/pqfl.zip ~/
sudo apt-get update && sudo apt-get install -y unzip tmux
cd ~ && unzip pqfl.zip && cd ~/pqfl
```
**Work only inside `~/pqfl` (the Linux disk).** Never run the project from `/mnt/c/...`: it is slow and breaks file permissions. Whenever a command says "from the project folder", run `cd ~/pqfl` first. Use `tmux` for long runs: type `tmux`, start the run, detach with `Ctrl+B` then `D`, return with `tmux attach`.

**1d. Rules while experiments run (WSL shares your PC):** keep the laptop plugged in, set the Windows power mode to "Best performance", disable sleep, close browsers/games/video calls, and do not start Windows updates. If Windows sleeps, WSL pauses and the run is ruined (the numbers become invalid; just repeat it).

> **DOCUMENT NOW (Observation 0: machine)**
> Screenshot the outputs of `nproc`, `free -h`, `lsb_release -ds`, `uname -r`, plus your Windows version (`winver`) and CPU model (`lscpu | grep "Model name"`).
> `python3 tools/log_obs.py --stage 0 --kind setup "Host: Windows <version>, CPU <model>; WSL2 Ubuntu 24.04, kernel <uname -r>, 4 cores, 8 GB RAM assigned via .wslconfig."`
> Report: Table 3 (hardware configuration) and Limitations.

---

## 2. Install system packages and Python packages (10 min)
```bash
cd ~/pqfl
bash env/01_install_deps.sh
```
The last lines must show `flwr 1.13.1`, `numpy 1.26.4`. If `flwr==1.13.1` is not found, tell me; do not change versions on your own.

## 2b. WSL feature check (2 min) - do not skip
```bash
cd ~/pqfl
bash env/00_check_system.sh
```
Expected: `PASS network namespaces`, `PASS veth pair`, `PASS tools ...`. The line to look at is **netem**:

- **`PASS netem`** -> perfect, everything in this guide works as written.
- **`FAIL netem`** -> the default WSL2 kernel was built without delay/loss emulation (this is common). Everything still works **except** the RTT and packet-loss sweeps (Stage 1 section 10.2 and the optional netem cells in section 12). Without them every connection has an RTT of about 0.1 ms. You then have three choices; pick one and tell your guide:
  - **A. Skip the sweeps** and state it in Limitations ("no WAN emulation; RTT about 0.1 ms"). This is acceptable for the main study (clients x rounds x configuration) but you can then not answer the packetisation/RTT part of RQ2 beyond the baseline.
  - **B. Do only the sweeps on a small Ubuntu cloud VM** (e.g. a 4-vCPU Ubuntu 24.04 machine for a few hours) using the original guide; everything else stays in WSL.
  - **C. Build a WSL kernel with netem** (about 30-60 min, steps in Appendix B). 

If `network namespaces` or `veth` fail: run `wsl --update` in PowerShell, `wsl --shutdown`, reopen Ubuntu, and run the check again; if it still fails, paste the output here.

> **DOCUMENT NOW (Observation 0b)**
> `python3 tools/log_obs.py --stage 0 --kind setup "System check: namespaces PASS, veth PASS, netem <PASS/FAIL>. Decision: <A/B/C or none needed>."`

---

## 3. Build OpenSSL 3.5 (10-15 min)
Open https://github.com/openssl/openssl/releases and note the newest **3.5.x** version (the thesis used 3.5.7). Then:
```bash
bash env/02_build_openssl.sh 3.5.4        # replace 3.5.4 with the newest 3.5.x if you want
```
At the end it prints the OpenSSL version, the ML-KEM algorithms and the ML-DSA algorithms. You must see
`ML-KEM-768`, `X25519MLKEM768` and `ML-DSA-65` in the lists.

> **DOCUMENT NOW (Observation 1: environment)**
> - Screenshot the final output (version + KEM + signature lists) -> save as `observations/fig_openssl.png`.
> - Run: `python3 tools/log_obs.py --stage 0 --kind setup "OpenSSL <version> built from source in /opt/openssl-3.5; ML-KEM-768, X25519MLKEM768, ML-DSA-65 present natively in default provider."`
> - Report section: 5 (System Architecture) and the thesis-style "Implementation" description.

## 4. Build nginx (10 min)
```bash
bash env/03_build_nginx.sh
```
The last lines show nginx's build options. You must see `built with OpenSSL 3.5.x`.

> **DOCUMENT NOW (Observation 2)**
> - Screenshot of `nginx -V` output -> `observations/fig_nginx.png`.
> - `python3 tools/log_obs.py --stage 0 --kind setup "nginx 1.27.4 built statically with OpenSSL <version>; stream + stream_ssl modules enabled."`

**Optional (only if your guide insists on oqs-provider):** In OpenSSL 3.5, ML-KEM and ML-DSA are built in, so oqs-provider is *not* in the data path of K1/H1/H2/P1. You can build it later (Appendix A). Say this explicitly in the report.

## 5. Create the virtual network (2 min)
```bash
bash env/04_netns_up.sh
```
It must end with 2 successful pings. (Ping works here because these are our own namespaces.)
Check the cable really has a normal MTU:
```bash
sudo ip netns exec cli ip link show veth-c | grep mtu        # must say mtu 1500
```
This matters: on the normal loopback interface the MTU is 65536 and big certificates would never be split into packets.

> **DOCUMENT NOW (Observation 3)**
> `python3 tools/log_obs.py --stage 0 --kind setup "Two namespaces (cli 10.10.0.2, srv 10.10.0.1) joined by veth, MTU 1500, TSO/GSO/GRO off. netem applied on both sides (delay 0, loss 0 by default)."`
> Report: Limitations (single-host virtual network) and Section 5.

If you reboot Windows, restart WSL (`wsl --shutdown`) or things look odd, run `bash env/04_netns_up.sh` again (namespaces are lost on restart).
If netem is unavailable the script prints nothing special here; that is fine for now.

## 6. Create the certificates (1 min)
```bash
bash pki/make_certs.sh
cat pki/certs/cert_sizes.txt
```
You will see the DER size of each certificate and its signature algorithm (`ecdsa-with-SHA256`, `ML-DSA-65`). Both `verify` lines must say `OK`.

> **DOCUMENT NOW (Observation 4: certificate sizes - first real result)**
> Copy the sizes into a table: ECDSA CA/leaf and ML-DSA-65 CA/leaf (bytes). Chain size = CA + leaf.
> `python3 tools/log_obs.py --stage 1 --kind measurement "Cert DER sizes: ecdsa CA=<..> leaf=<..>; mldsa65 CA=<..> leaf=<..> bytes."`
> Report: Table 3 (Stage 1) column "Cert chain (B)".

## 7. Get the dataset (CIC-IDS2017) (20 min)
1. Open the official page https://www.unb.ca/cic/datasets/ids-2017.html and download **"MachineLearningCSV"** (the 8 CSV files; fill the short form if asked).
2. Put the 8 CSV files in `~/cicids2017/` on the machine.
3. Prepare the data (cleans NaN/inf, makes benign-vs-attack labels, standardises, 80/20 split, uses at most 300,000 rows):
```bash
. venv/bin/activate
python fl/prepare_data.py --csv-dir ~/cicids2017
```
No dataset yet? Test the whole pipeline first with fake data: `python fl/prepare_data.py --synthetic`. **Never report results from fake data.** Re-run the real preparation before Stage 0 results you will report.

> **DOCUMENT NOW (Observation 5: dataset)**
> Copy the printed line "rows after cleaning ... attack fraction ...", train/test sizes, and the number of features.
> `python3 tools/log_obs.py --stage 0 --kind setup "CIC-IDS2017: <rows> rows after cleaning, attack fraction <..>, subsampled to <..>, features=<..>, 80/20 split, binary label, IID client shards."`
> Report: Methodology (dataset and model paragraph). Model size: 73,992 bytes one way (shown in every run's `model_bytes_one_way`).

## 8. Smoke test of the FL part only (2 min)
```bash
. venv/bin/activate
python controller/run_experiment.py --cfg K1 --clients 3 --rounds 3 --local-test --stage test
```
It must print a JSON block with `final_f1` around 0.7-0.99 and no errors. (This test does not use TLS.) Delete the test line from `results/runs.csv` afterwards: `rm results/runs.csv`.

---

## 9. STAGE 0 - Proxy path and handshake-count experiment  (your supervisor wants this FIRST)
Goal: find out how many TCP connections and TLS handshakes a Flower run **really** produces. Do not guess.

### 9.1 One run by hand first (to catch setup errors)
```bash
sudo venv/bin/python controller/run_experiment.py --cfg K1 --clients 5 --rounds 10 --mode native --stage 0
```
It starts: two nginx proxies, packet capture, 1 Flower server, 5 Flower clients; waits until finished; analyses the capture; prints a JSON block.
Look at these keys: `n_syn` (TCP connections), `n_streams`, `n_clienthello` (TLS handshakes), `n_rst` (resets), `expected_cxr` (= clients x rounds = 50), `hs_mean_ms`, `tcpdump_dropped` (must be 0).

### 9.2 Prove the traffic really is TLS 1.3 with the right algorithms
Every run keeps its evidence in `runs/<run_id>/`. Look at the newest one:
```bash
RUN=$(ls -d runs/* | tail -1); echo $RUN
cat $RUN/srv_access.log | head            # last columns: TLSv1.3, TLS_AES_256_GCM_SHA384, session reused (0/1)
head -5 $RUN/streams.csv                  # one line per TCP connection
```
Also confirm the group by a direct handshake (run Stage 1 once later) - `s_client_first.txt` lists "Negotiated TLS1.3 group".

### 9.3 Run the whole Stage 0 set (about 10 minutes)
```bash
bash stage0.sh
```
It runs: K1 native x3 repeats, K1 reconnect, PLAIN native, then prints the table.
- **native** = Flower behaves normally (connection probably stays open).
- **reconnect** = a new Flower session for every round, so every client makes a new TCP+TLS connection each round (the worst-case bound).

### 9.4 Look at the packets yourself (screenshot for the report)
```bash
RUN=$(ls -d runs/*native* | head -1)
tshark -r $RUN/capture.pcap -d tcp.port==4431,tls -Y "tls.handshake.type==1" -T fields -e frame.time_relative -e tcp.stream -e ip.src -e ip.dst | head -20
```
Each line is one ClientHello. Count them: `... | wc -l`. Compare with `n_clienthello` in the result. Optionally open the pcap in Wireshark (copy it to Windows with `cp runs/<run_id>/capture.pcap /mnt/c/Users/<YourWindowsName>/Downloads/`) and screenshot "Statistics -> Conversations -> TCP".

> **DOCUMENT NOW (Stage 0 - most important documentation)**
> Fill this table (Report: Table 2 in section 7.1):
>
> | Run | C | R | Mode | TCP connections (n_syn) | TLS handshakes (n_clienthello) | per client | equals C x R? | notes |
>
> Then log at least these observations (replace the <> parts):
> ```bash
> python3 tools/log_obs.py --stage 0 --cfg K1 --run <run_id> "Native C=5 R=10: <n_syn> TCP connections, <n_clienthello> TLS handshakes, <n_rst> resets. C x R = 50. => Flower <does / does not> create a new handshake each round."
> python3 tools/log_obs.py --stage 0 --cfg K1 --run <run_id> "Repeats 1-3 gave <a>,<b>,<c> handshakes (stable / not stable)."
> python3 tools/log_obs.py --stage 0 --cfg K1 --run <run_id> "Reconnect mode C=5 R=10: <n> handshakes (expected ~50)."
> python3 tools/log_obs.py --stage 0 --cfg PLAIN --kind verification "PLAIN capture shows no TLS; connections = <n>."
> python3 tools/log_obs.py --stage 0 --kind anomaly "<anything unexpected, e.g. extra connections, resets, timeouts>"
> ```
> Also save: the screenshot from 9.4, and `zip -r stage0_evidence.zip runs/*_s0_* results/runs.csv`.
> Report: section 7.1 + one paragraph "RQ1 answer" (the measured number, and what it depends on).

### 9.5 STOP here and send your supervisor the Stage 0 table
He asked for the measured number first. After his reply you finalise how much of the matrix you run (section 12).

---

## 10. STAGE 1 - Handshake characterisation (size, packets, RTT, retransmissions)
This measures isolated handshakes (300 per configuration) with `openssl s_client`, captured at packet level.

### 10.1 Baseline (same-machine network, RTT about 0.1 ms)
```bash
for c in K1 H1 H2 P1; do sudo venv/bin/python stage1/handshake_loop.py --cfg $c --n 300; done
```
Each run prints a JSON block and the evidence lines (protocol, cipher, negotiated group, peer signature type, verify code). Results are appended to `results/stage1.csv`.
Columns to copy into your table (Report Table 3):

| What | Column |
|---|---|
| handshake time (ms) | `hs_mean_ms`, `hs_median_ms`, `hs_p95_ms`, `hs_p99_ms`, `hs_std_ms` |
| bytes on the wire (both directions, whole handshake) | `hs_frame_bytes_mean` |
| TLS payload client->server / server->client | `hs_payload_c2s_mean`, `hs_payload_s2c_mean` |
| number of server data segments | `hs_segments_s2c_mean` |
| time the server's flight needs (>= RTT means it had to wait for the client: extra round trip) | `flight_span_ms_mean` |
| RTT measured from SYN to SYN-ACK | `rtt_syn_ms_mean` |
| retransmissions | `retx_total`, `retx_hs_mean`, `server_tcp_retrans_delta` |
| certificate sizes | `cert_leaf_der`, `cert_ca_der` |

How to read `flight_span_ms_mean`: it is the time between the first and last server packet before the client answers. If it is close to 0, the whole server flight went out at once. If it is about one RTT or more, the server had to wait for the client's ACK (initial congestion window reached) -> that is the packetisation effect your supervisor asked about. You measure it; you do not assume a threshold.

### 10.2 RTT and loss sweep (for the packetisation question)
**Needs netem (section 2b). If your check said `FAIL netem` and you chose option A, skip this whole subsection and write that decision down; if you try anyway, the script stops with the error "netem is not available".**
`--delay-ms D` adds D ms each way, so RTT = 2 x D.
```bash
for d in 0 10 25 50; do for c in K1 H2 P1; do
  sudo venv/bin/python stage1/handshake_loop.py --cfg $c --n 300 --delay-ms $d --tag sweep_rtt > /dev/null; done; done
for l in 1 3 5; do for c in K1 H2 P1; do
  sudo venv/bin/python stage1/handshake_loop.py --cfg $c --n 300 --delay-ms 10 --loss $l --tag sweep_loss > /dev/null; done; done
```
Check it worked: `rtt_syn_ms_mean` in `results/stage1.csv` should be about 2 x D (+0.1).
After the sweep, reset the network: `bash netem/set_netem.sh 0 0`.

> **DOCUMENT NOW (Stage 1)**
> - Table 3 (baseline) and a second table "by RTT" and "by loss" from `results/stage1.csv` (open it with LibreOffice/Excel or `column -s, -t < results/stage1.csv | less -S`).
> - Observations, for each configuration:
> ```bash
> python3 tools/log_obs.py --stage 1 --cfg H2 --run <run_dir> "Handshake <hs_frame_bytes_mean> B on the wire, server sent <hs_segments_s2c_mean> segments, flight span <..> ms vs RTT <..> ms => extra round trip: yes/no. Retransmissions: <..>."
> python3 tools/log_obs.py --stage 1 --kind verification --cfg H2 "s_client confirmed group X25519MLKEM768, signature mldsa65, Verify return code 0 (file runs/<..>/s_client_first.txt)."
> python3 tools/log_obs.py --stage 1 --kind decision "Chose RTT profile list {0,20,50,100} ms and loss {0,1,3,5}% because <reason>."
> ```
> - Compare with the thesis: thesis K1 ~0.92 ms and H2 ~2.25 ms, K1 total 1,261 B vs H2 12,022 B (different machine: write whether you agree and why it may differ).
> - Also record the TCP initial window your machine uses: `sudo ip netns exec srv ip route show` (if no `initcwnd` appears, Linux default = 10 segments; say that this is the value used).
> - Report: section 7.2.
> **STOP and share Stage 1 with your supervisor before the big runs.**

---

## 11. STAGE 2 - FL baseline without TLS (PLAIN)
```bash
bash run_matrix.sh 2 native    off "PLAIN" "5 10 20" "10 50 100" 5
bash run_matrix.sh 2 reconnect off "PLAIN" "5 10"    "10 50"     3
```
(`run_matrix.sh` arguments: stage, mode, resumption, configs, client counts, round counts, repeats.)
Time: native cells take seconds to a minute each. Reconnect cells take longer because every round starts new processes (roughly 5 s per round).

> **DOCUMENT NOW (Stage 2)** - baseline numbers per (C,R): `logical_total_s`, `setup_total_s`, `rounds_total_s`, `update_bytes_per_client_round`, `final_f1`.
> `python3 tools/log_obs.py --stage 2 --cfg PLAIN "Baseline C=<..> R=<..>: total <..> s (setup <..> s, rounds <..> s), F1 <..>, update <..> B per client per round, run-to-run spread <..>."`
> Report: Layer 3 (FL overhead) description; the "FL baseline" row of your results.

## 12. STAGE 3 - The TLS matrix
First agree with your supervisor how much to run (full matrix is many hours). Suggested order:
```bash
tmux                                         # so the run survives if your connection drops
# (a) native mode, all cells, 3 repeats   (about 1-2 h)
bash run_matrix.sh 3 native    off "K1 H1 H2 P1" "5 10 20" "10 50 100" 3
# (b) reconnect mode, smaller cells first   (hours)
bash run_matrix.sh 3 reconnect off "K1 H1 H2 P1" "5 10"    "10 50"     3
# (c) only if time allows: reconnect with more clients/rounds
bash run_matrix.sh 3 reconnect off "K1 H1 H2 P1" "20"      "10 50"     3
bash run_matrix.sh 3 reconnect off "K1 H1 H2 P1" "5"       "100"       3
```
Order of cells is random inside each repeat (this spreads cloud noise evenly). If a run says `!!! run failed`, look in that run's folder; failed runs simply have no result row.

Optional (needs netem): network profiles on a few cells only (decide the profiles after Stage 1):
```bash
bash run_matrix.sh 3 reconnect off "K1 H2 P1" "5" "10" 3 25 1      # one-way delay 25 ms (RTT 50), 1% loss
bash netem/set_netem.sh 0 0
```
**Rules while running:** do nothing else heavy on the machine; never mix runs from a different machine/day without noting it; a run with `tcpdump_dropped > 0` is invalid (the summary script skips it automatically).

> **DOCUMENT NOW (Stage 3), once at the start and once per batch**
> ```bash
> python3 tools/log_obs.py --stage 3 --kind decision "Matrix run: modes=<..>, C=<..>, R=<..>, repeats=<..>, random order, resume=off."
> python3 tools/log_obs.py --stage 3 --kind anomaly "<failed runs, outliers, unexpected handshake counts, timeouts>"
> ```
> Then run section 14 (summary) and record the first overhead numbers.

## 13. STAGE 4 - Session resumption
### 13.1 Isolated: full vs resumed handshake (per configuration)
```bash
for c in K1 H1 H2 P1; do sudo venv/bin/python stage1/handshake_loop.py --cfg $c --n 300 --resume --tag stage4 > /dev/null; done
```
In `results/stage1.csv` (rows with `resume = True`) check `reused_by_s_client` (should be about 300) and `n_resumed_psk` (ClientHellos that carry a resumption key, seen in the capture). Compare `hs_mean_ms`, `hs_frame_bytes_mean`, `hs_segments_s2c_mean` with the non-resumed rows of the same configuration:
- saving (ms) = hs_mean_ms(full) - hs_mean_ms(resumed)
- saving (bytes) = hs_frame_bytes_mean(full) - hs_frame_bytes_mean(resumed)
- **residual cost** = what is still left on the resumed handshake (it is not zero; measure it).
Look at the resumed handshake size for H1/H2 (X25519MLKEM768) vs K1: if the hybrid key share is still sent, the resumed handshake stays larger.

### 13.2 In the FL job (reconnect mode, because tickets only help when a client reconnects)
```bash
bash run_matrix.sh 4 reconnect on "K1 H1 H2 P1" "5 10" "10 50" 3
```
Check in the result that `n_resumed_psk` is greater than 0 (if it is 0, resumption did not happen - write that down as an observation, it is a finding, not an error; remember all clients connect at the same moment in round 1, so only reconnections can resume).

> **DOCUMENT NOW (Stage 4)**
> Table 5: full vs resumed (ms, bytes, segments, residual). Then:
> ```bash
> python3 tools/log_obs.py --stage 4 --cfg H2 --run <run_dir> "Resumed handshakes: <reused>/<n>; time <full> -> <resumed> ms; bytes <full> -> <resumed>; residual <..>% of full."
> python3 tools/log_obs.py --stage 4 --kind anomaly "<e.g. resumption failed for config X / tickets reused by several clients>"
> ```
> Report: section 7.4 and the answer to RQ4 ("is resumption alone sufficient?").

---

## 14. STAGE 5 - Tables, plots, crossover
```bash
. venv/bin/activate
python analysis/summarize.py
```
Creates `results/summary.csv` and plots `results/inflation_<mode>_res<on/off>.png` (time inflation vs number of rounds, one panel per client count, one line per configuration).

How each of your professor's overhead metrics maps to columns:

| Metric | Where / how |
|---|---|
| **Classical TLS overhead** (K1 vs no TLS) | `inflation_vs_PLAIN_pct` for K1; handshake cost of K1 from `results/stage1.csv`; `cpu_srv_proxy_s`, `cpu_cli_proxy_s` for K1 minus PLAIN |
| **PQ-TLS overhead** (vs K1) | Stage 1 columns of H1, H2, P1 minus K1: handshake time, bytes, segments, retransmissions. Decompose: **H1-K1** = ML-KEM effect, **H2-H1** = ML-DSA effect, **P1-H2** = dropping X25519. In the FL runs: `inflation_vs_K1_pct` |
| **FL overhead** | `setup_total_s`, `rounds_total_s`, `update_bytes_per_client_round`, cumulative bytes = C x R x `update_bytes_per_client_round`, `final_f1` |
| **Cumulative handshake cost** | `n_clienthello` (measured number of handshakes) x `hs_ms`; bytes = `n_clienthello` x `hs_bytes` |
| **Handshake share of useful bytes** | (`n_clienthello` x `hs_bytes`) / (C x R x `update_bytes_per_client_round`) |
| **Handshake count vs C x R** | `hs_per_client_round` (measured fraction) |
| **Crossover** | First (C,R) where `inflation_vs_K1_pct` (or vs PLAIN) reaches 1%, 5%, 10% and the spread over repeats (`logical_sd`) is smaller than the effect. Also compare with `analytic_vs_K1_pct` (the estimate from Stage 1 numbers). If it never reaches 1% in your range, say exactly that, with the largest value you saw |
| **IDS utility** | `final_f1` must be equal across configurations (TLS must not change learning). If not equal, log an anomaly |
| **CPU per handshake** | (`cpu_srv_proxy_s` of config - of PLAIN) / `n_clienthello` |

Notes on definitions (copy into the report):
- `logical_total_s` = connection setup time + sum of round times. It excludes Python start-up time.
- `setup_total_s` per session = from "all clients start connecting" to "last client starts its first training task". It contains the TCP + TLS handshake, the gRPC/HTTP2 setup and Flower registration, plus the slowest client. This is the place where handshake cost shows up in FL.
- Different clients handshake in parallel, so total handshake time summed over clients is a *resource cost*, not the delay you feel. The delay you feel is measured end to end by `logical_total_s`.

> **DOCUMENT NOW (Stage 5)**
> - Save the plots; paste them into the report section 7.3, 7.5, 7.6. Copy `summary.csv` rows into Tables 4 and 6.
> - `python3 tools/log_obs.py --stage 5 --kind decision "Significance thresholds 1/5/10 %; crossover = first cell with inflation >= threshold and > 2 x run-to-run std."`
> - `python3 tools/log_obs.py --stage 5 "Crossover for <cfg>/<mode>: <cell or 'none within tested range'>; largest inflation <..>% at C=<..>, R=<..>."`
> - Write the final answer to each research question (RQ1..RQ5) in section 8 (Conclusion) of the report using only these measured numbers.

---

## 15. Troubleshooting
| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: flwr` | You used the wrong Python. Use `sudo venv/bin/python ...` (runs) or `. venv/bin/activate` first |
| `nginx: [emerg] unknown directive "ssl_conf_command"` or `proxy_ssl_conf_command` | nginx was not built correctly; redo section 4. Bring me the exact error line |
| `nginx (srv) died ...` | Open the two files the message names (`runs/<id>/srv_stderr.log` and `srv_error.log`). Most common: leftover nginx from a failed run -> `sudo pkill nginx` and retry; or a certificate path problem -> redo section 6 |
| `Cannot open network namespace "srv"` | Redo `bash env/04_netns_up.sh` (it is lost after reboot) |
| timeout waiting for processes to become ready | Look at `runs/<id>/s000/server.out` and `client0.out` for the Python error |
| `n_streams = 0` / empty capture | `tcpdump_dropped`/`tcpdump.txt` in the run folder; check that `veth-c` exists: `sudo ip netns exec cli ip link` |
| `tshark failed` | Run `tshark -v`; if missing: `sudo apt-get install -y tshark` |
| `tcpdump_dropped` > 0 | Run is invalid; repeat it. Do not use it |
| Port already in use | `sudo pkill nginx; sudo pkill -f fl/server.py; sudo pkill -f fl/client.py` |
| Flower warnings about deprecated `start_client` | Harmless. Mention "classic API" in the report |
| `Verify return code` not 0 in s_client | CA/server mismatch; redo `bash pki/make_certs.sh` |
| `ERROR: network emulation (netem) is not available` | Your WSL kernel lacks netem. Skip delay/loss runs (option A) or see Appendix B |
| Run suddenly takes far longer / numbers jump | Windows went to sleep, updated, or another app used the CPU. Mark the run invalid and repeat it |
| `wsl --install` says virtualization is disabled | Enable "Virtualization" (Intel VT-x / AMD-V) in the BIOS, and turn on "Virtual Machine Platform" in Windows Features |
| `Cannot open network namespace` right after reopening Ubuntu | WSL restarted: run `bash env/04_netns_up.sh` again |
| Out of memory while building nginx/OpenSSL | Raise `memory=` in `.wslconfig`, or build with fewer jobs: edit `make -j"$(nproc)"` to `make -j2` |
| A run hangs for more than ~10 min | Press Ctrl+C, run the cleanup line above, look at `server.out`, then retry |
| Results look strange (huge spread) | Close other programs; run again; log an anomaly; consider more repeats |

When something fails, copy: (1) the command, (2) the full error, (3) the last 20 lines of the relevant log file, and send it to me.

---

## 16. What evidence to keep (zip it at the end)
```bash
zip -r evidence_all.zip runs results observations pki/certs/cert_sizes.txt
```
`runs/<id>/` contains for every run: `manifest.json` (versions, command), `capture.pcap`, `streams.csv`, nginx logs, per-session Flower logs, `result.json`. Never edit these files by hand.

## 17. Mapping to your report
| Report section | Fill with |
|---|---|
| Methodology / Architecture | sections 0, 3, 4, 5, 7 of this guide, the simplifications, single-host limitation |
| 7.1 Stage 0 | Table 2, the packet screenshot, RQ1 answer |
| 7.2 Stage 1 | Table 3 + RTT/loss tables, RQ2 answer |
| 7.3 Stage 3 | Table 4, plots, RQ3 answer |
| 7.4 Stage 4 | Table 5, RQ4 answer |
| 7.5 Crossover | Table 6, analytic vs measured comparison |
| 8 Conclusion | Findings: handshake count, per-config compounding, resumption, recommendation |
| Limitations | WSL2 virtual machine on a Windows host, single host, simulated clients, software CPU timers (not hardware counters), Flower 1.13.1 classic API, small NumPy MLP |

## Appendix A (optional): oqs-provider
Only if required. Needs cmake, ninja and liboqs 0.15.0; build liboqs from github.com/open-quantum-safe/liboqs, then oqs-provider 0.11.0 against your OpenSSL (`cmake -DOPENSSL_ROOT_DIR=/opt/openssl-3.5 ...`). With OpenSSL 3.5, `openssl list -kem-algorithms -provider oqsprovider` will show it only adds extra algorithms; your four configurations stay on OpenSSL's own ML-KEM/ML-DSA. Document it as "present but not in the data path". Ask me here if you want exact commands.


## Appendix B (optional): build a WSL2 kernel with netem
Only if the check said `FAIL netem` and you want delay/loss emulation. Takes 30-60 min and ~10 GB disk. In the Ubuntu terminal:
```bash
sudo apt-get install -y build-essential flex bison dwarves libssl-dev libelf-dev bc git
cd ~ && uname -r        # note the version, e.g. 6.6.xx.x-microsoft-standard-WSL2
git clone --depth 1 https://github.com/microsoft/WSL2-Linux-Kernel.git && cd WSL2-Linux-Kernel
./scripts/config --file Microsoft/config-wsl -e NET_SCH_NETEM -e NET_SCHED
make KCONFIG_CONFIG=Microsoft/config-wsl olddefconfig
make -j4 KCONFIG_CONFIG=Microsoft/config-wsl
mkdir -p /mnt/c/wsl-kernel && cp arch/x86/boot/bzImage /mnt/c/wsl-kernel/bzImage
```
Then in Windows edit `C:\Users\<YourWindowsName>\.wslconfig` and add this line under `[wsl2]` (double backslashes):
```
kernel=C:\\wsl-kernel\\bzImage
```
In PowerShell run `wsl --shutdown`, reopen Ubuntu, run `uname -r` (it should show the new kernel) and `bash env/00_check_system.sh` again. If it does not boot or the build fails, delete the `kernel=` line, `wsl --shutdown`, and use option A or B instead. If you hit an error, paste it here. In the report state the exact kernel you used.
