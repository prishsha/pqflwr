"""Prepare data once.
Real data:      python fl/prepare_data.py --csv-dir ~/cicids2017
Pipeline test:  python fl/prepare_data.py --synthetic"""
import argparse, glob, os, numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--csv-dir"); ap.add_argument("--synthetic", action="store_true")
ap.add_argument("--max-rows", type=int, default=300000)
ap.add_argument("--out", default="data/processed.npz")
a = ap.parse_args()
rng = np.random.default_rng(1)

if a.synthetic:
    from sklearn.datasets import make_classification
    X, y = make_classification(n_samples=60000, n_features=78, n_informative=20, weights=[0.8, 0.2], random_state=1)
else:
    import pandas as pd
    files = sorted(glob.glob(os.path.join(os.path.expanduser(a.csv_dir), "*.csv")))
    assert files, "no CSV files found in --csv-dir"
    df = pd.concat([pd.read_csv(f, encoding="latin1", low_memory=False) for f in files], ignore_index=True)
    df.columns = [c.strip() for c in df.columns]
    df = df.replace([np.inf, -np.inf], np.nan).dropna().drop_duplicates()
    y = (df["Label"].astype(str).str.strip().str.upper() != "BENIGN").astype(int).values
    X = df.drop(columns=["Label"]).select_dtypes("number")
    X = X.loc[:, X.std() > 0].values
    print("rows after cleaning:", len(df), " attack fraction: %.3f" % y.mean())

if len(X) > a.max_rows:
    keep = rng.choice(len(X), a.max_rows, replace=False); X, y = X[keep], y[keep]
perm = rng.permutation(len(X)); X, y = X[perm], y[perm]
n_tr = int(0.8 * len(X))
Xtr, Xte, ytr, yte = X[:n_tr], X[n_tr:], y[:n_tr], y[n_tr:]
mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-8          # standardise with TRAIN statistics only
Xtr, Xte = ((Xtr - mu) / sd).astype(np.float32), ((Xte - mu) / sd).astype(np.float32)
os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
np.savez(a.out, Xtr=Xtr, ytr=ytr.astype(np.int64), Xte=Xte, yte=yte.astype(np.int64))
print("saved", a.out, "train", Xtr.shape, "test", Xte.shape)
