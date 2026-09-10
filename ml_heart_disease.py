"""
Heart disease risk screening, trained on a real public heart disease
dataset (Kaggle-format CSV derived from the UCI Cleveland data; 303
patient records, 13 clinical features) saved locally as
heart_disease_kaggle.csv. This is a screening aid only, not a
diagnosis: every prediction is shown alongside the model's actual
cross-validated accuracy (see model_meta()) rather than an invented
number, so a doctor can judge how much to weigh it.

Training is offline (train_and_save(), reads the local CSV) and
produces heart_disease_model.joblib, which the running app loads
read-only. is_available() is False until that file exists.

Note: this dataset's categorical codes are 0-indexed (cp 0-3, restecg
0-2, slope 0-2, thal 0-3), which is NOT the same coding as the original
UCI Cleveland files (which use cp 1-4, thal 3/6/7 etc). The FIELDS
options below match this dataset's coding — don't mix data from the two
encodings without converting one of them.
"""

import os

try:
    import joblib
except ImportError:
    joblib = None

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heart_disease_model.joblib")
DEFAULT_CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heart_disease_kaggle.csv")

# (field_name, label, kind, options-or-range) — drives both the HTML form and predict()'s input order.
FIELDS = [
    ("age", "Age (years)", "number", (1, 120)),
    ("sex", "Sex", "select", [(1, "Male"), (0, "Female")]),
    ("cp", "Chest pain type", "select", [
        (0, "Typical angina"), (1, "Atypical angina"), (2, "Non-anginal pain"), (3, "Asymptomatic"),
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
        (0, "Upsloping"), (1, "Flat"), (2, "Downsloping"),
    ]),
    ("ca", "Number of major vessels colored by fluoroscopy", "select", [(0, "0"), (1, "1"), (2, "2"), (3, "3"), (4, "4")]),
    ("thal", "Thalassemia", "select", [(0, "Not recorded"), (1, "Normal"), (2, "Fixed defect"), (3, "Reversible defect")]),
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


def train_and_save(csv_path: str = DEFAULT_CSV_PATH) -> dict:
    """Offline, one-time (re-)training from the local CSV. Requires
    scikit-learn/pandas/joblib installed. Not run automatically by the
    app — run manually when you want to (re)produce
    heart_disease_model.joblib."""
    from datetime import datetime

    import joblib as _joblib
    import pandas as pd
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    df = pd.read_csv(csv_path).drop_duplicates()

    X = df[FIELD_NAMES]
    # This CSV's target column is inverted from the intuitive convention:
    # target=0 rows have the disease-consistent profile (higher oldpeak,
    # more vessels colored, ~55% exercise-induced angina) and target=1
    # rows look healthier (~14% angina). Flip it so y=1 always means
    # "heart disease indicators present", matching every label in FIELDS
    # and the risk_label text in predict().
    y = 1 - df["target"].astype(int)

    model = Pipeline([("scale", StandardScaler()), ("clf", LogisticRegression(max_iter=1000))])
    cv_scores = cross_val_score(model, X, y, cv=5)
    model.fit(X, y)

    bundle = {
        "model": model,
        "dataset": "Heart Disease dataset (Kaggle CSV, UCI-derived)",
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
