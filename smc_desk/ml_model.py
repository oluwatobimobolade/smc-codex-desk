"""Dependency-free ML core for SMC setup scoring.

Deliberately a *regularized logistic regression* in pure numpy, not XGBoost.
On a weak, small, regime-dependent signal, a high-capacity tree model + tuner
overfits spectacularly; a well-regularized linear model is the honest first
question: "is there ANY linearly-separable edge in these features, out of
sample, after costs?" If a linear model can't find it, a deeper model finding
it is almost always overfitting. Trees can be added later behind the same API.

Leakage discipline lives in the trainer (time-split, forward-only labels,
threshold chosen on train only). This file is just the estimator + scaler.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


class StandardScaler:
    def fit(self, X: np.ndarray) -> "StandardScaler":
        self.mean_ = X.mean(axis=0)
        self.std_ = X.std(axis=0)
        self.std_ = np.where(self.std_ == 0, 1.0, self.std_)
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        return (X - self.mean_) / self.std_

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        return self.fit(X).transform(X)


class LogisticRegression:
    """L2-regularized logistic regression via full-batch gradient descent."""

    def __init__(self, l2: float = 2.0, lr: float = 0.2, n_iter: int = 4000):
        self.l2 = l2
        self.lr = lr
        self.n_iter = n_iter

    def fit(self, X: np.ndarray, y: np.ndarray, sample_weight: np.ndarray | None = None) -> "LogisticRegression":
        n, d = X.shape
        Xb = np.hstack([np.ones((n, 1)), X])
        w = np.zeros(d + 1)
        sw = np.ones(n) if sample_weight is None else np.asarray(sample_weight, dtype=float)
        sw = sw / max(sw.mean(), 1e-9)
        for _ in range(self.n_iter):
            z = np.clip(Xb @ w, -30, 30)
            p = 1.0 / (1.0 + np.exp(-z))
            grad = Xb.T @ ((p - y) * sw) / n
            reg = self.l2 * np.r_[0.0, w[1:]] / n   # do not regularize the intercept
            w -= self.lr * (grad + reg)
        self.w_ = w
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        Xb = np.hstack([np.ones((X.shape[0], 1)), X])
        z = np.clip(Xb @ self.w_, -30, 30)
        return 1.0 / (1.0 + np.exp(-z))


class XGBoostClassifier:
    """XGBoost wrapper to provide the same interface as LogisticRegression."""

    def __init__(self, n_estimators: int = 100, max_depth: int = 3, learning_rate: float = 0.1, **kwargs: Any):
        self.params = {
            "max_depth": max_depth,
            "eta": learning_rate,
            "objective": "binary:logistic",
            "eval_metric": "logloss",
        }
        self.params.update(kwargs)
        self.n_estimators = n_estimators
        self.model = None

    def fit(self, X: np.ndarray, y: np.ndarray, sample_weight: np.ndarray | None = None) -> "XGBoostClassifier":
        import xgboost as xgb
        dtrain = xgb.DMatrix(X, label=y, weight=sample_weight)
        self.model = xgb.train(self.params, dtrain, num_boost_round=self.n_estimators)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        import xgboost as xgb
        dtest = xgb.DMatrix(X)
        return self.model.predict(dtest)


def expectancy(r: np.ndarray) -> dict:
    """Trade-relevant stats for an array of realized R multiples."""
    r = np.asarray(r, dtype=float)
    if r.size == 0:
        return {"n": 0, "win_rate": None, "avg_r": None, "total_r": 0.0, "profit_factor": None}
    wins = r[r > 0.05]
    losses = r[r < -0.05]
    gl = abs(losses.sum())
    return {
        "n": int(r.size),
        "win_rate": round(float((r > 0.05).mean()), 4),
        "avg_r": round(float(r.mean()), 4),
        "total_r": round(float(r.sum()), 3),
        "profit_factor": round(float(wins.sum() / gl), 3) if gl > 0 else None,
    }


def load_model(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def predict_proba_payload(payload: dict, X_raw: np.ndarray) -> np.ndarray:
    """Score a raw feature matrix (columns in payload['feature_names'] order)."""
    mean = np.asarray(payload["scaler_mean"], dtype=float)
    std = np.asarray(payload["scaler_std"], dtype=float)
    Xs = (np.asarray(X_raw, dtype=float) - mean) / std
    
    if payload.get("model") == "xgboost":
        import xgboost as xgb
        bst = xgb.Booster()
        raw = payload["xgb_json"]
        if isinstance(raw, str):
            raw = bytearray(raw.encode("utf-8"))
        bst.load_model(raw)
        return bst.predict(xgb.DMatrix(Xs))
    else:
        w = np.asarray(payload["weights"], dtype=float)
        Xb = np.hstack([np.ones((Xs.shape[0], 1)), Xs])
        z = np.clip(Xb @ w, -30, 30)
        return 1.0 / (1.0 + np.exp(-z))


def save_model(path: str | Path, model, scaler: StandardScaler,
               feature_names: list[str], threshold: float, meta: dict | None = None) -> None:
    payload = {
        "feature_names": feature_names,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_std": scaler.std_.tolist(),
        "threshold": float(threshold),
        "meta": meta or {},
    }
    
    if isinstance(model, LogisticRegression):
        payload["model"] = "logistic_regression_l2"
        payload["weights"] = model.w_.tolist()
        payload["l2"] = model.l2
    else:
        payload["model"] = "xgboost"
        raw = model.model.save_raw(format="json")
        payload["xgb_json"] = raw.decode("utf-8") if isinstance(raw, bytes) else raw

    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
