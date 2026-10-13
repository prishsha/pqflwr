import argparse, json, os, time, numpy as np, flwr as fl
from model import train_epoch

ap = argparse.ArgumentParser()
ap.add_argument("--cid", type=int, required=True); ap.add_argument("--num-clients", type=int, required=True)
ap.add_argument("--server", default="127.0.0.1:9093"); ap.add_argument("--data", required=True)
ap.add_argument("--ready-file", required=True); ap.add_argument("--go-file", required=True)
ap.add_argument("--log", required=True); ap.add_argument("--epochs", type=int, default=1)
ap.add_argument("--seed", type=int, default=0)
a = ap.parse_args()

d = np.load(a.data)
perm = np.random.default_rng(a.seed).permutation(len(d["Xtr"]))     # same permutation in every client
idx = np.array_split(perm, a.num_clients)[a.cid]                    # IID shard i of C
X, y = d["Xtr"][idx], d["ytr"][idx]
state = {"first_fit": None, "fit_s": []}

class C(fl.client.NumPyClient):
    def get_parameters(self, config): return []
    def fit(self, parameters, config):
        if state["first_fit"] is None: state["first_fit"] = time.time()
        t = time.perf_counter(); p = parameters
        for e in range(a.epochs): p = train_epoch(p, X, y, seed=a.seed + e)
        state["fit_s"].append(time.perf_counter() - t)
        return p, len(X), {}
    def evaluate(self, parameters, config): return 0.0, len(X), {}

open(a.ready_file, "w").close()                          # imports + data loaded
while not os.path.exists(a.go_file): time.sleep(0.005)   # barrier: all clients connect together
t_go = time.time()
fl.client.start_client(server_address=a.server, client=C().to_client(), insecure=True)
json.dump({"cid": a.cid, "t_go": t_go, "t_first_fit": state["first_fit"], "fit_s": state["fit_s"],
           "cpu_s": time.process_time()}, open(a.log, "w"))
