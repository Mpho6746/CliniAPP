# MediCare Clinic — Flask port

A Python/Flask rewrite of the original Flutter/Dart clinic app. Same
workflow, same six stations (Admin, Doctor, Nursing, Pharmacist, Records,
Statistics), same in-memory data model — now rendered as server-side
HTML instead of a Flutter widget tree.

## Run it

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:5000** in a browser.

## What maps to what

| Dart (original)                    | Python (this port)                          |
|-------------------------------------|----------------------------------------------|
| `Patient`, `PatientFile`, `Doctor`  | `models.py` dataclasses of the same name     |
| `DataRepository` singleton          | `models.store` (a `DataStore` instance)      |
| `FileStatus` / `Priority` enums     | string constants in `models.py`              |
| Each `StatelessWidget`/`StatefulWidget` screen | a Flask route + Jinja template in `templates/` |
| `Navigator.push(...)`               | `redirect(url_for(...))`                     |
| `setState(...)`                     | mutating the dataclass, then re-rendering on the next request |
| `SnackBar`                          | `flash()` messages shown at the top of the page |
| Doctor login session (`loggedInDoctor`) | Flask `session['doctor_username']`      |

## Machine learning: diagnosis suggestions

On a patient's file, a doctor can type a free-text symptom description and
click **Suggest possible diagnoses**. This runs a small text classifier
(TF-IDF + Logistic Regression, in `ml/diagnosis_model.py`) trained on ~65
hand-written example sentences across 16 common outpatient presentations
(common cold, UTI, migraine, gastroenteritis, asthma exacerbation, etc.),
and returns the top 3 matches with confidence scores.

**This is a demo-quality model, not a clinical tool:**
- It's trained on a few dozen synthetic examples per label, not real
  clinical data, and hasn't been validated against real cases at all.
- It only knows the 16 labels it was trained on — anything outside that
  list will just get the closest-sounding match, which may be wrong.
- The UI always shows a disclaimer next to suggestions for this reason.
  Don't remove it, and don't wire this model into anything that could
  reach a patient directly — it's a hint for a doctor to weigh alongside
  their own judgment, nothing more.
- To extend it: add more example sentences (or new labels) to
  `TRAINING_DATA` in `ml/diagnosis_model.py` — it retrains automatically
  each time the app starts, no separate build step needed.

## Notes / things worth doing before real use

- **Data is in-memory only**, exactly like the original — it resets whenever
  the server restarts. If you want it to persist, swap `models.store` for a
  real database (SQLite is the easiest first step).
- **Doctor PINs are stored in plain text**, mirroring the original app's
  behavior. For anything beyond a demo, hash them with
  `werkzeug.security.generate_password_hash`.
- `app.secret_key` is a placeholder — set a real random secret (e.g. via an
  environment variable) before deploying anywhere.
