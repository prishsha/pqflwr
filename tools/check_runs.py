"""Sanity checks on results/runs.csv.  python tools/check_runs.py --stage 7
Prints, per cell: number of valid runs, handshake count vs expectation, retransmissions, dropped packets, F1 spread."""
import argparse, os, numpy as np, pandas as pd
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ap = argparse.ArgumentParser(); ap.add_argument("--stage", required=True); ap.add_argument("--min-runs", type=int, default=10)
a = ap.parse_args()
d = pd.read_csv(os.path.join(ROOT, "results", "runs.csv")); d = d[(d.stage.astype(str) == a.stage) & (d.local_test == False)]
if d.empty: raise SystemExit("no runs for stage " + a.stage)
d["resume"] = d["resume"].astype(str)
key = ["profile", "mode", "resume", "cfg", "clients", "rounds", "initcwnd", "rto_min_ms"]
rows = []
for k, g in d.groupby(key):
    prof, mode, res, cfg, C, R, iw, rto = k
    exp_hs = C if mode == "native" else C * R
    issues = []
    if len(g) < a.min_runs: issues.append("only %d runs (<%d)" % (len(g), a.min_runs))
    if g.tcpdump_dropped.fillna(0).sum() > 0: issues.append("dropped packets in %d run(s)" % (g.tcpdump_dropped.fillna(0) > 0).sum())
    if cfg != "PLAIN":
        nh = g.n_clienthello.mean()
        if abs(nh - exp_hs) > 0.1 * exp_hs: issues.append("handshakes %.1f, expected about %d" % (nh, exp_hs))
        if res == "on" and mode == "reconnect" and g.n_resumed_psk.mean() < 0.5 * exp_hs: issues.append("resumption barely happened (%.1f resumed)" % g.n_resumed_psk.mean())
        if res == "off" and g.n_resumed_psk.mean() > 0: issues.append("resumed handshakes although resumption OFF")
    loss = g.loss_pct.iloc[0]
    if loss > 0 and g.retx_total.mean() == 0 and g.srv_tcp_retrans_delta.mean() == 0: issues.append("loss %.0f%% but no retransmissions seen" % loss)
    if g.final_f1.std() > 0.02: issues.append("F1 spread %.3f" % g.final_f1.std())
    rows.append(dict(zip(key, k), n=len(g), handshakes=round(g.n_clienthello.mean(), 1) if cfg != "PLAIN" else np.nan, expected=exp_hs if cfg != "PLAIN" else np.nan, issues="; ".join(issues) or "ok"))
r = pd.DataFrame(rows); pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 80)
print(r[["profile", "mode", "resume", "cfg", "clients", "rounds", "initcwnd", "rto_min_ms", "n", "handshakes", "expected", "issues"]].to_string(index=False))
bad = (r.issues != "ok").sum(); print("\n%d of %d cells have issues" % (bad, len(r)))
