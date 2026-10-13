"""Run ONE experiment cell.
Example (needs root):  sudo venv/bin/python controller/run_experiment.py --cfg K1 --clients 5 --rounds 10 --stage 0
--mode native     : one Flower session of R rounds (connection stays open - Flower's default behaviour)
--mode reconnect  : R sessions of 1 round each, so every client opens a NEW TCP+TLS connection every round
--resume on|off   : client proxy re-uses TLS session tickets or not
--local-test      : no namespaces / nginx / capture; only checks that the FL part runs on loopback"""
import argparse, csv, glob, json, os, sys, time, subprocess
import numpy as np
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "controller")); sys.path.insert(0, os.path.join(ROOT, "proxy"))
sys.path.insert(0, os.path.join(ROOT, "analysis"))
import common as C
import gen_conf
import analyze_pcap

ap = argparse.ArgumentParser()
ap.add_argument("--cfg", required=True, choices=list(C.CFGS)); ap.add_argument("--clients", type=int, required=True)
ap.add_argument("--rounds", type=int, required=True); ap.add_argument("--mode", default="native", choices=["native", "reconnect"])
ap.add_argument("--resume", default="off", choices=["on", "off"]); ap.add_argument("--repeat", type=int, default=1)
ap.add_argument("--delay-ms", type=float, default=0); ap.add_argument("--loss", type=float, default=0)
ap.add_argument("--stage", default="x"); ap.add_argument("--data", default=os.path.join(ROOT, "data", "processed.npz"))
ap.add_argument("--local-test", action="store_true"); ap.add_argument("--epochs", type=int, default=1)
a = ap.parse_args()
L = a.local_test
port, group, chain = C.CFGS[a.cfg]
if L: port = 4439

run_id = "%s_s%s_%s_C%d_R%d_%s_res%s_d%g_l%g_r%d" % (time.strftime("%Y%m%d-%H%M%S"), a.stage, a.cfg, a.clients, a.rounds,
                                                       a.mode, a.resume, a.delay_ms, a.loss, a.repeat)
rd = os.path.join(ROOT, "runs", run_id); os.makedirs(rd)
certdir = os.path.join(ROOT, "pki", "certs")
PY = sys.executable
print("RUN", run_id)

if not L: C.set_netem(a.delay_ms, a.loss)
procs = {}
if not L:
    open(os.path.join(rd, "srv.conf"), "w").write(gen_conf.server_conf(rd, certdir, port, group, chain))
    open(os.path.join(rd, "cli.conf"), "w").write(gen_conf.client_conf(rd, certdir, port, group, chain, a.resume == "on"))
    procs["srv"] = C.start_nginx("srv", os.path.join(rd, "srv.conf"), rd, "srv")
    procs["cli"] = C.start_nginx("cli", os.path.join(rd, "cli.conf"), rd, "cli")
    pcap = os.path.join(rd, "capture.pcap")
    procs["cap"] = C.start_capture(pcap, port, os.path.join(rd, "tcpdump.txt")); time.sleep(1.0)

retx0 = C.tcp_retrans("srv", L)
client_addr = "127.0.0.1:9092" if L else "127.0.0.1:%d" % gen_conf.PROXY_LOCAL
n_sessions, rounds_per = (1, a.rounds) if a.mode == "native" else (a.rounds, 1)
weights = None
sess_logs = []
t_run0 = time.time()
for s in range(n_sessions):
    sd = os.path.join(rd, "s%03d" % s); os.makedirs(sd)
    go = os.path.join(sd, "go")
    srv_cmd = [PY, os.path.join(ROOT, "fl", "server.py"), "--addr", "127.0.0.1:9092", "--clients", str(a.clients),
               "--rounds", str(rounds_per), "--round-offset", str(s * rounds_per), "--out-weights", os.path.join(sd, "w.npz"),
               "--data", a.data, "--log", os.path.join(sd, "server.json"), "--ready-file", os.path.join(sd, "server.ready")]
    if weights: srv_cmd += ["--init", weights]
    srv = subprocess.Popen(C.nsx("srv", srv_cmd, L), stdout=open(os.path.join(sd, "server.out"), "w"), stderr=subprocess.STDOUT)
    cl = []
    for i in range(a.clients):
        cmd = [PY, os.path.join(ROOT, "fl", "client.py"), "--cid", str(i), "--num-clients", str(a.clients), "--server", client_addr,
               "--data", a.data, "--ready-file", os.path.join(sd, "c%d.ready" % i), "--go-file", go,
               "--log", os.path.join(sd, "client%d.json" % i), "--epochs", str(a.epochs)]
        cl.append(subprocess.Popen(C.nsx("cli", cmd, L), stdout=open(os.path.join(sd, "client%d.out" % i), "w"), stderr=subprocess.STDOUT))
    t_wait = time.time()
    while not (os.path.exists(os.path.join(sd, "server.ready")) and all(os.path.exists(os.path.join(sd, "c%d.ready" % i)) for i in range(a.clients))):
        if time.time() - t_wait > 120: sys.exit("timeout waiting for processes to become ready; see " + sd)
        time.sleep(0.05)
    time.sleep(1.0)                                    # let the Flower server start listening
    open(go, "w").write(str(time.time()))              # GO: all clients connect now
    srv.wait(timeout=3600)
    for p in cl: p.wait(timeout=600)
    weights = os.path.join(sd, "w.npz")
    sess_logs.append(sd)
t_run1 = time.time()
retx1 = C.tcp_retrans("srv", L)

cpu = {}
if not L:
    cpu["cpu_srv_proxy_s"] = C.tree_cpu(procs["srv"].pid); cpu["cpu_cli_proxy_s"] = C.tree_cpu(procs["cli"].pid)
    time.sleep(1.0); C.stop_proc(procs["cap"])
    for k in ("cli", "srv"): C.stop_proc(procs[k], __import__("signal").SIGTERM)

# ---- FL metrics ----
setup_s = []; rounds_s = []; f1 = None; cpu_fl_srv = 0; cpu_fl_cli = 0; model_bytes = 0
for sd in sess_logs:
    sj = json.load(open(os.path.join(sd, "server.json"))); cj = [json.load(open(f)) for f in sorted(glob.glob(os.path.join(sd, "client*.json")))]
    t_go = min(c["t_go"] for c in cj); last_first_fit = max(c["t_first_fit"] for c in cj)
    setup_s.append(last_first_fit - t_go)                        # connect + handshake + registration + slowest client
    for i, r in enumerate(sj["rounds"]):
        start = last_first_fit if i == 0 else r["t_start"]       # round 1 starts when the last client is ready
        rounds_s.append(r["t_end"] - start); f1 = r["f1"]
    cpu_fl_srv += sj["cpu_s"]; cpu_fl_cli += sum(c["cpu_s"] for c in cj); model_bytes = sj["bytes_model"]
res = {"run_id": run_id, "stage": a.stage, "cfg": a.cfg, "mode": a.mode, "resume": a.resume, "clients": a.clients, "rounds": a.rounds,
       "repeat": a.repeat, "delay_ms": a.delay_ms, "loss_pct": a.loss, "local_test": L,
       "setup_total_s": sum(setup_s), "rounds_total_s": sum(rounds_s), "logical_total_s": sum(setup_s) + sum(rounds_s),
       "wall_total_s": t_run1 - t_run0, "final_f1": f1, "model_bytes_one_way": model_bytes,
       "update_bytes_per_client_round": 2 * model_bytes, "cpu_fl_server_s": cpu_fl_srv, "cpu_fl_clients_s": cpu_fl_cli,
       "srv_tcp_retrans_delta": retx1 - retx0}
res.update(cpu)
if not L:
    summ, ps = analyze_pcap.analyze(pcap, port, plain=(a.cfg == "PLAIN"), out_csv=os.path.join(rd, "streams.csv"))
    res.update({k: v for k, v in summ.items()})
    res["tcpdump_dropped"] = C.tcpdump_drops(os.path.join(rd, "tcpdump.txt"))
    res["expected_cxr"] = a.clients * a.rounds
C.write_manifest(os.path.join(rd, "manifest.json"), {"args": vars(a), "run_id": run_id})
json.dump(res, open(os.path.join(rd, "result.json"), "w"), indent=2, default=float)
out = os.path.join(ROOT, "results", "runs.csv"); new = not os.path.exists(out)
if os.path.exists(out):                                   # keep header consistent if new columns appear
    import pandas as pd
    old = pd.read_csv(out); pd.concat([old, pd.DataFrame([res])]).to_csv(out, index=False)
else:
    import pandas as pd; pd.DataFrame([res]).to_csv(out, index=False)
print(json.dumps(res, indent=1, default=float))
if not L and res.get("tcpdump_dropped", 0) > 0: print("WARNING: tcpdump dropped packets -> mark this run INVALID")
