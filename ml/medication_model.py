"""
Diagnosis/doctor-notes -> possible-medication suggestion model.

Same approach as diagnosis_model.py: a small, self-contained TF-IDF +
Logistic Regression classifier, trained on a handful of hand-written
doctor-note-style examples per medication label.

IMPORTANT — read before relying on this anywhere real:
This is trained on a few dozen hand-written examples, not on real clinical
or pharmacological data, and has not been validated in any way. It is a
decision-support hint for a pharmacist to consider alongside the doctor's
own order, never a prescription, and it must never be used to dispense
without independent clinical judgment. See DISCLAIMER below, which the UI
displays next to every suggestion.
"""

from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

DISCLAIMER = (
    "AI-generated suggestions based on the doctor's notes, meant to support a "
    "pharmacist's own judgment. Not a prescription. Always dispense according "
    "to the doctor's actual order."
)

# -------------------- Training data --------------------
# medication/plan label -> a handful of differently-phrased doctor-note
# style diagnosis summaries that would typically warrant it.

TRAINING_DATA = {
    "Paracetamol (supportive care)": [
        "diagnosed with common cold, supportive care advised",
        "viral upper respiratory infection, rest and fluids, symptomatic relief",
        "mild viral illness, advised rest and paracetamol for fever",
        "common cold, no antibiotics needed, symptomatic treatment",
        "low grade viral infection, supportive care only",
    ],
    "Paracetamol + rest (influenza)": [
        "influenza confirmed, rest, fluids, and paracetamol for fever and aches",
        "flu-like illness, supportive treatment with antipyretics",
        "diagnosed with influenza, advised bed rest and paracetamol",
        "seasonal flu, symptomatic management, review if worsens",
    ],
    "Ibuprofen or triptan (migraine)": [
        "migraine diagnosed, recommend analgesia and a dark quiet room",
        "classic migraine with aura, advised anti-inflammatory and rest",
        "recurrent one-sided headache consistent with migraine, pain relief prescribed",
        "migraine, trial ibuprofen, consider triptan if recurrent",
    ],
    "Paracetamol or ibuprofen (tension headache)": [
        "tension-type headache, advised simple analgesia and stress reduction",
        "muscle tension headache, mild, analgesia and relaxation advised",
        "stress-related headache, recommend paracetamol and rest",
    ],
    "Oral rehydration salts + antiemetic": [
        "gastroenteritis, advised oral rehydration and antiemetic",
        "viral gastroenteritis, rehydration therapy, review if not improving",
        "vomiting and diarrhea, likely viral, supportive fluids and antiemetic",
        "stomach bug, rehydration salts prescribed, bland diet advised",
    ],
    "Antibiotic course — UTI (e.g. nitrofurantoin)": [
        "urinary tract infection confirmed, antibiotic course prescribed",
        "uncomplicated UTI, started on a short antibiotic course",
        "cystitis symptoms, antibiotics prescribed, encourage fluids",
    ],
    "Antihistamine (allergic reaction)": [
        "allergic reaction, antihistamine prescribed, avoid known trigger",
        "hives and itching, likely allergic, antihistamine advised",
        "mild allergic reaction, oral antihistamine, monitor for worsening",
        "urticaria after food exposure, antihistamine given, advised follow-up",
    ],
    "Salbutamol inhaler (asthma)": [
        "asthma exacerbation, reliever inhaler prescribed",
        "wheeze and breathlessness, known asthmatic, salbutamol advised",
        "mild asthma flare, increase reliever inhaler use, review in days",
    ],
    "Antihypertensive — refer for BP work-up": [
        "elevated blood pressure noted, started on antihypertensive, referred for work-up",
        "hypertensive symptoms, blood pressure medication initiated, follow-up advised",
        "high blood pressure reading, antihypertensive prescribed, advised monitoring",
    ],
    "Short-term anxiolytic / counselling referral": [
        "anxiety / panic episode, advised short-term anxiolytic and counselling referral",
        "panic attack, no cardiac cause found, referred for counselling",
        "acute anxiety episode, reassurance given, referral for ongoing support",
    ],
    "NSAID + rest (musculoskeletal)": [
        "musculoskeletal back pain, advised NSAID and rest",
        "muscle strain, anti-inflammatory prescribed, advised gentle movement",
        "lower back pain after lifting, NSAID and physiotherapy advised",
    ],
    "Antibiotic eye drops (conjunctivitis)": [
        "bacterial conjunctivitis suspected, antibiotic eye drops prescribed",
        "red itchy eye with discharge, antibiotic drops given",
        "conjunctivitis diagnosed, advised hygiene and antibiotic eye drops",
    ],
    "Decongestant + analgesic (sinusitis)": [
        "sinusitis diagnosed, decongestant and analgesic advised",
        "facial pressure and nasal congestion, sinusitis, symptomatic treatment",
        "sinus infection, decongestant prescribed, antibiotics if not improving",
    ],
    "Topical corticosteroid + emollient (dermatitis)": [
        "dermatitis diagnosed, topical steroid cream and emollient prescribed",
        "itchy eczema patches, topical corticosteroid advised",
        "skin rash consistent with dermatitis, emollient and steroid cream given",
    ],
    "Oral antibiotic — refer if severe (pneumonia)": [
        "pneumonia diagnosed, oral antibiotic course started, review in days",
        "chest infection, antibiotics prescribed, advised to return if worsening",
        "community acquired pneumonia, antibiotic course, monitor breathing",
    ],
    "Antacid / PPI (reflux)": [
        "gastroesophageal reflux diagnosed, PPI prescribed, advised dietary changes",
        "heartburn consistent with reflux, antacid and lifestyle advice given",
        "GERD symptoms, proton pump inhibitor started",
    ],
    "URGENT — do not dispense, refer immediately": [
        "possible cardiac event, referred immediately, do not dispense, emergency transfer",
        "suspected acute coronary syndrome, urgent referral, no medication dispensed here",
        "appendicitis suspected, urgent surgical referral, do not dispense",
        "acute abdomen, likely appendicitis, referred for emergency surgical assessment",
        "chest pain radiating to arm, possible cardiac event, urgent transfer to hospital",
        "suspected heart attack, chest pain and shortness of breath, sent to ER immediately",
    ],
    "Refer for antenatal care + folic acid": [
        "possible pregnancy, referred for antenatal care, folic acid advised",
        "missed period with positive signs of pregnancy, referred to antenatal clinic",
        "suspected pregnancy, advised folic acid supplementation and antenatal follow-up",
    ],
}


@dataclass
class MedicationSuggestion:
    medication: str
    confidence: float  # 0-100


def _build_model(extra_examples: list[tuple[str, str]] | None = None) -> Pipeline:
    """Train the pipeline on the hand-written TRAINING_DATA plus any
    admin-fed (label, text) examples pulled from the database."""
    texts, labels = [], []
    for label, examples in TRAINING_DATA.items():
        for example in examples:
            texts.append(example)
            labels.append(label)

    for label, text in extra_examples or []:
        texts.append(text)
        labels.append(label)

    features = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), stop_words="english", min_df=1, sublinear_tf=True)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True)),
    ])
    pipeline = Pipeline([
        ("features", features),
        ("clf", LogisticRegression(max_iter=3000, C=3)),
    ])
    pipeline.fit(texts, labels)
    return pipeline


# Trained once when the module is first imported (dataset is tiny, fits in
# well under a second) and reused for every prediction after that. Call
# retrain() whenever admin-fed training examples change.
_model = _build_model()


def retrain(extra_examples: list[tuple[str, str]] | None = None) -> None:
    global _model
    _model = _build_model(extra_examples)


def predict_medications(notes_text: str, top_n: int = 3) -> list[MedicationSuggestion]:
    """Return the top_n most likely medication/plan labels for a doctor's
    notes, each with a 0-100 confidence score. Returns [] for empty input."""
    text = (notes_text or "").strip()
    if not text:
        return []

    probabilities = _model.predict_proba([text])[0]
    labels = _model.classes_

    ranked = sorted(zip(labels, probabilities), key=lambda pair: pair[1], reverse=True)
    top = ranked[:top_n]
    return [MedicationSuggestion(medication=label, confidence=round(prob * 100, 1)) for label, prob in top]
