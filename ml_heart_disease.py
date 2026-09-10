"""
Heart disease risk screening, trained on the real UCI Heart Disease
(Cleveland) dataset — https://archive.ics.uci.edu/dataset/45/heart+disease
303 patients, 13 clinical features, 297 after dropping rows with missing
values. This is a screening aid only, not a diagnosis: it reports the
model's actual cross-validated accuracy (see HEART_MODEL_META after
training) rather than an invented number, and every prediction is shown
alongside that accuracy so a doctor can judge how much to weigh it.

Training is offline (train_and_save(), requires network access to fetch
the dataset) and produces heart_disease_model.joblib, which the running
app loads read-only. is_available() is False until that file exists.
"""

import os

try:
    import joblib
except ImportError:
    joblib = None

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heart_disease_model.joblib")

# (field_name, label, kind, options-or-range) — drives both the HTML form and predict()'s input order.
FIELDS = [
    ("age", "Age (years)", "number", (1, 120)),
    ("sex", "Sex", "select", [(1, "Male"), (0, "Female")]),
    ("cp", "Chest pain type", "select", [
        (1, "Typical angina"), (2, "Atypical angina"), (3, "Non-anginal pain"), (4, "Asymptomatic"),
    ]),
    ("trestbps", "Resting blood pressure (mm Hg)", "number", (50, 260)),
    ("chol", "Serum cholesterol (mg/dl)", "number", (50, 700)),
    ("fbs", "Fasting blood sugar > 120 mg/dl", "select", [(1, "Yes"), (0, "No")]),
    ("restecg", "Resting ECG result", "select", [
        (0, "Normal"), (1, "ST-T wave abnormality"), (2, "Probable/definite left ventricular hypertrophy"),
    ]),
    ("thalach", "Maximum heart rate achieved", "number", (50, 250)),
    ("exang", "Exercise-induced angina", "select", [(1, "Yes"), (0, "No")]),
    ("oldpeak", "ST depression induced by exercise (relative to rest)", "decimal", (0, 10)),
    ("slope", "Slope of peak exercise ST segment", "select", [
        (1, "Upsloping"), (2, "Flat"), (3, "Downsloping"),
    ]),
    ("ca", "Number of major vessels colored by fluoroscopy (0-3)", "select", [(0, "0"), (1, "1"), (2, "2"), (3, "3")]),
    ("thal", "Thalassemia", "select", [(3, "Normal"), (6, "Fixed defect"), (7, "Reversible defect")]),
]
FIELD_NAMES = [f[0] for f in FIELDS]

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


def train_and_save() -> dict:
    """Offline, one-time (re-)training. Requires network access (fetches
    the dataset from UCI) and scikit-learn/pandas/ucimlrepo installed.
    Not run automatically by the app — run manually when you want to
    (re)produce heart_disease_model.joblib."""
    from datetime import datetime

    import joblib as _joblib
    import pandas as pd
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from ucimlrepo import fetch_ucirepo

    heart_disease = fetch_ucirepo(id=45)
    df = pd.concat([heart_disease.data.features, heart_disease.data.targets], axis=1).dropna()

    X = df[FIELD_NAMES]
    y = (df["num"] > 0).astype(int)

    model = Pipeline([("scale", StandardScaler()), ("clf", LogisticRegression(max_iter=1000))])
    cv_scores = cross_val_score(model, X, y, cv=5)
    model.fit(X, y)

    bundle = {
        "model": model,
        "dataset": "UCI Heart Disease (Cleveland)",
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
