"""
Data models for MediCare Clinic.

Backed by SQLite via Flask-SQLAlchemy, so registered patients, doctors,
and nurses persist across restarts of the dev server.
"""

from datetime import datetime, date

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

STATUS_REGISTERED = "registered"
STATUS_EVALUATED = "evaluated"
STATUS_DISPENSED = "dispensed"
STATUSES = (STATUS_REGISTERED, STATUS_EVALUATED, STATUS_DISPENSED)

PRIORITY_NORMAL = "normal"
PRIORITY_URGENT = "urgent"
PRIORITIES = (PRIORITY_NORMAL, PRIORITY_URGENT)

# Routine nursing tasks tracked once per patient per day.
ROUTINE_TASKS = [
    ("vitals", "Check vitals (q4h)"),
    ("meds", "Administer medication"),
    ("iv", "Check IV site"),
]

# Categories a patient can pick from their call-button page.
REQUEST_CATEGORIES = [
    ("pain", "In pain"),
    ("water", "Need water"),
    ("bathroom", "Bathroom help"),
]

REQUEST_STATUS_OPEN = "open"
REQUEST_STATUS_DONE = "done"

# Abnormal-value thresholds for adult vitals (simple, widely-used ranges —
# a decision-support flag for nursing, not a clinical calculator).
VITAL_TEMP_LOW = 35.0
VITAL_TEMP_HIGH = 38.0
VITAL_PULSE_LOW = 60
VITAL_PULSE_HIGH = 100
VITAL_BP_SYSTOLIC_LOW = 90
VITAL_BP_SYSTOLIC_HIGH = 140
VITAL_BP_DIASTOLIC_LOW = 60
VITAL_BP_DIASTOLIC_HIGH = 90

# Starter drug catalog — seeded once if the Medication table is empty.
STARTER_MEDICATIONS = [
    ("Paracetamol", "500mg", "Tablet", "Analgesic / antipyretic"),
    ("Ibuprofen", "400mg", "Tablet", "NSAID"),
    ("Amoxicillin", "500mg", "Capsule", "Antibiotic"),
    ("Nitrofurantoin", "100mg", "Capsule", "Antibiotic (UTI)"),
    ("Cetirizine", "10mg", "Tablet", "Antihistamine"),
    ("Salbutamol", "100mcg", "Inhaler", "Bronchodilator"),
    ("Amlodipine", "5mg", "Tablet", "Antihypertensive"),
    ("Omeprazole", "20mg", "Capsule", "PPI"),
    ("Metoclopramide", "10mg", "Tablet", "Antiemetic"),
    ("Oral rehydration salts", "1 sachet", "Sachet", "Rehydration"),
    ("Chloramphenicol", "1%", "Eye drops", "Antibiotic (eye)"),
    ("Hydrocortisone cream", "1%", "Cream", "Topical corticosteroid"),
    ("Folic acid", "5mg", "Tablet", "Supplement"),
    ("Diclofenac", "50mg", "Tablet", "NSAID"),
    ("Loratadine", "10mg", "Tablet", "Antihistamine"),
]


class Patient(db.Model):
    id_number = db.Column(db.String(13), primary_key=True)
    full_name = db.Column(db.String(200), nullable=False)
    age = db.Column(db.String(10), default="")
    gender = db.Column(db.String(20), default="")
    phone = db.Column(db.String(30), default="")
    street = db.Column(db.String(200), default="")
    city = db.Column(db.String(100), default="")
    province = db.Column(db.String(100), default="")
    postal_code = db.Column(db.String(20), default="")


class PatientFile(db.Model):
    patient_id = db.Column(db.String(13), db.ForeignKey("patient.id_number"), primary_key=True)
    patient = db.relationship("Patient", backref=db.backref("file", uselist=False))

    status = db.Column(db.String(20), default=STATUS_REGISTERED)
    doctor_notes = db.Column(db.Text, default="")
    pharmacist_notes = db.Column(db.Text, default="")
    priority = db.Column(db.String(20), default=PRIORITY_NORMAL)
    symptoms = db.Column(db.Text, default="")  # free-text symptoms, used as input to the diagnosis-suggestion model
    registered_at = db.Column(db.DateTime, default=datetime.now)
    evaluated_by = db.Column(db.String(6), default="")  # doctor username who last evaluated this file

    # Vitals, recorded by nursing before the doctor sees the patient
    temperature = db.Column(db.String(10), default="")     # in °C, e.g. "37.2"
    blood_pressure = db.Column(db.String(20), default="")  # e.g. "120/80"
    pulse = db.Column(db.String(10), default="")           # beats per minute
    vitals_recorded_at = db.Column(db.DateTime, nullable=True)
    vitals_recorded_by = db.Column(db.String(6), default="")  # nurse username who last recorded vitals


class VitalsReading(db.Model):
    """One historical vitals recording, kept alongside PatientFile's
    'current' vitals fields so trends over time can be charted and flagged."""
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.String(13), db.ForeignKey("patient.id_number"), nullable=False)
    patient = db.relationship("Patient", backref=db.backref("vitals_readings", lazy="dynamic"))
    temperature = db.Column(db.String(10), default="")
    blood_pressure = db.Column(db.String(20), default="")
    bp_systolic = db.Column(db.Integer, nullable=True)
    bp_diastolic = db.Column(db.Integer, nullable=True)
    pulse = db.Column(db.String(10), default="")
    flags = db.Column(db.String(200), default="")  # comma-separated abnormal-value flags, "" if normal
    recorded_at = db.Column(db.DateTime, default=datetime.now)
    recorded_by = db.Column(db.String(6), default="")  # nurse username


class HandoverNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.String(13), db.ForeignKey("patient.id_number"), nullable=False)
    patient = db.relationship("Patient", backref=db.backref("handover_notes", lazy="dynamic"))
    note = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.String(6), default="")  # nurse username who left the note
    created_at = db.Column(db.DateTime, default=datetime.now)


class ChecklistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.String(13), db.ForeignKey("patient.id_number"), nullable=False)
    patient = db.relationship("Patient", backref=db.backref("checklist_items", lazy="dynamic"))
    task_key = db.Column(db.String(20), nullable=False)
    task_date = db.Column(db.Date, default=date.today)
    completed = db.Column(db.Boolean, default=False)
    completed_by = db.Column(db.String(6), default="")  # nurse username who completed it
    completed_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (db.UniqueConstraint("patient_id", "task_key", "task_date", name="uq_checklist_item"),)


class PatientRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.String(13), db.ForeignKey("patient.id_number"), nullable=False)
    patient = db.relationship("Patient", backref=db.backref("requests", lazy="dynamic"))
    category = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(10), default=REQUEST_STATUS_OPEN)
    created_at = db.Column(db.DateTime, default=datetime.now)
    resolved_by = db.Column(db.String(6), default="")  # nurse username who handled it
    resolved_at = db.Column(db.DateTime, nullable=True)


class Medication(db.Model):
    """A drug catalog entry — the 'drug database' doctors prescribe from."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    common_dosage = db.Column(db.String(50), default="")  # e.g. "500mg"
    form = db.Column(db.String(30), default="")  # e.g. "Tablet", "Syrup", "Inhaler"
    category = db.Column(db.String(50), default="")  # e.g. "Analgesic"


class Prescription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.String(13), db.ForeignKey("patient.id_number"), nullable=False)
    patient = db.relationship("Patient", backref=db.backref("prescriptions", lazy="dynamic"))
    medication_id = db.Column(db.Integer, db.ForeignKey("medication.id"), nullable=False)
    medication = db.relationship("Medication")
    dosage = db.Column(db.String(50), default="")
    frequency = db.Column(db.String(50), default="")  # e.g. "Every 8 hours"
    duration = db.Column(db.String(50), default="")  # e.g. "5 days"
    instructions = db.Column(db.Text, default="")
    prescribed_by = db.Column(db.String(6), default="")  # doctor username
    prescribed_at = db.Column(db.DateTime, default=datetime.now)


class MedicationAdministration(db.Model):
    """One recorded dose given — the nursing medication administration record (MAR)."""
    id = db.Column(db.Integer, primary_key=True)
    prescription_id = db.Column(db.Integer, db.ForeignKey("prescription.id"), nullable=False)
    prescription = db.relationship("Prescription", backref=db.backref("administrations", lazy="dynamic"))
    administered_by = db.Column(db.String(6), default="")  # nurse username
    administered_at = db.Column(db.DateTime, default=datetime.now)
    notes = db.Column(db.Text, default="")


class Doctor(db.Model):
    username = db.Column(db.String(6), primary_key=True)
    pin = db.Column(db.String(4), nullable=False)
    full_name = db.Column(db.String(200), nullable=False)


class Nurse(db.Model):
    username = db.Column(db.String(6), primary_key=True)
    pin = db.Column(db.String(4), nullable=False)
    full_name = db.Column(db.String(200), nullable=False)


class Admin(db.Model):
    username = db.Column(db.String(6), primary_key=True)
    pin = db.Column(db.String(4), nullable=False)
    full_name = db.Column(db.String(200), nullable=False)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(10), nullable=False)  # "admin" / "doctor" / "nurse"
    username = db.Column(db.String(6), default="")
    action = db.Column(db.String(50), nullable=False)
    details = db.Column(db.String(300), default="")
    created_at = db.Column(db.DateTime, default=datetime.now)


def find_file(id_number: str) -> PatientFile | None:
    return db.session.get(PatientFile, id_number)


def find_admin(username: str) -> Admin | None:
    return db.session.get(Admin, username)


def log_action(role: str, username: str, action: str, details: str = "") -> None:
    db.session.add(AuditLog(role=role, username=username, action=action, details=details))
    db.session.commit()


def recent_audit_log(limit: int = 100) -> list[AuditLog]:
    return AuditLog.query.order_by(AuditLog.created_at.desc()).limit(limit).all()


def find_doctor(username: str) -> Doctor | None:
    return db.session.get(Doctor, username)


def find_nurse(username: str) -> Nurse | None:
    return db.session.get(Nurse, username)


def all_files() -> list[PatientFile]:
    return PatientFile.query.order_by(PatientFile.registered_at).all()


def all_doctors() -> list[Doctor]:
    return Doctor.query.all()


def active_files() -> list[PatientFile]:
    """Patients still in the clinic (not yet dispensed), for shift handover."""
    return (
        PatientFile.query
        .filter(PatientFile.status != STATUS_DISPENSED)
        .order_by(PatientFile.priority.desc(), PatientFile.registered_at)
        .all()
    )


def recent_handover_notes(patient_id: str, limit: int = 5) -> list[HandoverNote]:
    return (
        HandoverNote.query
        .filter_by(patient_id=patient_id)
        .order_by(HandoverNote.created_at.desc())
        .limit(limit)
        .all()
    )


def latest_handover_note(patient_id: str) -> HandoverNote | None:
    return (
        HandoverNote.query
        .filter_by(patient_id=patient_id)
        .order_by(HandoverNote.created_at.desc())
        .first()
    )


def open_requests() -> list[PatientRequest]:
    return (
        PatientRequest.query
        .filter_by(status=REQUEST_STATUS_OPEN)
        .order_by(PatientRequest.created_at)
        .all()
    )


def _parse_bp(blood_pressure: str) -> tuple[int | None, int | None]:
    try:
        systolic_text, diastolic_text = blood_pressure.split("/")
        return int(systolic_text.strip()), int(diastolic_text.strip())
    except (ValueError, AttributeError):
        return None, None


def evaluate_vitals(temperature: str, bp_systolic: int | None, bp_diastolic: int | None, pulse: str) -> list[str]:
    """Return a list of human-readable abnormal-value flags for a set of vitals."""
    flags = []

    try:
        temp = float(temperature)
        if temp >= VITAL_TEMP_HIGH:
            flags.append("High temperature")
        elif temp <= VITAL_TEMP_LOW:
            flags.append("Low temperature")
    except (TypeError, ValueError):
        pass

    try:
        pulse_value = float(pulse)
        if pulse_value >= VITAL_PULSE_HIGH:
            flags.append("High pulse")
        elif pulse_value <= VITAL_PULSE_LOW:
            flags.append("Low pulse")
    except (TypeError, ValueError):
        pass

    if bp_systolic is not None and bp_diastolic is not None:
        if bp_systolic >= VITAL_BP_SYSTOLIC_HIGH or bp_diastolic >= VITAL_BP_DIASTOLIC_HIGH:
            flags.append("High blood pressure")
        elif bp_systolic <= VITAL_BP_SYSTOLIC_LOW or bp_diastolic <= VITAL_BP_DIASTOLIC_LOW:
            flags.append("Low blood pressure")

    return flags


def record_vitals_reading(patient_id: str, temperature: str, blood_pressure: str, pulse: str, recorded_by: str) -> VitalsReading:
    """Log one historical vitals reading and return it, with abnormal-value flags computed."""
    bp_systolic, bp_diastolic = _parse_bp(blood_pressure)
    flags = evaluate_vitals(temperature, bp_systolic, bp_diastolic, pulse)
    reading = VitalsReading(
        patient_id=patient_id,
        temperature=temperature,
        blood_pressure=blood_pressure,
        bp_systolic=bp_systolic,
        bp_diastolic=bp_diastolic,
        pulse=pulse,
        flags=", ".join(flags),
        recorded_by=recorded_by,
    )
    db.session.add(reading)
    return reading


def vitals_history(patient_id: str, limit: int = 10) -> list[VitalsReading]:
    return (
        VitalsReading.query
        .filter_by(patient_id=patient_id)
        .order_by(VitalsReading.recorded_at.desc())
        .limit(limit)
        .all()
    )


def latest_vitals_flags(patient_id: str) -> list[str]:
    reading = (
        VitalsReading.query
        .filter_by(patient_id=patient_id)
        .order_by(VitalsReading.recorded_at.desc())
        .first()
    )
    if reading is None or not reading.flags:
        return []
    return [f.strip() for f in reading.flags.split(",")]


def seed_medications() -> None:
    """Populate the drug catalog with starter entries, once, if it's empty."""
    if Medication.query.first() is not None:
        return
    for name, dosage, form, category in STARTER_MEDICATIONS:
        db.session.add(Medication(name=name, common_dosage=dosage, form=form, category=category))
    db.session.commit()


def all_medications() -> list[Medication]:
    return Medication.query.order_by(Medication.name).all()


def find_medication(medication_id: int) -> Medication | None:
    return db.session.get(Medication, medication_id)


def prescriptions_for(patient_id: str) -> list[Prescription]:
    return (
        Prescription.query
        .filter_by(patient_id=patient_id)
        .order_by(Prescription.prescribed_at.desc())
        .all()
    )


def recent_administrations(prescription_id: int, limit: int = 5) -> list[MedicationAdministration]:
    return (
        MedicationAdministration.query
        .filter_by(prescription_id=prescription_id)
        .order_by(MedicationAdministration.administered_at.desc())
        .limit(limit)
        .all()
    )


def checklist_for(patient_id: str) -> list[dict]:
    """Today's routine-task checklist for a patient, creating rows on first view."""
    today = date.today()
    existing = {
        item.task_key: item
        for item in ChecklistItem.query.filter_by(patient_id=patient_id, task_date=today).all()
    }
    result = []
    for key, label in ROUTINE_TASKS:
        item = existing.get(key)
        if item is None:
            item = ChecklistItem(patient_id=patient_id, task_key=key, task_date=today)
            db.session.add(item)
        result.append({
            "key": key,
            "label": label,
            "completed": item.completed,
            "completed_by": item.completed_by,
            "completed_at": item.completed_at,
        })
    db.session.commit()
    return result
