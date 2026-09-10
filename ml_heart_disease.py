"""
Heart disease risk screening, trained on the real multi-site UCI Heart
Disease dataset (Cleveland + Hungary + Switzerland + VA Long Beach; 920
raw records) saved locally as heart_disease_uci_full.csv. This is a
screening aid only, not a diagnosis: every prediction is shown alongside
the model's actual cross-validated accuracy (see model_meta()) rather
than an invented number.

Training is offline (train_and_save(), reads the local CSV) and produces
heart_disease_model.joblib, which the running app loads read-only.
is_available() is False until that file exists.

Data notes (why the model uses 10 fields, not the original 13):
- "ca" (vessels colored by fluoroscopy) and "thal" (thalassemia) are
  missing in 90-99% of the Hungary/Switzerland/VA Long Beach rows, and
  "slope" is missing in 51-65% of them. Requiring all 13 fields leaves
  ~300 usable rows (Cleveland only); dropping these three unlocks ~661
  real rows across 3 sites. Chose data volume over those 3 fields.
- Switzerland's "chol" column is 0 for every single row -- a known
  missing-value placeholder in this dataset, not a real cholesterol
  reading of zero (medically implausible). Treated as missing here.
- The multi-class "num" target (0-4 severity) is binarized to
  disease-present/absent, same as the previous version. Verified this
  dataset's target direction is NOT inverted (unlike the single-site
  Kaggle CSV used previously) by checking that the disease-positive
  group has the expected worse profile (older, higher oldpeak, more
  exercise-induced angina) before training on it.
"""

import os

try:
    import joblib
except ImportError:
    joblib = None

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heart_disease_model.joblib")
DEFAULT_CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heart_disease_uci_full.csv")

# (field_name, label, kind, options-or-range) — drives both the HTML form and predict()'s input order.
FIELDS = [
    ("age", "Age (years)", "number", (1, 120)),
    ("sex", "Sex", "select", [(1, "Male"), (0, "Female")]),
    ("cp", "Chest pain type", "select", [
        (0, "Typical angina"), (1, "Atypical angina"), (2, "Non-anginal"), (3, "Asymptomatic"),
    ]),
    ("trestbps", "Resting blood pressure (mm Hg)", "number", (50, 260)),
    ("chol", "Serum cholesterol (mg/dl)", "number", (50, 700)),
    ("fbs", "Fasting blood sugar > 120 mg/dl", "select", [(1, "Yes"), (0, "No")]),
    ("restecg", "Resting ECG result", "select", [
        (0, "Normal"), (1, "ST-T wave abnormality"), (2, "Probable/definite left ventricular hypertrophy"),
    ]),
    ("thalach", "Maximum heart rate achieved", "number", (50, 250)),
    ("exang", "Exercise-induced angina", "select", [(1, "Yes"), (0, "No")]),
    ("oldpeak", "ST depression induced by exercise (relative to rest)", "decimal", (-5, 10)),
]
FIELD_NAMES = [f[0] for f in FIELDS]

CP_MAP = {"typical angina": 0, "atypical angina": 1, "non-anginal": 2, "asymptomatic": 3}
RESTECG_MAP = {"normal": 0, "st-t abnormality": 1, "lv hypertrophy": 2}

_cache = None


def is_available() -> bool:
    return joblib is not None and os.path.exists(MODEL_PATH)


def _load():
    global _cache
    if _cache is None:
        _cache = joblib.load(MODEL_PATH)
    return _cache


def model_meta() -> dict:
    """Dataset/accuracy provenance to disclose alongside any prediction."""
    bundle = _load()
    return {
        "dataset": bundle["dataset"],
        "n_samples": bundle["n_samples"],
        "cv_accuracy_mean": bundle["cv_accuracy_mean"],
        "cv_accuracy_std": bundle["cv_accuracy_std"],
        "trained_at": bundle["trained_at"],
    }


def predict(features: dict) -> dict:
    """features: {field_name: value} for every name in FIELD_NAMES.
    Returns {"probability": float 0-1, "risk_label": str}."""
    import pandas as pd

    bundle = _load()
    model = bundle["model"]
    row = pd.DataFrame([[float(features[name]) for name in FIELD_NAMES]], columns=FIELD_NAMES)
    probability = float(model.predict_proba(row)[0][1])
    risk_label = "Higher likelihood of heart disease indicators" if probability >= 0.5 else "Lower likelihood of heart disease indicators"
    return {"probability": probability, "risk_label": risk_label}


def _load_and_clean(csv_path: str):
    import numpy as np
    import pandas as pd

    df = pd.read_csv(csv_path)

    # Known missing-value placeholder, not a real reading of zero.
    df.loc[df["chol"] == 0, "chol"] = np.nan

    df["sex"] = df["sex"].map({"Male": 1, "Female": 0})
    df["cp"] = df["cp"].map(CP_MAP)
    df["restecg"] = df["restecg"].map(RESTECG_MAP)
    df["fbs"] = df["fbs"].map({True: 1, False: 0})
    df["exang"] = df["exang"].map({True: 1, False: 0})
    df["thalach"] = df["thalch"]  # source column is named "thalch"

    df = df.dropna(subset=FIELD_NAMES + ["num"])
    return df


def train_and_save(csv_path: str = DEFAULT_CSV_PATH) -> dict:
    """Offline, one-time (re-)training from the local CSV. Requires
    scikit-learn/pandas/joblib installed. Not run automatically by the
    app — run manually when you want to (re)produce
    heart_disease_model.joblib."""
    from datetime import datetime

    import joblib as _joblib
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    df = _load_and_clean(csv_path)

    X = df[FIELD_NAMES]
    y = (df["num"] > 0).astype(int)

    model = Pipeline([("scale", StandardScaler()), ("clf", LogisticRegression(max_iter=1000))])
    cv_scores = cross_val_score(model, X, y, cv=5)
    model.fit(X, y)

    bundle = {
        "model": model,
        "dataset": "UCI Heart Disease, multi-site (Cleveland/Hungary/Switzerland/VA Long Beach)",
        "n_samples": len(df),
        "cv_accuracy_mean": round(float(cv_scores.mean()), 4),
        "cv_accuracy_std": round(float(cv_scores.std()), 4),
        "trained_at": datetime.now().isoformat(timespec="seconds"),
    }
    _joblib.dump(bundle, MODEL_PATH)
    return bundle


if __name__ == "__main__":
    result = train_and_save()
    print(f"Trained on {result['n_samples']} real patients from {result['dataset']}.")
    print(f"5-fold cross-validated accuracy: {result['cv_accuracy_mean']*100:.1f}% (+/- {result['cv_accuracy_std']*100:.1f}%)")
    print(f"Saved to {MODEL_PATH}")
