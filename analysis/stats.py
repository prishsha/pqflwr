"""Per-cell statistics: n, mean, SD, 95% CI (Student t), p50/p95/p99, and paired-vs-K1 tests.
   python analysis/stats.py --stage 7            (writes results/stats_cells.csv, results/stats_vs_K1.csv, plots)"""
import argparse, os, numpy as np, pandas as pd
from scipy import stats as st
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KEY = ["profile", "mode", "resume", "cfg", "clients", "rounds", "initcwnd", "rto_min_ms"]
METRICS = ["epoch_total_s", "cp_total_s", "data_total_s", "train_total_s", "agg_total_s", "hs_mean_ms",
           "cpu_srv_proxy_s", "cpu_cli_proxy_s", "retx_total", "srv_tcp_retrans_delta"]

def ci95(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]; n = len(x)
    if n < 2: return (np.nan, np.nan, np.nan, np.nan)
    m, sd = x.mean(), x.std(ddof=1); h = st.t.ppf(0.975, n - 1) * sd / np.sqrt(n)
    return m, sd, m - h, m + h

def load_valid(stage, local=False):
    d = pd.read_csv(os.path.join(ROOT, "results", "runs.csv"))
    d = d[(d.stage.astype(str) == str(stage)) & (d.local_test == local)]
    if "tcpdump_dropped" in d: d = d[d.tcpdump_dropped.fillna(0) == 0]
    return d.dropna(subset=["profile"]).reset_index(drop=True)

def pooled_handshakes(d):
    """tail latency of individual handshakes, pooled over all runs of a cell (from runs/<id>/streams.csv)."""
    rows = []
    for k, g in d.groupby(KEY):
        v = []
        for rid in g.run_id:
            f = os.path.join(ROOT, "runs", rid, "streams.csv")
            if os.path.exists(f):
                s = pd.read_csv(f)
                if "hs_ms" in s: v += list(s.hs_ms.dropna())
        if v:
            v = np.array(v); rows.append(dict(zip(KEY, k), hs_n=len(v), hs_p50_ms=np.percentile(v, 50), hs_p95_ms=np.percentile(v, 95),
                                              hs_p99_ms=np.percentile(v, 99), hs_max_ms=v.max()))
    return pd.DataFrame(rows)

def cells(d):
    rows = []
    for k, g in d.groupby(KEY):
        r = dict(zip(KEY, k)); r["n_runs"] = len(g)
        for m in METRICS:
            if m in g:
                mean, sd, lo, hi = ci95(g[m]); v = g[m].dropna().values
                r.update({m + "_mean": mean, m + "_sd": sd, m + "_ci_lo": lo, m + "_ci_hi": hi})
                if len(v): r.update({m + "_p50": np.percentile(v, 50), m + "_p95": np.percentile(v, 95), m + "_p99": np.percentile(v, 99)})
        for m in ["n_clienthello", "n_resumed_psk", "n_syn", "final_f1"]:
            if m in g: r[m + "_mean"] = g[m].mean()
        rows.append(r)
    return pd.DataFrame(rows)

def vs_k1(d, metric="epoch_total_s"):
    """Welch t-test, Mann-Whitney U and Cliff's delta of each cfg against K1 in the same condition."""
    base = [c for c in KEY if c != "cfg"]; rows = []
    for k, g in d.groupby(base):
        ref = g[g.cfg == "K1"][metric].dropna().values
        for cfg, gg in g.groupby("cfg"):
            if cfg == "K1": continue
            x = gg[metric].dropna().values
            if len(ref) < 2 or len(x) < 2: continue
            diff = x.mean() - ref.mean(); se = np.sqrt(x.var(ddof=1) / len(x) + ref.var(ddof=1) / len(ref))
            dof = se**4 / ((x.var(ddof=1) / len(x))**2 / (len(x) - 1) + (ref.var(ddof=1) / len(ref))**2 / (len(ref) - 1)) if se > 0 else 1
            h = st.t.ppf(0.975, dof) * se
            u = st.mannwhitneyu(x, ref, alternative="two-sided").pvalue
            cd = (np.sum(x[:, None] > ref[None, :]) - np.sum(x[:, None] < ref[None, :])) / (len(x) * len(ref))
            rows.append(dict(zip(base, k), cfg=cfg, metric=metric, n=len(x), n_k1=len(ref), diff_s=diff, diff_ci_lo=diff - h, diff_ci_hi=diff + h,
                             diff_pct_vs_K1=100 * diff / ref.mean(), mannwhitney_p=u, cliffs_delta=cd,
                             significant_95=bool((diff - h > 0) or (diff + h < 0))))
    return pd.DataFrame(rows)

def plots(d, c):
    os.makedirs(os.path.join(ROOT, "results", "plots"), exist_ok=True)
    for (mode, res, clients, rounds), g in c.groupby(["mode", "resume", "clients", "rounds"]):
        profs = [p for p in ["LAN", "WAN50", "WAN100", "LOSS1", "LOSS3", "LOSS5"] if p in set(g.profile)]
        cfgs = [x for x in ["PLAIN", "K1", "H1", "H2", "P1"] if x in set(g.cfg)]
        if not profs or not cfgs: continue
        fig, ax = plt.subplots(1, 2, figsize=(12, 4))
        w = 0.8 / len(cfgs)
        for i, cfg in enumerate(cfgs):                                  # (a) epoch time with 95% CI
            gg = g[g.cfg == cfg].set_index("profile").reindex(profs)
            ax[0].bar(np.arange(len(profs)) + i * w, gg.epoch_total_s_mean, w, label=cfg,
                      yerr=[gg.epoch_total_s_mean - gg.epoch_total_s_ci_lo, gg.epoch_total_s_ci_hi - gg.epoch_total_s_mean], capsize=2)
        ax[0].set_xticks(np.arange(len(profs)) + 0.4 - w / 2); ax[0].set_xticklabels(profs); ax[0].set_ylabel("epoch time (s)  mean, 95% CI")
        ax[0].legend(fontsize=7); ax[0].set_title("Total FL time")
        comp = {"compute": g.train_total_s_mean + g.agg_total_s_mean, "control plane": g.cp_total_s_mean, "data plane": g.data_total_s_mean}
        for i, cfg in enumerate(cfgs):                                  # (b) stacked decomposition
            gg = g[g.cfg == cfg].set_index("profile").reindex(profs); bottom = np.zeros(len(profs))
            for j, (nm, col) in enumerate([("compute", gg.train_total_s_mean + gg.agg_total_s_mean), ("control plane", gg.cp_total_s_mean), ("data plane", gg.data_total_s_mean)]):
                ax[1].bar(np.arange(len(profs)) + i * w, col.values, w, bottom=bottom, color=["#9aa7b8", "#1f3a5f", "#d98c3f"][j], label=nm if i == 0 else None, edgecolor="white", linewidth=.3)
                bottom += col.values
        ax[1].set_xticks(np.arange(len(profs)) + 0.4 - w / 2); ax[1].set_xticklabels(profs); ax[1].legend(fontsize=7)
        ax[1].set_title("Decomposition (bars per profile: %s)" % ", ".join(cfgs)); ax[1].set_ylabel("seconds")
        fig.suptitle("mode=%s resume=%s C=%s R=%s" % (mode, res, clients, rounds)); fig.tight_layout()
        fig.savefig(os.path.join(ROOT, "results", "plots", "epoch_%s_res%s_C%s_R%s.png" % (mode, res, clients, rounds)), dpi=150); plt.close(fig)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--stage", required=True); ap.add_argument("--local-test", action="store_true")
    a = ap.parse_args()
    d = load_valid(a.stage, a.local_test)
    c = cells(d); h = pooled_handshakes(d)
    if len(h): c = c.merge(h, on=KEY, how="left")
    c.to_csv(os.path.join(ROOT, "results", "stats_cells.csv"), index=False)
    v = vs_k1(d); v.to_csv(os.path.join(ROOT, "results", "stats_vs_K1.csv"), index=False)
    plots(d, c)
    low = c[c.n_runs < 10]
    print("cells: %d | cells with fewer than 10 runs: %d" % (len(c), len(low)))
    if len(low): print("WARNING: your supervisor asked for at least 10-20 repeats; run matrix.py again to complete them.")
    print("saved results/stats_cells.csv, results/stats_vs_K1.csv, results/plots/*.png")
