### OBS-0001 | stage 0 | - | setup | 2026-10-13 04:26:48
run: `-`

OpenSSL <version> built from source in /opt/openssl-3.5; ML-KEM-768, X25519MLKEM768, ML-DSA-65 present natively in default provider.

### OBS-0002 | stage 0 | - | setup | 2026-10-13 04:39:44
run: `-`

nginx 1.27.4 built statically with OpenSSL <version>; stream + stream_ssl modules enabled.

### OBS-0003 | stage 0 | - | setup | 2026-10-13 04:40:40
run: `-`

Two namespaces (cli 10.10.0.2, srv 10.10.0.1) joined by veth, MTU 1500, TSO/GSO/GRO off. netem applied on both sides (delay 0, loss 0 by default).

### OBS-0004 | stage 1 | - | measurement | 2026-10-13 04:41:06
run: `-`

Cert DER sizes: ecdsa CA=<..> leaf=<..>; mldsa65 CA=<..> leaf=<..> bytes.

### OBS-0005 | stage 0 | - | setup | 2026-10-13 05:06:08
run: `-`

CIC-IDS2017: 2520798 rows after cleaning, attack fraction 0.169, subsampled to 300000 rows, features=70, 80/20 split, binary label, IID client shards.

### OBS-0006 | stage 0 | K1 | measurement | 2026-10-13 05:36:50
run: `20261013-053059_s0_K1_C5_R10_native_resoff_d0_l0_r1`

Native C=5 R=10: 5 TCP connections, 5 TLS handshakes, 1 reset. C x R = 50. Flower does not create a new handshake each round in native mode.

### OBS-0007 | stage 0 | K1 | measurement | 2026-10-13 05:36:50
run: `20261013-053205_s0_K1_C5_R10_native_resoff_d0_l0_r3`

Native repeats 1-3 gave 5, 5, 5 handshakes. Handshake counts were stable.

### OBS-0008 | stage 0 | K1 | measurement | 2026-10-13 05:36:50
run: `20261013-053238_s0_K1_C5_R10_reconnect_resoff_d0_l0_r1`

Reconnect mode C=5 R=10: 50 TCP connections and 50 TLS handshakes, matching expected C x R = 50.

### OBS-0009 | stage 0 | PLAIN | verification | 2026-10-13 05:36:50
run: `-`

PLAIN native capture shows no TLS ClientHello messages; 5 TCP connections.

### OBS-0010 | stage 0 | - | anomaly | 2026-10-13 05:36:50
run: `-`

Native repeat 1 and reconnect mode recorded TCP resets. Counts were 1 and 2 respectively; investigate only if other evidence indicates a problem.

### OBS-0011 | stage 1 | H2 | measurement | 2026-10-13 06:38:03
run: `runs/20261013-061703_sweep_rtt_H2_d50_l0`

300 handshakes; mean handshake latency 111.16 ms, median 104.15 ms, p95 107.13 ms, p99 110.28 ms. Mean handshake wire bytes 12949.86 B; server sent 8 segments; mean flight span 1.82 ms versus SYN RTT 50.16 ms. No TCP retransmissions observed. Extra round trip: not established by these aggregate metrics.

### OBS-0012 | stage 1 | H2 | verification | 2026-10-13 06:38:39
run: `-`

s_client confirmed group X25519MLKEM768, signature mldsa65, TLS 1.3, cipher TLS_AES_256_GCM_SHA384, Verify return code 0 (ok). Evidence: runs/20261013-061703_sweep_rtt_H2_d50_l0/s_client_first.txt.

### OBS-0013 | stage 1 | - | decision | 2026-10-13 06:38:47
run: `-`

Used RTT profiles {0,10,25,50} ms and packet loss {0,1,3,5}%. The RTT sweep measures sensitivity to increasing network delay; the loss sweep measures retransmission and handshake-latency effects under packet loss. Configurations K1, H2, and P1 were tested for both sweeps, with 300 handshakes per run.

### OBS-0014 | stage 1 | H2 | measurement | 2026-10-13 06:39:20
run: `runs/20261013-062108_sweep_loss_H2_d10_l1`

At 10 ms configured delay and 1% loss: 300 handshakes, mean latency 23.93 ms, p95 42.06 ms, TCP retransmission total 36.

### OBS-0015 | stage 1 | H2 | measurement | 2026-10-13 06:39:20
run: `runs/20261013-062446_sweep_loss_H2_d10_l3`

At 10 ms configured delay and 3% loss: 300 handshakes, mean latency 36.32 ms, p95 82.29 ms, TCP retransmission total 130.

### OBS-0016 | stage 1 | H2 | measurement | 2026-10-13 06:39:21
run: `runs/20261013-062815_sweep_loss_H2_d10_l5`

At 10 ms configured delay and 5% loss: 300 handshakes, mean latency 51.27 ms, p95 111.72 ms, TCP retransmission total 148.

### OBS-0017 | stage 2 | PLAIN | measurement | 2026-10-13 09:21:03
run: `-`

Baseline mode=native C=5 R=10: total 32.6672 s (setup 0.0433 s, rounds 32.6239 s), F1 0.9451, update 139792 B per client per round, run-to-run spread 8.5757 s (5 repeats).

### OBS-0018 | stage 2 | PLAIN | measurement | 2026-10-13 09:21:03
run: `-`

Baseline mode=native C=5 R=50: total 204.7628 s (setup 0.0430 s, rounds 204.7198 s), F1 0.9611, update 139792 B per client per round, run-to-run spread 34.9460 s (5 repeats).

### OBS-0019 | stage 2 | PLAIN | measurement | 2026-10-13 09:21:03
run: `-`

Baseline mode=native C=5 R=100: total 368.3301 s (setup 0.0341 s, rounds 368.2960 s), F1 0.9634, update 139792 B per client per round, run-to-run spread 58.2844 s (5 repeats).

### OBS-0020 | stage 2 | PLAIN | measurement | 2026-10-13 09:21:03
run: `-`

Baseline mode=native C=10 R=10: total 21.3629 s (setup 0.0882 s, rounds 21.2747 s), F1 0.9408, update 139792 B per client per round, run-to-run spread 5.1186 s (5 repeats).

### OBS-0021 | stage 2 | PLAIN | measurement | 2026-10-13 09:21:03
run: `-`

Baseline mode=native C=10 R=50: total 106.1790 s (setup 0.0857 s, rounds 106.0933 s), F1 0.9538, update 139792 B per client per round, run-to-run spread 12.2019 s (5 repeats).

### OBS-0022 | stage 2 | PLAIN | measurement | 2026-10-13 09:21:03
run: `-`

Baseline mode=native C=10 R=100: total 208.2641 s (setup 0.0777 s, rounds 208.1864 s), F1 0.9613, update 139792 B per client per round, run-to-run spread 18.5964 s (5 repeats).

### OBS-0023 | stage 2 | PLAIN | measurement | 2026-10-13 09:21:03
run: `-`

Baseline mode=native C=20 R=10: total 15.2408 s (setup 0.5863 s, rounds 14.6545 s), F1 0.9332, update 139792 B per client per round, run-to-run spread 1.6983 s (5 repeats).

### OBS-0024 | stage 2 | PLAIN | measurement | 2026-10-13 09:21:03
run: `-`

Baseline mode=native C=20 R=50: total 83.6265 s (setup 0.1638 s, rounds 83.4626 s), F1 0.9472, update 139792 B per client per round, run-to-run spread 13.9365 s (5 repeats).

### OBS-0025 | stage 2 | PLAIN | measurement | 2026-10-13 09:21:03
run: `-`

Baseline mode=native C=20 R=100: total 163.7273 s (setup 0.1676 s, rounds 163.5597 s), F1 0.9542, update 139792 B per client per round, run-to-run spread 29.7273 s (5 repeats).

### OBS-0026 | stage 2 | PLAIN | measurement | 2026-10-13 09:21:03
run: `-`

Baseline mode=reconnect C=5 R=10: total 33.0187 s (setup 0.3654 s, rounds 32.6533 s), F1 0.9451, update 139792 B per client per round, run-to-run spread 10.0625 s (3 repeats).

### OBS-0027 | stage 2 | PLAIN | measurement | 2026-10-13 09:21:03
run: `-`

Baseline mode=reconnect C=5 R=50: total 119.0132 s (setup 1.7255 s, rounds 117.2877 s), F1 0.9611, update 139792 B per client per round, run-to-run spread 1.7409 s (3 repeats).

### OBS-0028 | stage 2 | PLAIN | measurement | 2026-10-13 09:21:03
run: `-`

Baseline mode=reconnect C=10 R=10: total 20.9896 s (setup 0.7442 s, rounds 20.2454 s), F1 0.9408, update 139792 B per client per round, run-to-run spread 5.1177 s (3 repeats).

### OBS-0029 | stage 2 | PLAIN | measurement | 2026-10-13 09:21:03
run: `-`

Baseline mode=reconnect C=10 R=50: total 109.3560 s (setup 3.8114 s, rounds 105.5446 s), F1 0.9538, update 139792 B per client per round, run-to-run spread 33.7010 s (3 repeats).

### OBS-0030 | stage 3 | - | decision | 2026-10-15 15:06:58
run: `-`

Matrix run: modes=native,reconnect; native C=5,10,20 R=10,50,100; reconnect C=5,10 R=10,50; repeats=3; resume=off; 156 result rows recorded.

### OBS-0031 | stage 6 | - | setup | 2026-10-19 15:59:01
run: `-`

Updated code to v2: control/data-plane metrics, netem rate, TCP knobs, resumable matrix, statistics, analytical model. 4 unit tests pass.

### OBS-0032 | stage 6 | - | verification | 2026-10-19 16:10:11
run: `-`

netem verified: 25ms one-way delay -> ping RTT avg 50.696 ms; configured 3% loss -> observed 3.67% ping loss (11/300 packets); 20 Mbit/s -> iperf3 receiver 19.0 Mbit/s; initcwnd 4 and rto_min 50ms applied and reset successfully.

### OBS-0033 | stage 6 | - | decision | 2026-10-19 16:11:49
run: `-`

Network profiles verified in controller/profiles.py: LAN (RTT ~0.1 ms, unlimited bandwidth, 0% loss), WAN50 (RTT 50 ms, 20 Mbit/s, 0% loss), WAN100 (RTT 100 ms, 20 Mbit/s, 0% loss), LOSS1 (RTT 50 ms, 20 Mbit/s, 1% loss), LOSS3 (RTT 100 ms, 20 Mbit/s, 3% loss), LOSS5 (RTT 100 ms, 20 Mbit/s, 5% loss). Delay is configured one-way; RTT is approximately twice the delay. Loss is applied on the server-side network interface, affecting server-to-client traffic. Profiles cover ideal LAN, high-latency links, and lossy constrained networks.

### OBS-0034 | stage 6 | H2 | verification | 2026-10-19 16:23:34
run: `-`

Calibration H2 WAN100 transient C=10 R=10: control plane 4.517 s, data plane 6.551 s, compute 66.441 s, total 78.799 s; parts sum to total.

### OBS-0035 | stage 6 | H2 | measurement | 2026-10-19 17:14:34
run: `-`

initcwnd=4, RTT 50 ms: server flight 10223 B in 8 segments, bursts 2.00, handshake 106.57 ms vs 56.87 ms at initcwnd=10 -> extra RTT likely.

### OBS-0036 | stage 6 | H2 | measurement | 2026-10-19 17:14:38
run: `-`

Loss 3%, RTT 100 ms: H2 p95 309.94 ms, p99 521.31 ms, retransmissions 53 (K1: p95 104.38 ms, p99 410.47 ms, retransmissions 24).

### OBS-0037 | stage 6 | - | measurement | 2026-10-19 17:14:43
run: `-`

CPU time per handshake (server/client, ms): K1 2.267/17.996, H1 3.200/22.555, H2 1.533/6.751, P1 1.500/6.777.

### OBS-0038 | stage 6 | H2 | anomaly | 2026-10-19 17:14:52
run: `-`

H2 full handshake at RTT 50 ms: initcwnd=4 produced a 52.62 ms server-flight span and 106.57 ms mean handshake latency, compared with a 3.74 ms flight span and 56.87 ms mean at initcwnd=10. The roughly 50 ms difference is consistent with an additional RTT, but requires confirmation from packet captures.

### OBS-0039 | stage 7 | - | decision | 2026-10-23 07:43:14
run: `-`

Scaling experiment 1: clients 5 and 20, rounds 10, repeats 5, profiles LAN WAN100 LOSS3, resumption off; default configurations and connection modes. Reduced repeats to limit runtime.

### OBS-0040 | stage 7 | - | decision | 2026-10-24 08:47:51
run: `-`

Reduced Stage 7 matrix: client scaling C=5,20 with R=10 and 5 repeats on LAN/WAN100/LOSS3; persistent scaling C=10 with R=20,30 and 5 repeats on LAN/WAN100/LOSS3; reconnect resumption comparison C=10, R=20, 5 repeats on WAN100 with resume off/on. Native and reconnect modes evaluated; matrix runner supports resuming missing runs. Stage 7.4 higher-repeat confirmation cells not completed.

### OBS-0041 | stage 7 | - | measurement | 2026-10-24 08:49:00
run: `-`

Handshake instrumentation summary: native persistent mode, C=10, R=20/30: median n_syn=10 per run; median n_sessions=1. Reconnect mode, C=10, R=20: median n_syn=200 per run, matching C x R=200. With resumption off, median n_resumed_psk=0; with resumption on, median n_resumed_psk=190/200 (95%). Native n_clienthello mean=8 despite median=10 and some zero counts, indicating incomplete or inconsistent ClientHello capture; interpret ClientHello counts cautiously.

### OBS-0042 | stage 9 | - | measurement | 2026-10-24 09:01:24
run: `-`

Model fit: control plane MAPE 27.83%, data plane MAPE 36.93%, total MAPE 11.93% (total R2 0.564). Parameters: kappa_reg 2.6102, tau_cp 0.6055 s, kappa_pay_pers/trans 0.0/0.0, theta_ser 0.06734, theta_tls 0.04473, tau_data 0.28785 s.

### OBS-0043 | stage 9 | - | measurement | 2026-10-24 09:01:36
run: `-`

Leave-one-profile-out total MAPE: LAN 16.16%, LOSS3 19.97%, LOSS5 8.85%, WAN100 18.62%. The output currently lists four held-out profiles; WAN50 and LOSS1 results are not present in this table.

### OBS-0044 | stage 9 | - | decision | 2026-10-24 09:01:46
run: `-`

Stage 9 analytical model fitted using non-negative least squares. In-sample total MAPE is 11.93%, but total R2 is 0.564 and data-plane R2 is 0.0214. Both fitted payload round-trip parameters are zero. Interpret component-level and held-out-profile errors before making broad predictive claims.

### OBS-0045 | stage 9 | - | anomaly | 2026-10-24 09:02:27
run: `-`

Leave-one-profile-out total MAPE: LAN 16.16%, LOSS3 19.97%, LOSS5 8.85%, WAN100 18.62%. Threshold classification agreement was 67.31% at 1%, 70.19% at 5%, and 77.88% at 10%. In-sample total MAPE was 11.93%, but total R2 was 0.564 and data-plane R2 was 0.0214. The model's predictions are not uniformly accurate across profiles; the cause of the largest errors requires further examination.

