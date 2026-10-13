"""Stage 5: tables + plots from results/runs.csv.   python analysis/summarize.py"""
import os, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
df = pd.read_csv(os.path.join(ROOT, "results", "runs.csv"))
df = df[(df.local_test == False) & (df.get("tcpdump_dropped", 0).fillna(0) == 0)]     # drop test runs and invalid runs
key = ["mode", "resume", "clients", "rounds", "cfg"]
agg = df.groupby(key).agg(n_runs=("run_id", "count"), logical_s=("logical_total_s", "mean"), logical_sd=("logical_total_s", "std"),
      wall_s=("wall_total_s", "mean"), setup_s=("setup_total_s", "mean"), rounds_s=("rounds_total_s", "mean"),
      n_syn=("n_syn", "mean"), n_clienthello=("n_clienthello", "mean"), n_resumed=("n_resumed_psk", "mean"),
      hs_ms=("hs_mean_ms", "mean"), hs_bytes=("hs_frame_bytes_mean", "mean"), retx=("retx_total", "mean"),
      cpu_srv_proxy=("cpu_srv_proxy_s", "mean"), cpu_cli_proxy=("cpu_cli_proxy_s", "mean"), f1=("final_f1", "mean")).reset_index()
agg["hs_per_client_round"] = agg.n_clienthello / (agg.clients * agg.rounds)           # measured, not assumed
base = ["mode", "clients", "rounds"]
plain = agg[agg.cfg == "PLAIN"].drop_duplicates(base)[base + ["logical_s"]].rename(columns={"logical_s": "plain_s"})
k1 = agg[agg.cfg == "K1"][base + ["resume", "logical_s", "hs_ms", "n_clienthello"]].rename(columns={"logical_s": "k1_s", "hs_ms": "k1_hs_ms", "n_clienthello": "k1_nhs"})
agg = agg.merge(plain, on=base, how="left").merge(k1, on=base + ["resume"], how="left")
agg["inflation_vs_K1_pct"] = 100 * (agg.logical_s - agg.k1_s) / agg.k1_s
agg["inflation_vs_PLAIN_pct"] = 100 * (agg.logical_s - agg.plain_s) / agg.plain_s
# analytic estimate: handshakes of ONE client are sequential, different clients are parallel
agg["analytic_vs_K1_pct"] = 100 * ((agg.n_clienthello * agg.hs_ms - agg.k1_nhs * agg.k1_hs_ms) / 1000 / agg.clients) / agg.k1_s
agg.to_csv(os.path.join(ROOT, "results", "summary.csv"), index=False)
print(agg.round(3).to_string())
for (mode, resume), g in agg.groupby(["mode", "resume"]):
    cl = sorted(g.clients.unique()); fig, ax = plt.subplots(1, len(cl), figsize=(4.2 * len(cl), 3.6), sharey=True, squeeze=False)
    for i, c in enumerate(cl):
        for cfg, gg in g[(g.clients == c) & (g.cfg != "PLAIN")].groupby("cfg"):
            gg = gg.sort_values("rounds"); ax[0][i].plot(gg.rounds, gg.inflation_vs_PLAIN_pct, marker="o", label=cfg)
        ax[0][i].set_title("%d clients" % c); ax[0][i].set_xlabel("rounds"); ax[0][i].grid(alpha=.3)
    ax[0][0].set_ylabel("time inflation vs no-TLS (%)"); ax[0][-1].legend()
    fig.suptitle("mode=%s, resumption=%s" % (mode, resume)); fig.tight_layout()
    fig.savefig(os.path.join(ROOT, "results", "inflation_%s_res%s.png" % (mode, resume)), dpi=160); plt.close(fig)
print("saved results/summary.csv and plots")
