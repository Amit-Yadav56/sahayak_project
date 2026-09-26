"""
ml/eligibility_matcher/train.py
==================================
Trains an XGBoost regressor on synthetic (user, scheme) pairs to predict
an eligibility score in [0, 1], then evaluates it on a held-out test set.

The model predicts a continuous score rather than one of the four status
classes directly — the score_to_status() bucketing happens at inference
time, making it easy to adjust thresholds later without retraining.

Run:  python -m ml.eligibility_matcher.train
Output: ml/eligibility_matcher/model.json  (XGBoost booster, loadable
        with xgboost.Booster().load_model())
"""

import json
import time
from pathlib import Path

import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

from ml.eligibility_matcher.synthesize import generate, score_to_status, STATUS_THRESHOLDS
from ml.eligibility_matcher.features import FEATURE_NAMES

MODEL_OUT = Path("ml/eligibility_matcher/model.json")
SEED = 42


def main():
    print("Generating synthetic training data...")
    t0 = time.time()
    X, y = generate()
    print(f"  {len(X):,} examples in {time.time()-t0:.1f}s  shape={X.shape}\n")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.15, random_state=SEED
    )

    print(f"Train: {len(X_train):,}   Test (held out): {len(X_test):,}\n")

    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=FEATURE_NAMES)
    dtest  = xgb.DMatrix(X_test,  label=y_test,  feature_names=FEATURE_NAMES)

    params = {
        "objective":        "reg:squarederror",
        "eval_metric":      "mae",
        "max_depth":        6,
        "eta":              0.1,
        "subsample":        0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 5,
        "seed":             SEED,
        "verbosity":        0,
    }

    print("Training XGBoost...")
    t1 = time.time()
    evals_result = {}
    model = xgb.train(
        params,
        dtrain,
        num_boost_round=300,
        evals=[(dtrain, "train"), (dtest, "test")],
        early_stopping_rounds=20,
        evals_result=evals_result,
        verbose_eval=50,
    )
    print(f"  Done in {time.time()-t1:.1f}s  "
          f"best round={model.best_iteration}  "
          f"best test MAE={model.best_score:.4f}\n")

    # --- Evaluation ---
    y_pred = model.predict(dtest)
    mae  = mean_absolute_error(y_test, y_pred)
    # within-0.1 accuracy (how often the predicted score is within ±0.1 of true)
    within_01 = float(np.mean(np.abs(y_pred - y_test) < 0.10))
    print(f"Test MAE:              {mae:.4f}")
    print(f"Within ±0.10:          {100*within_01:.1f}%\n")

    # Status-classification accuracy (how often the predicted status bucket
    # matches the true status bucket)
    true_statuses = np.array([score_to_status(s) for s in y_test])
    pred_statuses = np.array([score_to_status(s) for s in y_pred])
    status_acc = float(np.mean(true_statuses == pred_statuses))
    print(f"Status bucket accuracy: {100*status_acc:.1f}%")

    # Per-status breakdown
    print("\nPer-status breakdown (true label → predicted):")
    print(f"  {'Status':<22} {'True N':>8} {'Correct':>8} {'Accuracy':>10}")
    for _, status in STATUS_THRESHOLDS:
        mask = true_statuses == status
        n = int(mask.sum())
        if n == 0:
            continue
        correct = int((pred_statuses[mask] == status).sum())
        print(f"  {status:<22} {n:>8,} {correct:>8,} {100*correct/n:>9.1f}%")

    # Feature importance
    print("\nTop 15 features by gain:")
    importance = model.get_score(importance_type="gain")
    top = sorted(importance.items(), key=lambda x: -x[1])[:15]
    max_gain = top[0][1]
    for feat, gain in top:
        bar = "█" * int(30 * gain / max_gain)
        print(f"  {feat:<28} {bar}")

    # Save
    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(MODEL_OUT))
    print(f"\nSaved model → {MODEL_OUT}")


if __name__ == "__main__":
    main()
