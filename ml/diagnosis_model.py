"""
Symptom -> possible-diagnosis suggestion model.

This is a small, self-contained text classifier: TF-IDF features over a
free-text symptom description, feeding a multinomial Logistic Regression
over a fixed list of common outpatient presentations.

IMPORTANT — read before relying on this anywhere real:
This is trained on a few dozen hand-written example sentences per label,
not on real clinical data, and has not been validated in any way. It is a
decision-support hint for a clinician to consider, never a diagnosis, and
it must never be shown to or used by anyone without medical training. See
DISCLAIMER below, which the UI displays next to every suggestion.
"""

from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

DISCLAIMER = (
    "AI-generated suggestions based on the text entered, meant to support a "
    "clinician's own judgment. Not a diagnosis. Always confirm independently."
)

# -------------------- Training data --------------------
# label -> a handful of differently-phrased symptom descriptions.
# Keeping several varied phrasings per label helps the TF-IDF vectorizer
# generalize a little beyond exact wording.

TRAINING_DATA = {
    "Common cold": [
        "runny nose, sneezing, mild sore throat, low grade fever, cough for two days",
        "stuffy nose and sneezing with a scratchy throat, no high fever",
        "mild cough, congestion, and a sore throat that started gradually",
        "runny nose, watery eyes, sneezing, feeling a bit run down",
        "sore throat",
        "blocked nose and sneezing for a couple of days, otherwise well",
        "mild cold symptoms, sniffles and a scratchy throat, no fever",
    ],
    "Influenza": [
        "high fever, body aches, chills, fatigue, dry cough, headache",
        "sudden onset fever with muscle aches and extreme tiredness",
        "fever over 38.5, chills, sore throat, dry cough, exhaustion",
        "body aches, headache, fever, and chills that came on quickly",
        "fever",
        "hit suddenly with fever, chills, and whole-body aches, feels exhausted",
        "high temperature, muscle pain, and fatigue that came on overnight",
    ],
    "Migraine": [
        "throbbing one-sided headache, nausea, sensitivity to light and sound",
        "severe pulsing headache on one side with nausea and light sensitivity",
        "recurring headache with visual aura, nausea, worse with movement",
        "one sided pounding headache, wants to lie in a dark quiet room",
        "headache",
        "bad headache, only on one side, light hurts the eyes, feels nauseous",
        "pounding headache with an aura beforehand, nausea, needs a dark room",
    ],
    "Tension headache": [
        "dull pressure headache on both sides, neck tightness, feels stressed",
        "band-like tight headache across the forehead, mild, no nausea",
        "constant dull ache in the head and neck, worse after a stressful day",
        "mild to moderate headache on both sides with shoulder muscle tension",
        "mild headache and tight neck and shoulders after a stressful week",
        "dull, pressing headache all over, no nausea, no light sensitivity",
    ],
    "Gastroenteritis": [
        "nausea, vomiting, watery diarrhea, stomach cramps",
        "vomiting and frequent watery diarrhea since last night, cramping",
        "stomach cramps with several episodes of diarrhea and nausea",
        "nausea, loose stools, mild fever, abdominal cramping after a meal out",
        "stomach bug, vomiting and diarrhea since yesterday, mild cramping",
        "diarrhea and nausea, no appetite, started after eating out",
    ],
    "Urinary tract infection": [
        "burning sensation when urinating, frequent urination, lower abdominal pain",
        "pain and burning while passing urine, urgency, cloudy urine",
        "frequent trips to the bathroom, burning on urination, pelvic discomfort",
        "lower abdominal pain with painful, frequent urination",
        "burning when urinating",
        "urgency and burning on urination for two days, cloudy smelly urine",
    ],
    "Allergic reaction": [
        "skin rash, itching, hives, swelling after eating shellfish",
        "sudden hives and itching after taking a new medication",
        "itchy raised welts on the skin and mild lip swelling after a meal",
        "widespread itchy rash that started shortly after exposure to pollen",
        "hives all over the body and itching, started soon after a meal",
        "itchy skin welts and swollen lips after eating something new",
    ],
    "Asthma exacerbation": [
        "shortness of breath, wheezing, chest tightness, worse with exercise",
        "wheezing and difficulty breathing, chest feels tight, known asthma",
        "breathlessness with audible wheeze, worse at night and with cold air",
        "chest tightness and wheeze after exertion, using rescue inhaler more often",
        "wheezing",
        "known asthmatic, more short of breath than usual with audible wheeze",
    ],
    "Hypertensive symptoms": [
        "headache, dizziness, blurred vision, high blood pressure reading",
        "throbbing headache with dizziness, blood pressure reading elevated",
        "occasional dizziness and headaches, history of high blood pressure",
        "blurred vision and headache, found to have an elevated blood pressure reading",
        "dizziness",
        "feels lightheaded with a headache, blood pressure reads high today",
    ],
    "Anxiety / panic episode": [
        "rapid heartbeat, sweating, chest tightness, feeling of impending doom",
        "sudden racing heart, shortness of breath, and a sense of panic",
        "episodes of intense fear with sweating, trembling, and rapid pulse",
        "chest tightness and hyperventilation triggered by stress, no cardiac history",
        "feels anxious with a racing heart and trembling hands, no chest pain",
        "sudden panic with sweating and shortness of breath, resolves within minutes",
    ],
    "Musculoskeletal back pain": [
        "lower back pain after lifting, muscle stiffness, pain worse with movement",
        "sharp lower back pain that started after bending to pick something up",
        "stiff, achy lower back, worse in the morning, better with gentle movement",
        "muscle spasm in the lower back after a long day of physical work",
        "back pain",
        "lower back pain",
        "pulled a muscle in the lower back, sore and stiff, no radiation to legs",
    ],
    "Conjunctivitis": [
        "red itchy eyes, discharge, watering eyes",
        "eyes are red and gritty with a sticky discharge in the mornings",
        "itchy watery eyes with mild redness, no vision change",
        "pink, irritated eyes with crusting and tearing",
        "red eye",
        "one eye red and watery with yellow discharge, eyelids stuck together in the morning",
    ],
    "Sinusitis": [
        "facial pressure, nasal congestion, thick nasal discharge, headache",
        "pressure and pain around the cheeks and forehead, thick green mucus",
        "blocked nose with facial tenderness and headache lasting over a week",
        "nasal congestion, post-nasal drip, and facial pressure that worsens leaning forward",
        "facial pain and pressure with thick green nasal discharge for over a week",
    ],
    "Dermatitis": [
        "itchy red rash, dry flaky skin, patches on the elbows",
        "dry itchy patches of skin behind the knees and elbows",
        "red inflamed rash that itches, worse after using a new soap",
        "flaky, itchy skin patches that flare up periodically",
        "itchy rash",
        "dry, itchy, flaky patches that come and go, worse in winter",
    ],
    "Pneumonia": [
        "productive cough with green sputum, fever, chest pain when breathing, shortness of breath",
        "cough bringing up thick yellow-green phlegm with fever and chest pain",
        "fever, cough, and breathlessness with sharp pain on deep breaths",
        "persistent productive cough, fever, and fatigue lasting over a week",
        "cough",
        "fever and productive cough for a week, short of breath, pain on deep breathing",
    ],
    "Gastroesophageal reflux": [
        "burning chest pain after meals, acid reflux, sour taste in mouth",
        "heartburn and a sour taste that worsens after eating and lying down",
        "burning sensation behind the breastbone after large meals",
        "regurgitation and chest burning, worse at night when lying flat",
        "heartburn most nights after dinner, sour taste, no shortness of breath",
    ],
    "Possible cardiac event": [
        "severe chest pain radiating to the left arm, shortness of breath, sweating",
        "crushing central chest pain with shortness of breath and cold sweat",
        "chest tightness and pain spreading to the jaw and left arm, nausea",
        "sudden chest pressure with breathlessness, sweating, and lightheadedness",
        "chest pain radiating to the back and left shoulder, breathless and sweaty",
        "tight crushing chest pain at rest, shortness of breath, feels faint",
        "chest pain, radiates to arm",
    ],
    "Appendicitis": [
        "pain starting around the belly button moving to the lower right abdomen, nausea, low fever",
        "sharp lower right abdominal pain, worse with movement, loss of appetite",
        "abdominal pain migrating to the right side, tenderness, mild fever, nausea",
        "right-sided abdominal pain that worsens over hours, nausea, low-grade fever",
        "stomach pain",
        "worsening pain in the lower right abdomen, off food, low fever",
    ],
    "Possible pregnancy": [
        "missed period, nausea, breast tenderness",
        "missed period and morning sickness",
        "no period for two months, feeling nauseous and tired",
        "late period, sore breasts, feeling more tired than usual",
        "missed period",
        "period is late, nauseous most mornings, breasts feel tender and swollen",
        "no period this month, mild nausea, fatigue, food aversions",
    ],
}


@dataclass
class Suggestion:
    diagnosis: str
    confidence: float  # 0-100


def _build_model() -> Pipeline:
    texts, labels = [], []
    for label, examples in TRAINING_DATA.items():
        for example in examples:
            texts.append(example)
            labels.append(label)

    features = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), stop_words="english", min_df=1, sublinear_tf=True)),
        # Character n-grams catch word variants the word-level vectorizer misses
        # (e.g. "tired" vs. "tiredness") despite the tiny training vocabulary.
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True)),
    ])
    pipeline = Pipeline([
        ("features", features),
        ("clf", LogisticRegression(max_iter=3000, C=3)),
    ])
    pipeline.fit(texts, labels)
    return pipeline


# Trained once when the module is first imported (dataset is tiny, fits in
# well under a second) and reused for every prediction after that.
_model = _build_model()


def predict_diagnoses(symptom_text: str, top_n: int = 3) -> list[Suggestion]:
    """Return the top_n most likely diagnosis labels for a symptom description,
    each with a 0-100 confidence score. Returns [] for empty/blank input."""
    text = (symptom_text or "").strip()
    if not text:
        return []

    probabilities = _model.predict_proba([text])[0]
    labels = _model.classes_

    ranked = sorted(zip(labels, probabilities), key=lambda pair: pair[1], reverse=True)
    top = ranked[:top_n]
    return [Suggestion(diagnosis=label, confidence=round(prob * 100, 1)) for label, prob in top]
