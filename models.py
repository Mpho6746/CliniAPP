"""
Data models for CliniApp.

Backed by SQLite via Flask-SQLAlchemy, so registered patients, doctors,
and nurses persist across restarts of the dev server.
"""

import random
from datetime import datetime, date, timedelta

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

APPOINTMENT_SCHEDULED = "scheduled"
APPOINTMENT_COMPLETED = "completed"
APPOINTMENT_CANCELLED = "cancelled"
APPOINTMENT_NO_SHOW = "no_show"
APPOINTMENT_STATUSES = (APPOINTMENT_SCHEDULED, APPOINTMENT_COMPLETED, APPOINTMENT_CANCELLED, APPOINTMENT_NO_SHOW)

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

# A product is flagged "expiring soon" within this many days of its expiry date.
EXPIRY_WARNING_DAYS = 30

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


class MedicationTrainingExample(db.Model):
    """Admin-fed training data for the medication-suggestion model: a
    doctor-note-style text paired with the medication/plan label it implies."""
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(150), nullable=False)
    text = db.Column(db.Text, nullable=False)
    added_by = db.Column(db.String(6), default="")
    added_at = db.Column(db.DateTime, default=datetime.now)


class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.String(13), db.ForeignKey("patient.id_number"), nullable=False)
    patient = db.relationship("Patient", backref=db.backref("appointments", lazy="dynamic"))
    doctor_username = db.Column(db.String(6), db.ForeignKey("doctor.username"), nullable=True)
    doctor = db.relationship("Doctor")
    scheduled_at = db.Column(db.DateTime, nullable=False)
    reason = db.Column(db.String(200), default="")
    status = db.Column(db.String(20), default=APPOINTMENT_SCHEDULED)
    notes = db.Column(db.Text, default="")
    created_by = db.Column(db.String(6), default="")  # admin username who scheduled it
    created_at = db.Column(db.DateTime, default=datetime.now)


class Product(db.Model):
    """A physical stock item — medical supplies, equipment, or drug stock on
    hand. Separate from Medication, which is the prescribing catalog."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), default="")  # e.g. "Medication", "Supply", "Equipment"
    quantity = db.Column(db.Integer, default=0)
    unit = db.Column(db.String(30), default="")  # e.g. "boxes", "units", "bottles"
    reorder_level = db.Column(db.Integer, default=0)  # flagged low-stock at or below this
    expiry_date = db.Column(db.Date, nullable=True)
    added_by = db.Column(db.String(6), default="")
    updated_at = db.Column(db.DateTime, default=datetime.now)


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
    is_active = db.Column(db.Boolean, default=True)


class Nurse(db.Model):
    username = db.Column(db.String(6), primary_key=True)
    pin = db.Column(db.String(4), nullable=False)
    full_name = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=True)


class Pharmacist(db.Model):
    username = db.Column(db.String(6), primary_key=True)
    pin = db.Column(db.String(4), nullable=False)
    full_name = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=True)


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


class ClinicSettings(db.Model):
    """Singleton row of clinic-wide, admin-configurable settings."""
    id = db.Column(db.Integer, primary_key=True)

    # Clinic > General / Contact
    clinic_name = db.Column(db.String(150), default="CliniApp")
    clinic_phone = db.Column(db.String(30), default="")
    clinic_address = db.Column(db.String(300), default="")

    # System > Security
    session_timeout_minutes = db.Column(db.Integer, default=30)
    login_lockout_threshold = db.Column(db.Integer, default=5)  # failed attempts before lockout
    login_lockout_window_minutes = db.Column(db.Integer, default=15)  # lockout window

    # Clinical > Vital Signs thresholds
    temp_low = db.Column(db.Float, default=VITAL_TEMP_LOW)
    temp_high = db.Column(db.Float, default=VITAL_TEMP_HIGH)
    pulse_low = db.Column(db.Integer, default=VITAL_PULSE_LOW)
    pulse_high = db.Column(db.Integer, default=VITAL_PULSE_HIGH)
    bp_systolic_low = db.Column(db.Integer, default=VITAL_BP_SYSTOLIC_LOW)
    bp_systolic_high = db.Column(db.Integer, default=VITAL_BP_SYSTOLIC_HIGH)
    bp_diastolic_low = db.Column(db.Integer, default=VITAL_BP_DIASTOLIC_LOW)
    bp_diastolic_high = db.Column(db.Integer, default=VITAL_BP_DIASTOLIC_HIGH)


def find_file(id_number: str) -> PatientFile | None:
    return db.session.get(PatientFile, id_number)


def find_admin(username: str) -> Admin | None:
    return db.session.get(Admin, username)


def find_staff_by_employee_number(employee_number: str):
    """Look up an employee number across every staff role and return
    (role, staff_object), or (None, None) if it doesn't belong to anyone."""
    for role, model_cls in STAFF_MODELS.items():
        staff = db.session.get(model_cls, employee_number)
        if staff is not None:
            return role, staff
    return None, None


def generate_employee_number() -> str:
    """A random 6-digit employee number guaranteed unique across every
    staff role (and admin, to avoid any cross-login-page confusion)."""
    while True:
        candidate = f"{random.randint(0, 999999):06d}"
        _, staff = find_staff_by_employee_number(candidate)
        if staff is None and find_admin(candidate) is None:
            return candidate


def log_action(role: str, username: str, action: str, details: str = "") -> None:
    db.session.add(AuditLog(role=role, username=username, action=action, details=details))
    db.session.commit()


def recent_audit_log(limit: int = 100) -> list[AuditLog]:
    return AuditLog.query.order_by(AuditLog.created_at.desc()).limit(limit).all()


def find_doctor(username: str) -> Doctor | None:
    return db.session.get(Doctor, username)


def find_nurse(username: str) -> Nurse | None:
    return db.session.get(Nurse, username)


def find_pharmacist(username: str) -> Pharmacist | None:
    return db.session.get(Pharmacist, username)


def all_files() -> list[PatientFile]:
    return PatientFile.query.order_by(PatientFile.registered_at).all()


def all_doctors() -> list[Doctor]:
    return Doctor.query.all()


def all_nurses() -> list[Nurse]:
    return Nurse.query.all()


def all_pharmacists() -> list[Pharmacist]:
    return Pharmacist.query.all()


def active_doctors() -> list[Doctor]:
    return Doctor.query.filter_by(is_active=True).all()


def active_nurses() -> list[Nurse]:
    return Nurse.query.filter_by(is_active=True).all()


def active_pharmacists() -> list[Pharmacist]:
    return Pharmacist.query.filter_by(is_active=True).all()


STAFF_MODELS = {"doctor": Doctor, "nurse": Nurse, "pharmacist": Pharmacist}


def create_staff(role: str, username: str, pin: str, full_name: str):
    model_cls = STAFF_MODELS[role]
    staff = model_cls(username=username, pin=pin, full_name=full_name)
    db.session.add(staff)
    db.session.commit()
    return staff


def update_staff(role: str, username: str, full_name: str | None = None, new_pin: str | None = None):
    model_cls = STAFF_MODELS[role]
    staff = db.session.get(model_cls, username)
    if staff is None:
        return None
    if full_name:
        staff.full_name = full_name
    if new_pin:
        staff.pin = new_pin
    db.session.commit()
    return staff


def set_staff_active(role: str, username: str, active: bool):
    model_cls = STAFF_MODELS[role]
    staff = db.session.get(model_cls, username)
    if staff is not None:
        staff.is_active = active
        db.session.commit()
    return staff


def recent_failed_logins(role: str, username: str, window_minutes: int) -> int:
    cutoff = datetime.now() - timedelta(minutes=window_minutes)
    return (
        AuditLog.query
        .filter(
            AuditLog.role == role, AuditLog.username == username,
            AuditLog.action == "login_failed", AuditLog.created_at >= cutoff,
        )
        .count()
    )


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


def get_clinic_settings() -> ClinicSettings:
    """The single clinic-settings row, created with defaults on first access."""
    settings = ClinicSettings.query.first()
    if settings is None:
        settings = ClinicSettings()
        db.session.add(settings)
        db.session.commit()
    return settings


def evaluate_vitals(temperature: str, bp_systolic: int | None, bp_diastolic: int | None, pulse: str) -> list[str]:
    """Return a list of human-readable abnormal-value flags for a set of vitals,
    checked against the clinic's admin-configurable thresholds."""
    s = get_clinic_settings()
    flags = []

    try:
        temp = float(temperature)
        if temp >= s.temp_high:
            flags.append("High temperature")
        elif temp <= s.temp_low:
            flags.append("Low temperature")
    except (TypeError, ValueError):
        pass

    try:
        pulse_value = float(pulse)
        if pulse_value >= s.pulse_high:
            flags.append("High pulse")
        elif pulse_value <= s.pulse_low:
            flags.append("Low pulse")
    except (TypeError, ValueError):
        pass

    if bp_systolic is not None and bp_diastolic is not None:
        if bp_systolic >= s.bp_systolic_high or bp_diastolic >= s.bp_diastolic_high:
            flags.append("High blood pressure")
        elif bp_systolic <= s.bp_systolic_low or bp_diastolic <= s.bp_diastolic_low:
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


def migrate_schema() -> None:
    """Add columns introduced after a table already existed on disk.

    db.create_all() only creates missing tables — it never alters an
    existing one — so a database created before a model gained new columns
    would otherwise error on every query that touches them. This adds any
    missing columns in place, preserving existing rows and data. New tables
    (e.g. a brand-new model) don't need an entry here — create_all() already
    handles those; this is only for columns added to a table that already
    exists somewhere out there.
    """
    inspector = db.inspect(db.engine)
    table_names = set(inspector.get_table_names())

    def add_missing_columns(table: str, columns: dict[str, str]) -> None:
        if table not in table_names:
            return
        existing = {col["name"] for col in inspector.get_columns(table)}
        for name, ddl_type in columns.items():
            if name not in existing:
                db.session.execute(db.text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))

    add_missing_columns("clinic_settings", {
        "clinic_name": "VARCHAR(150) DEFAULT 'CliniApp'",
        "clinic_phone": "VARCHAR(30) DEFAULT ''",
        "clinic_address": "VARCHAR(300) DEFAULT ''",
        "session_timeout_minutes": "INTEGER DEFAULT 30",
        "login_lockout_threshold": "INTEGER DEFAULT 5",
        "login_lockout_window_minutes": "INTEGER DEFAULT 15",
    })
    add_missing_columns("doctor", {"is_active": "BOOLEAN DEFAULT 1"})
    add_missing_columns("nurse", {"is_active": "BOOLEAN DEFAULT 1"})

    db.session.commit()


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


def all_training_examples() -> list[MedicationTrainingExample]:
    return MedicationTrainingExample.query.order_by(MedicationTrainingExample.added_at.desc()).all()


def training_examples_as_tuples() -> list[tuple[str, str]]:
    return [(e.label, e.text) for e in MedicationTrainingExample.query.all()]


def add_training_example(label: str, text: str, added_by: str) -> MedicationTrainingExample:
    example = MedicationTrainingExample(label=label, text=text, added_by=added_by)
    db.session.add(example)
    db.session.commit()
    return example


def delete_training_example(example_id: int) -> None:
    example = db.session.get(MedicationTrainingExample, example_id)
    if example is not None:
        db.session.delete(example)
        db.session.commit()


def all_products() -> list[Product]:
    return Product.query.order_by(Product.name).all()


def find_product(product_id: int) -> Product | None:
    return db.session.get(Product, product_id)


def low_stock_products() -> list[Product]:
    return [p for p in Product.query.all() if p.quantity <= p.reorder_level]


def expiring_soon_products(days: int = EXPIRY_WARNING_DAYS) -> list[Product]:
    cutoff = date.today() + timedelta(days=days)
    return [
        p for p in Product.query.filter(Product.expiry_date.isnot(None)).all()
        if p.expiry_date <= cutoff
    ]


def adjust_product_stock(product_id: int, change: int) -> Product | None:
    product = find_product(product_id)
    if product is None:
        return None
    product.quantity = max(0, product.quantity + change)
    product.updated_at = datetime.now()
    db.session.commit()
    return product


def delete_product(product_id: int) -> None:
    product = find_product(product_id)
    if product is not None:
        db.session.delete(product)
        db.session.commit()


def all_appointments() -> list[Appointment]:
    return Appointment.query.order_by(Appointment.scheduled_at).all()


def upcoming_appointments() -> list[Appointment]:
    """Scheduled appointments from now on, soonest first."""
    return (
        Appointment.query
        .filter(Appointment.status == APPOINTMENT_SCHEDULED, Appointment.scheduled_at >= datetime.now())
        .order_by(Appointment.scheduled_at)
        .all()
    )


def todays_appointments() -> list[Appointment]:
    today = date.today()
    start = datetime.combine(today, datetime.min.time())
    end = datetime.combine(today, datetime.max.time())
    return (
        Appointment.query
        .filter(Appointment.scheduled_at >= start, Appointment.scheduled_at <= end)
        .order_by(Appointment.scheduled_at)
        .all()
    )


def find_appointment(appointment_id: int) -> Appointment | None:
    return db.session.get(Appointment, appointment_id)


def set_appointment_status(appointment_id: int, status: str) -> Appointment | None:
    appointment = find_appointment(appointment_id)
    if appointment is not None:
        appointment.status = status
        db.session.commit()
    return appointment


def appointments_on(day: date) -> list[Appointment]:
    start = datetime.combine(day, datetime.min.time())
    end = datetime.combine(day, datetime.max.time())
    return (
        Appointment.query
        .filter(Appointment.scheduled_at >= start, Appointment.scheduled_at <= end)
        .order_by(Appointment.scheduled_at)
        .all()
    )


def appointment_counts_for_month(year: int, month: int) -> dict[date, int]:
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    counts: dict[date, int] = {}
    for a in Appointment.query.filter(Appointment.scheduled_at >= start, Appointment.scheduled_at < end).all():
        d = a.scheduled_at.date()
        counts[d] = counts.get(d, 0) + 1
    return counts


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
