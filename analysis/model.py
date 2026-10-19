"""Analytical overhead model for the total FL training time T_epoch (a training run of R rounds).

   T_epoch = T_compute + T_handshake(control plane) + T_payload(data plane) + T_loss

   control plane (per session, N_s sessions: 1 persistent, R transient)
       T_ctrl = RTT*(kappa_reg + I_tls*(1+k_extra)) + t_cpu(cfg,state,C) + C*B_s2c*8/BW  + P_cp*tau_cp
       k_extra = ceil(log2(m/IW + 1)) - 1,  m = ceil(B_s2c/MSS)      (slow start, initial window IW)
       t_cpu   = t_1 + (C-1)*t_s                                        (server proxy is single threaded)
       state   = full or resumed, mixed with measured fraction rho
       P_cp    = 1-(1-p)^(C*m_hs)                                       (any of the C handshakes hit by a loss)
   data plane (per round)
       T_data  = RTT*kappa_pay(conn) + 2*C*B_upd*8/BW + theta_ser*2*C*B_upd + I_tls*theta_tls*2*C*B_upd + P_data*tau_data
       P_data  = 1-(1-p)^(C*ceil(B_upd/MSS))
   Free parameters (fitted by non-negative least squares): kappa_reg, tau_cp, kappa_pay_pers, kappa_pay_trans,
   theta_ser, theta_tls, tau_data.   Everything else is MEASURED (Stage 1 handshake table, PLAIN baseline, link settings).
   python analysis/model.py --stage 7
"""
import argparse, json, math, os, numpy as np, pandas as pd
from scipy.optimize import nnls
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MSS = 1448; IW_DEFAULT = 10; RTO_DEFAULT_MS = 200; M_PLAIN = 6   # segments of a plain TCP connect+registration (assumption, stated)

def k_extra(bytes_s2c, iw):
    if bytes_s2c <= 0: return 0
    m = math.ceil(bytes_s2c / MSS)
    return max(0, math.ceil(math.log2(m / iw + 1)) - 1)

def load_hs_table(path=None):
    """One row per (cfg, resumed?) from the LAN Stage-1 measurements (delay 0, loss 0, no rate limit, default route)."""
    s = pd.read_csv(path or os.path.join(ROOT, "results", "stage1.csv"))
    for c, dflt in [("rate_mbit", 0), ("initcwnd", 0), ("rto_min_ms", 0), ("cpu_srv_per_hs_ms", np.nan)]:
        if c not in s: s[c] = dflt
    s = s[(s.delay_ms == 0) & (s.loss_pct == 0) & (s.rate_mbit.fillna(0) == 0) & (s.initcwnd.fillna(0) == 0) & (s.rto_min_ms.fillna(0) == 0)]
    tab = {}
    for (cfg, res), g in s.groupby(["cfg", "resume"]):
        g = g.iloc[-1]
        t1 = g.hs_mean_ms / 1000; ts = (g.cpu_srv_per_hs_ms / 1000) if g.cpu_srv_per_hs_ms == g.cpu_srv_per_hs_ms else 0.5 * t1
        tab[(cfg, bool(res))] = dict(t1=t1, ts=ts, s2c=g.hs_payload_s2c_mean, segs=g.hs_segments_s2c_mean + 1)  # +1 = SYN-ACK
    tab[("PLAIN", False)] = tab[("PLAIN", True)] = dict(t1=0.0, ts=0.0, s2c=0.0, segs=M_PLAIN)
    return tab

def hs_params(tab, cfg, resumed):
    if (cfg, resumed) in tab: return tab[(cfg, resumed)]
    return tab[(cfg, False)]          # fall back to the full handshake if no resumed measurement exists

def comp_table(d):
    p = d[d.cfg == "PLAIN"]
    out = {}
    for c, g in p.groupby("clients"): out[int(c)] = float(((g.train_total_s + g.agg_total_s) / g.rounds).mean())
    return out

def known_cp(row, tab, rho, iw):
    """sum over states of the parts of T_ctrl that are measured, per session (seconds)."""
    C = row["clients"]; rtt = row["rtt_ms"] / 1000; bw = row["rate_mbit"] * 1e6
    tls = row["cfg"] != "PLAIN"; tot = 0.0; m_hs = 0.0
    for resumed, w in ((False, 1 - rho), (True, rho)):
        if w <= 0: continue
        h = hs_params(tab, row["cfg"], resumed)
        t = (rtt * (1 + k_extra(h["s2c"], iw)) if tls else 0.0) + h["t1"] + (C - 1) * h["ts"]
        t += (C * h["s2c"] * 8 / bw) if bw > 0 else 0.0
        tot += w * t; m_hs += w * h["segs"]
    return tot, m_hs

def features(row, tab, comp, rho=None, iw=IW_DEFAULT):
    C, R = row["clients"], row["rounds"]; rtt = row["rtt_ms"] / 1000; p = row["loss_pct"] / 100; bw = row["rate_mbit"] * 1e6
    Ns = R if row["mode"] == "reconnect" else 1
    if rho is None: rho = (row["n_resumed_psk"] / row["n_clienthello"]) if row.get("n_clienthello", 0) else 0.0
    k_cp, m_hs = known_cp(row, tab, rho, iw)
    P_cp = 1 - (1 - p) ** (C * m_hs)
    B1 = row["model_bytes_one_way"]; m_d = math.ceil(B1 / MSS); P_data = 1 - (1 - p) ** (C * m_d)
    MB = 2 * C * B1 / 1e6
    known_data = (2 * C * B1 * 8 / bw) if bw > 0 else 0.0
    tls = 1.0 if row["cfg"] != "PLAIN" else 0.0
    pers = 1.0 if row["mode"] == "native" else 0.0
    return dict(Ns=Ns, known_cp=Ns * k_cp, f_cp=[Ns * rtt, Ns * P_cp],
                known_data=R * known_data, f_data=[R * rtt * pers, R * rtt * (1 - pers), R * MB, tls * R * MB, R * P_data],
                comp=R * comp.get(int(C), np.nan))

CP_NAMES = ["kappa_reg", "tau_cp"]; DATA_NAMES = ["kappa_pay_pers", "kappa_pay_trans", "theta_ser", "theta_tls", "tau_data"]

def fit(d, tab, comp):
    F = [features(r, tab, comp) for _, r in d.iterrows()]
    Acp = np.array([f["f_cp"] for f in F]); ycp = d.cp_total_s.values - np.array([f["known_cp"] for f in F])
    Ad = np.array([f["f_data"] for f in F]); yd = d.data_total_s.values - np.array([f["known_data"] for f in F])
    th_cp, _ = nnls(Acp, ycp); th_d, _ = nnls(Ad, yd)
    return dict(zip(CP_NAMES, th_cp)) | dict(zip(DATA_NAMES, th_d))

def predict_row(row, th, tab, comp, rho=None, iw=IW_DEFAULT, rto_ms=RTO_DEFAULT_MS):
    f = features(row, tab, comp, rho, iw)
    tau_cp = th["tau_cp"] * (rto_ms / RTO_DEFAULT_MS)          # hypothesis H-M2: tail-loss stall of a handshake scales with RTO_min
    cp = f["known_cp"] + f["f_cp"][0] * th["kappa_reg"] + f["f_cp"][1] * tau_cp
    data = f["known_data"] + sum(x * th[n] for x, n in zip(f["f_data"], DATA_NAMES))
    return dict(comp=f["comp"], cp=cp, data=data, total=f["comp"] + cp + data)

def evaluate(d, th, tab, comp):
    rows = []
    for _, r in d.iterrows():
        p = predict_row(r, th, tab, comp); rows.append(dict(run_id=r.run_id, profile=r.profile, mode=r["mode"], resume=r.resume, cfg=r.cfg,
            clients=r.clients, rounds=r.rounds, cp_meas=r.cp_total_s, cp_pred=p["cp"], data_meas=r.data_total_s, data_pred=p["data"],
            total_meas=r.epoch_total_s, total_pred=p["total"]))
    return pd.DataFrame(rows)

def metrics(e):
    cell = e.groupby(["profile", "mode", "resume", "cfg", "clients", "rounds"]).mean(numeric_only=True).reset_index()
    out = {}
    for k in ("cp", "data", "total"):
        m, p = cell[k + "_meas"], cell[k + "_pred"]
        out[k] = dict(MAPE_pct=float(100 * np.mean(np.abs(p - m) / np.maximum(m, 1e-9))), RMSE_s=float(np.sqrt(np.mean((p - m) ** 2))),
                      R2=float(1 - np.sum((m - p) ** 2) / np.sum((m - m.mean()) ** 2)) if len(m) > 1 and m.var() > 0 else float("nan"))
    return out, cell

def leave_one_profile_out(d, tab, comp):
    rows = []
    for prof in sorted(d.profile.unique()):
        tr, te = d[d.profile != prof], d[d.profile == prof]
        if len(tr) < 10 or len(te) == 0: continue
        th = fit(tr, tab, comp); e = evaluate(te, th, tab, comp); m, _ = metrics(e)
        rows.append(dict(held_out=prof, n_runs=len(te), cp_MAPE=m["cp"]["MAPE_pct"], data_MAPE=m["data"]["MAPE_pct"], total_MAPE=m["total"]["MAPE_pct"]))
    return pd.DataFrame(rows)

def crossover_table(th, tab, comp, profiles, clients=(5, 10, 20), rounds=(10, 50, 100), B1=73992, thetas=(1, 5, 10)):
    """Predicted inflation (%) of each PQ configuration vs K1 and vs PLAIN, and the smallest R (<=1000) at which it reaches theta."""
    rows = []
    for prof, p in profiles.items():
        for mode in ("native", "reconnect"):
            for res in ("off", "on"):
                for C in clients:
                    if C not in comp: continue
                    base = dict(clients=C, rtt_ms=2 * p["delay_ms"], loss_pct=p["loss"], rate_mbit=p["rate_mbit"], mode=mode, model_bytes_one_way=B1, n_clienthello=0, n_resumed_psk=0)
                    def tot(cfg, R):
                        row = dict(base, cfg=cfg, rounds=R)
                        rho = 0.0 if (res == "off" or cfg == "PLAIN" or mode == "native") else 1 - 1 / R
                        return predict_row(row, th, tab, comp, rho=rho)["total"]
                    for cfg in ("K1", "H1", "H2", "P1"):
                        for R in rounds:
                            tc, tk, tp = tot(cfg, R), tot("K1", R), tot("PLAIN", R)
                            rows.append(dict(profile=prof, mode=mode, resume=res, clients=C, rounds=R, cfg=cfg, pred_total_s=tc,
                                             infl_vs_K1_pct=100 * (tc - tk) / tk, infl_vs_PLAIN_pct=100 * (tc - tp) / tp))
    return pd.DataFrame(rows)

def plots(e, cell, outdir):
    fig, ax = plt.subplots(1, 3, figsize=(13, 4))
    for a, k, t in zip(ax, ("cp", "data", "total"), ("control plane (s)", "data plane (s)", "total epoch time (s)")):
        a.scatter(cell[k + "_meas"], cell[k + "_pred"], s=14); lim = [0, max(cell[k + "_meas"].max(), cell[k + "_pred"].max()) * 1.05]
        a.plot(lim, lim, "k--", lw=.8); a.set_xlabel("measured"); a.set_ylabel("model"); a.set_title(t); a.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(os.path.join(outdir, "model_pred_vs_meas.png"), dpi=150); plt.close(fig)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--stage", required=True); ap.add_argument("--local-test", action="store_true")
    a = ap.parse_args()
    sys_path = os.path.join(ROOT, "analysis"); import sys; sys.path.insert(0, sys_path); sys.path.insert(0, os.path.join(ROOT, "controller"))
    from stats import load_valid
    from profiles import PROFILES
    d = load_valid(a.stage, a.local_test).dropna(subset=["cp_total_s", "data_total_s"]).reset_index(drop=True)
    d["resume"] = d["resume"].astype(str)
    tab = load_hs_table(); comp = comp_table(d)
    d = d[d.cfg.isin({c for c, _ in tab})]
    th = fit(d, tab, comp); e = evaluate(d, th, tab, comp); m, cell = metrics(e); cv = leave_one_profile_out(d, tab, comp)
    out = os.path.join(ROOT, "results"); os.makedirs(out, exist_ok=True)
    json.dump({"parameters": th, "fit_quality": m, "constants": dict(MSS=MSS, IW_DEFAULT=IW_DEFAULT, RTO_DEFAULT_MS=RTO_DEFAULT_MS, M_PLAIN=M_PLAIN)},
              open(os.path.join(out, "model_params.json"), "w"), indent=2)
    cell.to_csv(os.path.join(out, "model_fit_cells.csv"), index=False); cv.to_csv(os.path.join(out, "model_cv.csv"), index=False)
    crossover_table(th, tab, comp, PROFILES, B1=float(d.model_bytes_one_way.iloc[0])).to_csv(os.path.join(out, "model_predictions.csv"), index=False)
    os.makedirs(os.path.join(out, "plots"), exist_ok=True); plots(e, cell, os.path.join(out, "plots"))
    print("fitted parameters:"); [print("  %-16s %.4g" % kv) for kv in th.items()]
    print("fit quality (cell means):", json.dumps(m, indent=1)); print("leave-one-profile-out:\n", cv.round(2).to_string(index=False))
