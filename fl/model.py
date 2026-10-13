"""Tiny numpy MLP (features -> 128 -> 64 -> 2). No torch needed, so processes start fast."""
import numpy as np

def init_params(n_in, n_classes=2, seed=0):
    rng = np.random.default_rng(seed)
    sizes = [n_in, 128, 64, n_classes]
    p = []
    for a, b in zip(sizes[:-1], sizes[1:]):
        p.append((rng.standard_normal((a, b)) * np.sqrt(2.0 / a)).astype(np.float32))
        p.append(np.zeros(b, dtype=np.float32))
    return p

def _forward(p, X):
    h1 = np.maximum(X @ p[0] + p[1], 0)
    h2 = np.maximum(h1 @ p[2] + p[3], 0)
    z = h2 @ p[4] + p[5]
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return h1, h2, e / e.sum(axis=1, keepdims=True)

def loss_acc_f1(p, X, y):
    probs = _forward(p, X)[2]
    loss = float(-np.log(probs[np.arange(len(y)), y] + 1e-9).mean())
    pred = probs.argmax(axis=1)
    acc = float((pred == y).mean())
    f1s = []
    for c in np.unique(y):
        tp = np.sum((pred == c) & (y == c)); fp = np.sum((pred == c) & (y != c)); fn = np.sum((pred != c) & (y == c))
        f1s.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return loss, acc, float(np.mean(f1s))

def train_epoch(p, X, y, lr=0.05, batch=256, seed=0):
    p = [a.copy() for a in p]
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(X))
    for s in range(0, len(X), batch):
        b = idx[s:s + batch]
        xb, yb = X[b], y[b]
        h1, h2, probs = _forward(p, xb)
        d3 = probs.copy(); d3[np.arange(len(b)), yb] -= 1; d3 /= len(b)
        g4 = h2.T @ d3; g5 = d3.sum(0)
        d2 = (d3 @ p[4].T) * (h2 > 0)
        g2 = h1.T @ d2; g3 = d2.sum(0)
        d1 = (d2 @ p[2].T) * (h1 > 0)
        g0 = xb.T @ d1; g1 = d1.sum(0)
        for i, g in enumerate([g0, g1, g2, g3, g4, g5]):
            p[i] -= lr * g.astype(np.float32)
    return p
