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

