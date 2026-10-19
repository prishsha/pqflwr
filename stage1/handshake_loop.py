"""Stage 1: N isolated handshakes of one configuration, captured and analysed.
sudo venv/bin/python stage1/handshake_loop.py --cfg H2 --n 300
Resumption test:  add --resume  (first handshake saves a session, the next N resume it)"""
import argparse, os, subprocess, sys, time, json
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for d in ("controller", "proxy", "analysis"): sys.path.insert(0, os.path.join(ROOT, d))
import common as C, gen_conf, analyze_pcap
import pandas as pd

ap = argparse.ArgumentParser(); ap.add_argument("--cfg", required=True, choices=[c for c in C.CFGS if c != "PLAIN"])
ap.add_argument("--n", type=int, default=300); ap.add_argument("--warmup", type=int, default=20)
ap.add_argument("--delay-ms", type=float, default=0); ap.add_argument("--loss", type=float, default=0)
ap.add_argument("--resume", action="store_true"); ap.add_argument("--tag", default="stage1")
ap.add_argument("--rate-mbit", type=float, default=0); ap.add_argument("--initcwnd", type=int, default=0); ap.add_argument("--rto-min-ms", type=int, default=0)
a = ap.parse_args()
port, group, chain = C.CFGS[a.cfg]
certdir = os.path.join(ROOT, "pki", "certs")
rd = os.path.join(ROOT, "runs", "%s_%s_%s_d%g_l%g_r%g_iw%d_rto%d%s" % (time.strftime("%Y%m%d-%H%M%S"), a.tag, a.cfg, a.delay_ms, a.loss, a.rate_mbit, a.initcwnd, a.rto_min_ms, "_resume" if a.resume else ""))
os.makedirs(rd)
C.set_netem(a.delay_ms, a.loss, a.rate_mbit); C.tune_route(a.initcwnd, a.rto_min_ms)
open(os.path.join(rd, "srv.conf"), "w").write(gen_conf.server_conf(rd, certdir, port, group, chain))
srv = C.start_nginx("srv", os.path.join(rd, "srv.conf"), rd, "srv")
sink = subprocess.Popen(C.nsx("srv", [sys.executable, "-c",
    "import socket\ns=socket.socket();s.setsockopt(1,2,1);s.bind(('127.0.0.1',9092));s.listen(256)\nk=[]\nwhile True: k.append(s.accept()[0])"]))
time.sleep(0.5)
env = dict(os.environ, LD_LIBRARY_PATH=C.OPENSSL_LIB)
sess = os.path.join(rd, "sess.pem")
def handshake(use_sess_in, save_out=None, hold=0.1):
    cmd = [C.OPENSSL, "s_client", "-connect", "%s:%d" % (C.SRV_IP, port), "-tls1_3", "-groups", group,
           "-CAfile", os.path.join(certdir, "ca-%s.crt" % chain), "-servername", "testserver", "-verify_hostname", "testserver"]
    if use_sess_in: cmd += ["-sess_in", sess]
    if save_out: cmd += ["-sess_out", save_out]
    p = subprocess.Popen(C.nsx("cli", cmd), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True)
    time.sleep(hold); out, _ = p.communicate(input="")
    return out
first = handshake(False, sess if a.resume else None, hold=0.3)
open(os.path.join(rd, "s_client_first.txt"), "w").write(first)   # evidence: negotiated group, sig type, verify code
for _ in range(a.warmup): handshake(a.resume, sess if a.resume else None, hold=0.3 if a.resume else 0.1)
pcap = os.path.join(rd, "capture.pcap")
cap = C.start_capture(pcap, port, os.path.join(rd, "tcpdump.txt")); time.sleep(1.0)
import resource
r0 = C.tcp_retrans("srv"); reused = 0
cpu_srv0 = C.tree_cpu(srv.pid); ru0 = resource.getrusage(resource.RUSAGE_CHILDREN); ru0 = ru0.ru_utime + ru0.ru_stime
for _ in range(a.n):
    out = handshake(a.resume, sess if a.resume else None, hold=0.3 if a.resume else 0.1)
    reused += ("Reused, TLSv1.3" in out)
r1 = C.tcp_retrans("srv")
cpu_srv1 = C.tree_cpu(srv.pid); ru1 = resource.getrusage(resource.RUSAGE_CHILDREN); ru1 = ru1.ru_utime + ru1.ru_stime
time.sleep(1.0); C.stop_proc(cap); C.stop_proc(srv, 15); C.stop_proc(sink, 15)
summ, ps = analyze_pcap.analyze(pcap, port, out_csv=os.path.join(rd, "streams.csv"))
der = lambda f: len(subprocess.run([C.OPENSSL, "x509", "-in", os.path.join(certdir, f), "-outform", "DER"], capture_output=True, env=env).stdout)
row = {"run_dir": os.path.basename(rd), "cfg": a.cfg, "resume": a.resume, "n": a.n, "delay_ms": a.delay_ms, "loss_pct": a.loss,
       "reused_by_s_client": reused, "server_tcp_retrans_delta": r1 - r0, "tcpdump_dropped": C.tcpdump_drops(os.path.join(rd, "tcpdump.txt")),
       "rate_mbit": a.rate_mbit, "initcwnd": a.initcwnd, "rto_min_ms": a.rto_min_ms, "rtt_ms": 2 * a.delay_ms,
       "cpu_srv_per_hs_ms": 1000 * (cpu_srv1 - cpu_srv0) / a.n, "cpu_cli_per_hs_ms": 1000 * (ru1 - ru0) / a.n,
       "cert_leaf_der": der("server-%s.crt" % chain), "cert_ca_der": der("ca-%s.crt" % chain)}
if "hs_ms" in ps and ps.hs_ms.notna().sum() > 1:
    import numpy as np
    from scipy import stats as _st
    h = ps.hs_ms.dropna().values; hw = _st.t.ppf(0.975, len(h) - 1) * h.std(ddof=1) / np.sqrt(len(h))
    row.update({"hs_ci95_lo_ms": h.mean() - hw, "hs_ci95_hi_ms": h.mean() + hw})
row.update(summ)
out = os.path.join(ROOT, "results", "stage1.csv")
pd.concat([pd.read_csv(out), pd.DataFrame([row])]).to_csv(out, index=False) if os.path.exists(out) else pd.DataFrame([row]).to_csv(out, index=False)
subprocess.run(C.nsx("srv", ["ip", "route", "show"]), stdout=open(os.path.join(rd, "srv_route.txt"), "w"))
print(json.dumps(row, indent=1, default=float))
print("\nfirst handshake evidence:\n", "\n".join(l for l in first.splitlines() if any(k in l for k in ("group", "Peer signature", "Cipher is", "Verify return", "Protocol"))))
