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

