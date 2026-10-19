import argparse, json, time, numpy as np, flwr as fl
from flwr.common import ndarrays_to_parameters, parameters_to_ndarrays
from model import init_params, loss_acc_f1

ap = argparse.ArgumentParser()
ap.add_argument("--addr", default="127.0.0.1:9092"); ap.add_argument("--clients", type=int, required=True)
ap.add_argument("--rounds", type=int, required=True); ap.add_argument("--round-offset", type=int, default=0)
ap.add_argument("--init"); ap.add_argument("--out-weights", required=True)
ap.add_argument("--data", required=True); ap.add_argument("--log", required=True)
ap.add_argument("--ready-file", required=True)
a = ap.parse_args()

d = np.load(a.data); Xte, yte = d["Xte"], d["yte"]
if a.init:
    z = np.load(a.init); init = [z["p%d" % i] for i in range(6)]
else:
    init = init_params(Xte.shape[1], 2, seed=0)
log = {"t_first_configure": None, "rounds": [], "bytes_model": int(sum(x.nbytes for x in init))}
t_start = {}; t_dispatch = {}; t_agg0 = {}; agg_s = {}; eval_s = {}

def eval_fn(server_round, params, config):
    te0 = time.perf_counter()
    loss, acc, f1 = loss_acc_f1(params, Xte, yte)
    if server_round > 0:
        eval_s[server_round] = time.perf_counter() - te0
        log["rounds"].append({"round": server_round + a.round_offset, "t_start": t_start.get(server_round),
                              "t_dispatch": t_dispatch.get(server_round),   # all clients registered, FitIns about to be sent
                              "t_agg0": t_agg0.get(server_round),           # all client updates received
                              "agg_s": agg_s.get(server_round), "eval_s": eval_s.get(server_round),
                              "t_end": time.time(), "loss": loss, "acc": acc, "f1": f1})
    return loss, {"acc": acc, "f1": f1}

class S(fl.server.strategy.FedAvg):
    latest = None
    def configure_fit(self, server_round, parameters, client_manager):
        now = time.time()
        if log["t_first_configure"] is None: log["t_first_configure"] = now
        t_start[server_round] = now
        res = super().configure_fit(server_round, parameters, client_manager)   # waits until C clients are registered
        t_dispatch[server_round] = time.time()
        return res
    def aggregate_fit(self, server_round, results, failures):
        t_agg0[server_round] = time.time(); ta = time.perf_counter()
        params, m = super().aggregate_fit(server_round, results, failures)
        agg_s[server_round] = time.perf_counter() - ta
        if params is not None: S.latest = parameters_to_ndarrays(params)
        return params, m

strat = S(fraction_fit=1.0, fraction_evaluate=0.0, min_fit_clients=a.clients, min_evaluate_clients=0,
          min_available_clients=a.clients, evaluate_fn=eval_fn,
          initial_parameters=ndarrays_to_parameters(init))
open(a.ready_file, "w").close()
fl.server.start_server(server_address=a.addr, config=fl.server.ServerConfig(num_rounds=a.rounds), strategy=strat)
np.savez(a.out_weights, **{"p%d" % i: x for i, x in enumerate(S.latest)})
log["cpu_s"] = time.process_time()
json.dump(log, open(a.log, "w"))
