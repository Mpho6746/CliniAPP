"""
Data models for CliniApp.

Backed by SQLite via Flask-SQLAlchemy. Starting simple: a single User
model with one role. More roles (doctor/nurse/pharmacist/admin) get
layered on once the basic login is solid.
"""

import calendar
import random
from datetime import date, datetime, timedelta

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hospital_number = db.Column(db.String(50), unique=True, nullable=False)
    hospital_name = db.Column(db.String(200), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


def find_user_by_hospital_number(hospital_number: str) -> User | None:
    return User.query.filter_by(hospital_number=hospital_number).first()


def create_user(hospital_number: str, password: str, hospital_name: str) -> User:
    user = User(hospital_number=hospital_number, hospital_name=hospital_name)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


STAFF_GENDER_OPTIONS = ["Male", "Female", "Other", "Prefer not to say"]
STAFF_SHIFT_OPTIONS = ["Morning", "Afternoon", "Night", "Rotating"]

STAFF_ROLES = ["doctor", "nurse", "pharmacist", "admin", "receptionist", "lab_technician", "other"]
STAFF_LABELS = {
    "doctor": "Doctor",
    "nurse": "Nurse",
    "pharmacist": "Pharmacist",
    "admin": "Admin",
    "receptionist": "Receptionist",
    "lab_technician": "Lab Technician",
    "other": "Other",
}

ACCESS_LEVELS = ["full", "read_only", "clinical", "restricted"]
ACCESS_LEVEL_LABELS = {
    "full": "Full Access",
    "read_only": "Read-only",
    "clinical": "Clinical (patients only)",
    "restricted": "Restricted (custom)",
}
DEFAULT_ACCESS_LEVEL_BY_ROLE = {
    "admin": "full",
    "doctor": "clinical",
    "nurse": "clinical",
    "pharmacist": "clinical",
    "receptionist": "read_only",
    "lab_technician": "clinical",
    "other": "restricted",
}


class Staff(db.Model):
    """A single table for every staff role. `role` determines which pages
    they can reach; `access_level` further restricts what they can do
    within those pages (see has_access())."""

    id = db.Column(db.Integer, primary_key=True)
    employee_number = db.Column(db.String(6), unique=True, nullable=False)
    full_name = db.Column(db.String(200), nullable=False)
    pin_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False)
    access_level = db.Column(db.String(20), nullable=False, default="restricted")
    created_at = db.Column(db.DateTime, default=datetime.now)

    email = db.Column(db.String(200), nullable=False, default="")
    phone_work = db.Column(db.String(20), nullable=False, default="")
    phone_mobile = db.Column(db.String(20), nullable=False, default="")
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(30), nullable=False, default="")
    national_id = db.Column(db.String(50), nullable=False, default="")
    home_address = db.Column(db.String(300), nullable=False, default="")

    specialization = db.Column(db.String(200), nullable=False, default="")
    qualification = db.Column(db.String(200), nullable=False, default="")
    years_of_experience = db.Column(db.Integer, nullable=True)
    license_number = db.Column(db.String(100), nullable=False, default="")
    date_joined = db.Column(db.Date, nullable=True)
    shift_preference = db.Column(db.String(20), nullable=False, default="")
    consultation_fee = db.Column(db.Float, nullable=True)

    def set_pin(self, pin: str) -> None:
        self.pin_hash = generate_password_hash(pin)

    def check_pin(self, pin: str) -> bool:
        return check_password_hash(self.pin_hash, pin)


def has_access(staff: "Staff", module: str, need: str = "view") -> bool:
    """module: 'patients' (patient records + clinical actions + appointments)
    or 'admin_ops' (staff management, settings, reports, ticket admin).
    need: 'view' or 'write'. Role decides which pages exist; this decides
    what a staff member can do within pages their role already reaches."""
    level = staff.access_level
    if level == "full":
        return True
    if level == "read_only":
        return need == "view"
    if level == "clinical":
        return module == "patients"
    return False  # restricted


def find_staff_by_employee_number(employee_number: str):
    """Returns (role, staff_object) or (None, None) if no one has that number."""
    staff = Staff.query.filter_by(employee_number=employee_number).first()
    return (staff.role, staff) if staff else (None, None)


def search_staff(query: str):
    """Search staff by name or employee number. Returns a list of
    (role, staff_object) tuples, newest first."""
    like = f"%{query}%"
    results = Staff.query.filter(
        db.or_(Staff.full_name.ilike(like), Staff.employee_number.ilike(like))
    ).order_by(Staff.created_at.desc()).all()
    return [(s.role, s) for s in results]


def total_staff_count() -> int:
    return Staff.query.count()


def employee_number_taken(employee_number: str) -> bool:
    _, staff = find_staff_by_employee_number(employee_number)
    return staff is not None


def create_staff(
    role: str,
    employee_number: str,
    pin: str,
    full_name: str,
    access_level: str = "restricted",
    email: str = "",
    phone_work: str = "",
    phone_mobile: str = "",
    date_of_birth=None,
    gender: str = "",
    national_id: str = "",
    home_address: str = "",
    specialization: str = "",
    qualification: str = "",
    years_of_experience=None,
    license_number: str = "",
    date_joined=None,
    shift_preference: str = "",
    consultation_fee=None,
):
    staff = Staff(
        employee_number=employee_number,
        full_name=full_name,
        role=role,
        access_level=access_level,
        email=email,
        phone_work=phone_work,
        phone_mobile=phone_mobile,
        date_of_birth=date_of_birth,
        gender=gender,
        national_id=national_id,
        home_address=home_address,
        specialization=specialization,
        qualification=qualification,
        years_of_experience=years_of_experience,
        license_number=license_number,
        date_joined=date_joined or date.today(),
        shift_preference=shift_preference,
        consultation_fee=consultation_fee,
    )
    staff.set_pin(pin)
    db.session.add(staff)
    db.session.commit()
    return staff


PATIENT_STATUSES = ["Active", "Inactive", "Deceased", "Transferred"]


class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_number = db.Column(db.String(6), unique=True, nullable=False)
    full_name = db.Column(db.String(200), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    email = db.Column(db.String(200), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="Active")
    next_appointment = db.Column(db.Date, nullable=True)
    insurance_provider = db.Column(db.String(200), nullable=False, default="")
    insurance_policy_number = db.Column(db.String(100), nullable=False, default="")
    emergency_contact_name = db.Column(db.String(200), nullable=False, default="")
    emergency_contact_phone = db.Column(db.String(20), nullable=False, default="")


def _generate_patient_number() -> str:
    while True:
        candidate = f"{random.randint(0, 999999):06d}"
        if not Patient.query.filter_by(patient_number=candidate).first():
            return candidate


def patient_number_taken(patient_number: str) -> bool:
    return Patient.query.filter_by(patient_number=patient_number).first() is not None


def find_potential_duplicate_patients(full_name: str, date_of_birth, phone_number: str):
    """Existing patients that look like the same person: same name + DOB, or same phone."""
    return Patient.query.filter(
        db.or_(
            db.and_(Patient.full_name.ilike(full_name), Patient.date_of_birth == date_of_birth),
            Patient.phone_number == phone_number,
        )
    ).all()


def create_patient(
    full_name: str,
    date_of_birth,
    gender: str,
    phone_number: str,
    address: str = "",
    email: str = "",
    status: str = "Active",
    next_appointment=None,
    insurance_provider: str = "",
    insurance_policy_number: str = "",
    emergency_contact_name: str = "",
    emergency_contact_phone: str = "",
    patient_number: str | None = None,
) -> Patient:
    patient = Patient(
        patient_number=patient_number or _generate_patient_number(),
        full_name=full_name,
        date_of_birth=date_of_birth,
        gender=gender,
        phone_number=phone_number,
        address=address,
        email=email,
        status=status,
        next_appointment=next_appointment,
        insurance_provider=insurance_provider,
        insurance_policy_number=insurance_policy_number,
        emergency_contact_name=emergency_contact_name,
        emergency_contact_phone=emergency_contact_phone,
    )
    db.session.add(patient)
    db.session.commit()
    return patient


def list_patients(
    query: str = "",
    sort: str = "created_at",
    direction: str = "desc",
    gender: str = "",
    status: str = "",
    min_age=None,
    max_age=None,
    registered_from=None,
    registered_to=None,
    location: str = "",
):
    q = Patient.query
    if query:
        like = f"%{query}%"
        q = q.filter(
            db.or_(
                Patient.full_name.ilike(like),
                Patient.patient_number.ilike(like),
                Patient.phone_number.ilike(like),
            )
        )

    if gender:
        q = q.filter(Patient.gender == gender)
    if status:
        q = q.filter(Patient.status == status)
    if location:
        q = q.filter(Patient.address.ilike(f"%{location}%"))
    if registered_from:
        q = q.filter(Patient.created_at >= datetime.combine(registered_from, datetime.min.time()))
    if registered_to:
        q = q.filter(Patient.created_at <= datetime.combine(registered_to, datetime.max.time()))

    today = date.today()
    if max_age is not None:
        # Someone at most max_age years old was born on or after this date.
        earliest_dob = date(today.year - max_age - 1, today.month, today.day) + timedelta(days=1)
        q = q.filter(Patient.date_of_birth >= earliest_dob)
    if min_age is not None:
        # Someone at least min_age years old was born on or before this date.
        latest_dob = date(today.year - min_age, today.month, today.day)
        q = q.filter(Patient.date_of_birth <= latest_dob)

    sort_columns = {
        "name": Patient.full_name,
        "patient_number": Patient.patient_number,
        "status": Patient.status,
        "next_appointment": Patient.next_appointment,
        "gender": Patient.gender,
        "phone_number": Patient.phone_number,
        "created_at": Patient.created_at,
    }
    column = sort_columns.get(sort, Patient.created_at)
    order = column.desc() if direction == "desc" else column.asc()
    return q.order_by(order).all()


def get_patient(patient_id: int) -> Patient | None:
    return db.session.get(Patient, patient_id)


def update_patient(
    patient: Patient,
    full_name: str,
    date_of_birth,
    gender: str,
    phone_number: str,
    address: str,
    email: str = "",
    status: str = "Active",
    next_appointment=None,
    insurance_provider: str = "",
    insurance_policy_number: str = "",
    emergency_contact_name: str = "",
    emergency_contact_phone: str = "",
) -> Patient:
    patient.full_name = full_name
    patient.date_of_birth = date_of_birth
    patient.gender = gender
    patient.phone_number = phone_number
    patient.address = address
    patient.email = email
    patient.status = status
    patient.next_appointment = next_appointment
    patient.insurance_provider = insurance_provider
    patient.insurance_policy_number = insurance_policy_number
    patient.emergency_contact_name = emergency_contact_name
    patient.emergency_contact_phone = emergency_contact_phone
    db.session.commit()
    return patient


def last_visit(patient_id: int):
    """Most recent consultation date for a patient, or None if they've never had one."""
    consultations = patient_consultations(patient_id)
    return consultations[0].created_at if consultations else None


def appointment_counts_for_month(year: int, month: int) -> dict:
    """{day_of_month: count} for patients whose next_appointment falls in that month."""
    days_in_month = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, days_in_month)
    patients = Patient.query.filter(
        Patient.next_appointment >= month_start, Patient.next_appointment <= month_end
    ).all()
    counts = {}
    for patient in patients:
        counts[patient.next_appointment.day] = counts.get(patient.next_appointment.day, 0) + 1
    return counts


def appointments_on_date(day):
    return Patient.query.filter(Patient.next_appointment == day).order_by(Patient.full_name).all()


def delete_patient(patient: Patient) -> None:
    db.session.delete(patient)
    db.session.commit()


def staff_counts_by_role() -> dict:
    counts = {role: 0 for role in STAFF_ROLES}
    for role, count in db.session.query(Staff.role, db.func.count(Staff.id)).group_by(Staff.role).all():
        counts[role] = count
    return counts


def recent_staff(limit: int = 5):
    """Most recently added staff across every role, newest first."""
    return [(s.role, s) for s in Staff.query.order_by(Staff.created_at.desc()).limit(limit).all()]


def recent_patients(limit: int = 5):
    return Patient.query.order_by(Patient.created_at.desc()).limit(limit).all()


def total_patient_count() -> int:
    return Patient.query.count()


class ClinicSettings(db.Model):
    """Singleton row (id is always 1) holding clinic-wide configuration."""

    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(300), nullable=False, default="")
    phone_number = db.Column(db.String(20), nullable=False, default="")
    operating_hours = db.Column(db.String(200), nullable=False, default="")
    pin_length = db.Column(db.Integer, nullable=False, default=4)
    doctor_theme = db.Column(db.String(10), nullable=False, default="light")
    nurse_theme = db.Column(db.String(10), nullable=False, default="light")
    pharmacist_theme = db.Column(db.String(10), nullable=False, default="light")
    admin_theme = db.Column(db.String(10), nullable=False, default="light")
    receptionist_theme = db.Column(db.String(10), nullable=False, default="light")
    lab_technician_theme = db.Column(db.String(10), nullable=False, default="light")
    other_theme = db.Column(db.String(10), nullable=False, default="light")
    announcement = db.Column(db.Text, nullable=False, default="")
    late_payment_fee = db.Column(db.Float, nullable=False, default=0.0)


def get_settings() -> ClinicSettings:
    settings = db.session.get(ClinicSettings, 1)
    if settings is None:
        settings = ClinicSettings(id=1)
        db.session.add(settings)
        db.session.commit()
    return settings


def update_clinic_profile(address: str, phone_number: str, operating_hours: str) -> ClinicSettings:
    settings = get_settings()
    settings.address = address
    settings.phone_number = phone_number
    settings.operating_hours = operating_hours
    db.session.commit()
    return settings


def update_pin_policy(pin_length: int) -> ClinicSettings:
    settings = get_settings()
    settings.pin_length = pin_length
    db.session.commit()
    return settings


def update_announcement(text: str) -> ClinicSettings:
    settings = get_settings()
    settings.announcement = text
    db.session.commit()
    return settings


def update_department_themes(themes: dict) -> ClinicSettings:
    """themes: {"doctor": "light"|"dark", "nurse": ..., "pharmacist": ..., "admin": ...}"""
    settings = get_settings()
    for role, theme in themes.items():
        setattr(settings, f"{role}_theme", theme)
    db.session.commit()
    return settings


def update_late_payment_fee(fee: float) -> ClinicSettings:
    settings = get_settings()
    settings.late_payment_fee = fee
    db.session.commit()
    return settings


def theme_for_role(role: str | None) -> str:
    if role not in STAFF_ROLES:
        return "light"
    return getattr(get_settings(), f"{role}_theme")


class Consultation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=False)
    notes = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    patient = db.relationship("Patient")
    doctor = db.relationship("Staff", foreign_keys=[doctor_id])


class Prescription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=False)
    medication_name = db.Column(db.String(200), nullable=False)
    dosage = db.Column(db.String(100), nullable=False)
    instructions = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    patient = db.relationship("Patient")
    doctor = db.relationship("Staff", foreign_keys=[doctor_id])


def add_consultation(patient_id: int, doctor_id: int, notes: str) -> Consultation:
    consultation = Consultation(patient_id=patient_id, doctor_id=doctor_id, notes=notes)
    db.session.add(consultation)
    db.session.commit()
    # The author has obviously "read" their own note.
    db.session.add(ConsultationRead(staff_role="doctor", staff_id=doctor_id, consultation_id=consultation.id))
    db.session.commit()
    return consultation


def add_prescription(patient_id: int, doctor_id: int, medication_name: str, dosage: str, instructions: str) -> Prescription:
    prescription = Prescription(
        patient_id=patient_id,
        doctor_id=doctor_id,
        medication_name=medication_name,
        dosage=dosage,
        instructions=instructions,
    )
    db.session.add(prescription)
    db.session.commit()
    return prescription


def patient_consultations(patient_id: int):
    return Consultation.query.filter_by(patient_id=patient_id).order_by(Consultation.created_at.desc()).all()


def patient_prescriptions(patient_id: int):
    return Prescription.query.filter_by(patient_id=patient_id).order_by(Prescription.created_at.desc()).all()


def count_consultations_by_doctor(doctor_id: int) -> int:
    return Consultation.query.filter_by(doctor_id=doctor_id).count()


def count_prescriptions_by_doctor(doctor_id: int) -> int:
    return Prescription.query.filter_by(doctor_id=doctor_id).count()


def new_patients_since(since: datetime) -> int:
    return Patient.query.filter(Patient.created_at >= since).count()


def new_patients_per_day(days: int = 7):
    """List of (date, count) for the last `days` days, oldest first."""
    today = datetime.now().date()
    start = today - timedelta(days=days - 1)
    counts = {start + timedelta(days=i): 0 for i in range(days)}
    window_start = datetime.combine(start, datetime.min.time())
    for patient in Patient.query.filter(Patient.created_at >= window_start).all():
        day = patient.created_at.date()
        if day in counts:
            counts[day] += 1
    return [(day, counts[day]) for day in sorted(counts)]


def patient_growth(days: int = 30):
    """Cumulative total patient count at the end of each of the last `days` days."""
    today = datetime.now().date()
    start = today - timedelta(days=days - 1)
    created_dates = sorted(p.created_at for p in Patient.query.all())
    result = []
    idx = 0
    running_total = sum(1 for d in created_dates if d < datetime.combine(start, datetime.min.time()))
    for i in range(days):
        day = start + timedelta(days=i)
        day_end = datetime.combine(day, datetime.max.time())
        while idx < len(created_dates) and created_dates[idx] <= day_end:
            running_total += 1
            idx += 1
        result.append((day, running_total))
    return result


def recent_consultations(limit: int = 10):
    return Consultation.query.order_by(Consultation.created_at.desc()).limit(limit).all()


def recent_prescriptions(limit: int = 10):
    return Prescription.query.order_by(Prescription.created_at.desc()).limit(limit).all()


def recent_activity(limit: int = 8):
    """Clinic-wide activity feed combining every real event we track,
    newest first. No read/unread state — just the latest few of each kind."""
    events = []

    for patient in recent_patients(limit):
        events.append({
            "created_at": patient.created_at,
            "message": f"New patient registered: {patient.full_name} (#{patient.patient_number})",
        })

    for role, staff in recent_staff(limit):
        events.append({
            "created_at": staff.created_at,
            "message": f"{STAFF_LABELS[role]} added: {staff.full_name}",
        })

    for consultation in recent_consultations(limit):
        events.append({
            "created_at": consultation.created_at,
            "message": f"Consultation recorded for {consultation.patient.full_name} by {consultation.doctor.full_name}",
        })

    for prescription in recent_prescriptions(limit):
        events.append({
            "created_at": prescription.created_at,
            "message": f"Prescription added for {prescription.patient.full_name}: {prescription.medication_name}",
        })

    for ticket in SupportTicket.query.order_by(SupportTicket.created_at.desc()).limit(limit).all():
        events.append({
            "created_at": ticket.created_at,
            "message": f"Support ticket submitted by {ticket.submitted_by_name}: {ticket.subject}",
        })

    events.sort(key=lambda e: e["created_at"], reverse=True)
    return events[:limit]


class SupportTicket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    submitted_by_role = db.Column(db.String(20), nullable=False)
    submitted_by_name = db.Column(db.String(200), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open")
    created_at = db.Column(db.DateTime, default=datetime.now)


def create_ticket(role: str, staff_full_name: str, subject: str, message: str) -> SupportTicket:
    ticket = SupportTicket(
        submitted_by_role=role,
        submitted_by_name=staff_full_name,
        subject=subject,
        message=message,
    )
    db.session.add(ticket)
    db.session.commit()
    return ticket


def list_all_tickets():
    return SupportTicket.query.order_by(SupportTicket.created_at.desc()).all()


def list_tickets_by_submitter(role: str, staff_full_name: str):
    return (
        SupportTicket.query.filter_by(submitted_by_role=role, submitted_by_name=staff_full_name)
        .order_by(SupportTicket.created_at.desc())
        .all()
    )


def get_ticket(ticket_id: int) -> SupportTicket | None:
    return db.session.get(SupportTicket, ticket_id)


def resolve_ticket(ticket: SupportTicket) -> SupportTicket:
    ticket.status = "resolved"
    db.session.commit()
    return ticket


def open_ticket_count() -> int:
    return SupportTicket.query.filter_by(status="open").count()


DEFAULT_DASHBOARD_WIDGETS = {
    "admin": ["quick_actions", "dashboard_summary", "chart_new_patients", "chart_staff_pie", "chart_growth", "calendar"],
    "doctor": ["dashboard_summary", "calendar"],
}

DASHBOARD_WIDGET_LABELS = {
    "quick_actions": "Quick actions",
    "dashboard_summary": "Dashboard summary",
    "chart_new_patients": "New patients chart",
    "chart_staff_pie": "Staff by role chart",
    "chart_growth": "Patient growth chart",
    "calendar": "Calendar",
}


class DashboardLayout(db.Model):
    """One row per (staff member, widget): its position and whether it's hidden."""

    id = db.Column(db.Integer, primary_key=True)
    staff_role = db.Column(db.String(20), nullable=False)
    staff_id = db.Column(db.Integer, nullable=False)
    widget_key = db.Column(db.String(50), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    hidden = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (db.UniqueConstraint("staff_role", "staff_id", "widget_key"),)


def get_dashboard_layout(role: str, staff_id: int):
    """List of {key, label, hidden} in the staff member's saved order.
    Seeds their layout from the role's defaults on first access."""
    rows = DashboardLayout.query.filter_by(staff_role=role, staff_id=staff_id).order_by(DashboardLayout.position).all()
    if not rows:
        for i, key in enumerate(DEFAULT_DASHBOARD_WIDGETS.get(role, [])):
            db.session.add(DashboardLayout(staff_role=role, staff_id=staff_id, widget_key=key, position=i))
        db.session.commit()
        rows = DashboardLayout.query.filter_by(staff_role=role, staff_id=staff_id).order_by(DashboardLayout.position).all()
    return [{"key": r.widget_key, "label": DASHBOARD_WIDGET_LABELS.get(r.widget_key, r.widget_key), "hidden": r.hidden} for r in rows]


def save_dashboard_order(role: str, staff_id: int, ordered_keys: list) -> None:
    """Re-save the layout in `ordered_keys` order, preserving current hidden flags."""
    valid_keys = set(DEFAULT_DASHBOARD_WIDGETS.get(role, []))
    ordered_keys = [k for k in ordered_keys if k in valid_keys]
    existing = {row.widget_key: row for row in DashboardLayout.query.filter_by(staff_role=role, staff_id=staff_id).all()}

    for i, key in enumerate(ordered_keys):
        if key in existing:
            existing[key].position = i
        else:
            db.session.add(DashboardLayout(staff_role=role, staff_id=staff_id, widget_key=key, position=i))

    missing = valid_keys - set(ordered_keys)
    for i, key in enumerate(missing, start=len(ordered_keys)):
        if key in existing:
            existing[key].position = i
        else:
            db.session.add(DashboardLayout(staff_role=role, staff_id=staff_id, widget_key=key, position=i))

    db.session.commit()


def toggle_dashboard_widget(role: str, staff_id: int, widget_key: str) -> None:
    get_dashboard_layout(role, staff_id)  # ensure seeded
    row = DashboardLayout.query.filter_by(staff_role=role, staff_id=staff_id, widget_key=widget_key).first()
    if row:
        row.hidden = not row.hidden
        db.session.commit()


AGE_BRACKETS = [("0-17", 0, 17), ("18-35", 18, 35), ("36-50", 36, 50), ("51-65", 51, 65), ("66+", 66, 999)]


def _age(date_of_birth) -> int:
    today = date.today()
    return today.year - date_of_birth.year - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))


def _age_bracket(age: int) -> str:
    for label, lo, hi in AGE_BRACKETS:
        if lo <= age <= hi:
            return label
    return AGE_BRACKETS[-1][0]


def demographics_summary() -> dict:
    patients = Patient.query.all()
    gender_counts = {"Female": 0, "Male": 0, "Other": 0}
    status_counts = {status: 0 for status in PATIENT_STATUSES}
    for patient in patients:
        gender_counts[patient.gender] = gender_counts.get(patient.gender, 0) + 1
        status_counts[patient.status] = status_counts.get(patient.status, 0) + 1
    return {"total": len(patients), "gender_counts": gender_counts, "status_counts": status_counts}


def age_gender_breakdown():
    """List of {age_group, Female, Male, Other, total} rows, one per age bracket."""
    genders = ["Female", "Male", "Other"]
    breakdown = {label: {g: 0 for g in genders} for label, _, _ in AGE_BRACKETS}
    for patient in Patient.query.all():
        bracket = _age_bracket(_age(patient.date_of_birth))
        if patient.gender in breakdown[bracket]:
            breakdown[bracket][patient.gender] += 1

    rows = []
    for label, _, _ in AGE_BRACKETS:
        counts = breakdown[label]
        rows.append({"age_group": label, **counts, "total": sum(counts.values())})
    return rows


def new_registrations_by_month(months: int = 12):
    """List of ('YYYY-MM', count) for each of the last `months` months, oldest first."""
    today = date.today()
    buckets = []
    year, month = today.year, today.month
    for _ in range(months):
        buckets.append((year, month))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    buckets.reverse()

    counts = {b: 0 for b in buckets}
    earliest_year, earliest_month = buckets[0]
    window_start = datetime(earliest_year, earliest_month, 1)
    for patient in Patient.query.filter(Patient.created_at >= window_start).all():
        key = (patient.created_at.year, patient.created_at.month)
        if key in counts:
            counts[key] += 1

    return [(f"{y}-{m:02d}", counts[(y, m)]) for y, m in buckets]


def patient_missing_fields(patient: Patient) -> list:
    """Labels for commonly-expected fields that are blank on this patient."""
    missing = []
    if not patient.email:
        missing.append("email")
    if not patient.address:
        missing.append("address")
    return missing


def is_overdue(patient: Patient) -> bool:
    return bool(patient.next_appointment and patient.next_appointment < date.today())


def overdue_appointment_count() -> int:
    return Patient.query.filter(Patient.next_appointment < date.today()).count()


class ConsultationRead(db.Model):
    """Tracks which staff member has seen which consultation note."""

    id = db.Column(db.Integer, primary_key=True)
    staff_role = db.Column(db.String(20), nullable=False)
    staff_id = db.Column(db.Integer, nullable=False)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultation.id"), nullable=False)

    __table_args__ = (db.UniqueConstraint("staff_role", "staff_id", "consultation_id"),)


def mark_patient_notes_read(role: str, staff_id: int, patient_id: int) -> None:
    already_read = {
        r.consultation_id
        for r in ConsultationRead.query.filter_by(staff_role=role, staff_id=staff_id).all()
    }
    for consultation in Consultation.query.filter_by(patient_id=patient_id).all():
        if consultation.id not in already_read:
            db.session.add(ConsultationRead(staff_role=role, staff_id=staff_id, consultation_id=consultation.id))
    db.session.commit()


def unread_notes_count(role: str, staff_id: int, patient_id: int | None = None) -> int:
    q = Consultation.query
    if patient_id is not None:
        q = q.filter_by(patient_id=patient_id)
    read_ids = {
        r.consultation_id
        for r in ConsultationRead.query.filter_by(staff_role=role, staff_id=staff_id).all()
    }
    return sum(1 for c in q.all() if c.id not in read_ids)


def unread_notes_by_patient(role: str, staff_id: int) -> dict:
    """{patient_id: unread_count} across every patient with at least one unread note."""
    read_ids = {
        r.consultation_id
        for r in ConsultationRead.query.filter_by(staff_role=role, staff_id=staff_id).all()
    }
    counts = {}
    for consultation in Consultation.query.all():
        if consultation.id not in read_ids:
            counts[consultation.patient_id] = counts.get(consultation.patient_id, 0) + 1
    return counts


class LabResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    technician_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=False)
    test_name = db.Column(db.String(200), nullable=False)
    result = db.Column(db.String(500), nullable=False)
    notes = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, default=datetime.now)

    patient = db.relationship("Patient")
    technician = db.relationship("Staff", foreign_keys=[technician_id])


def add_lab_result(patient_id: int, technician_id: int, test_name: str, result: str, notes: str = "") -> LabResult:
    lab_result = LabResult(
        patient_id=patient_id, technician_id=technician_id, test_name=test_name, result=result, notes=notes
    )
    db.session.add(lab_result)
    db.session.commit()
    return lab_result


def patient_lab_results(patient_id: int):
    return LabResult.query.filter_by(patient_id=patient_id).order_by(LabResult.created_at.desc()).all()


def count_lab_results_by_technician(technician_id: int) -> int:
    return LabResult.query.filter_by(technician_id=technician_id).count()


# -------------------- Billing & Finance: tariffs and medical aid schemes --------------------
# Foundation only: the service/price catalog and the medical aid scheme catalog with
# contracted rates. Patient invoicing, claims, and revenue reports build on top of this
# once it exists, and aren't part of this pass.

class ServiceTariff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    category = db.Column(db.String(100), nullable=False, default="")
    price = db.Column(db.Float, nullable=False)
    tariff_code = db.Column(db.String(50), nullable=False, default="")
    requires_preauth = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


def list_tariffs():
    return ServiceTariff.query.order_by(ServiceTariff.category, ServiceTariff.name).all()


def add_tariff(name: str, category: str, price: float, tariff_code: str = "", requires_preauth: bool = False) -> ServiceTariff:
    tariff = ServiceTariff(
        name=name, category=category, price=price, tariff_code=tariff_code, requires_preauth=requires_preauth
    )
    db.session.add(tariff)
    db.session.commit()
    return tariff


def delete_tariff(tariff_id: int) -> None:
    tariff = db.session.get(ServiceTariff, tariff_id)
    if tariff:
        db.session.delete(tariff)
        db.session.commit()


class DiscountPolicy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    percentage = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


def list_discount_policies():
    return DiscountPolicy.query.order_by(DiscountPolicy.name).all()


def add_discount_policy(name: str, percentage: float) -> DiscountPolicy:
    policy = DiscountPolicy(name=name, percentage=percentage)
    db.session.add(policy)
    db.session.commit()
    return policy


def delete_discount_policy(policy_id: int) -> None:
    policy = db.session.get(DiscountPolicy, policy_id)
    if policy:
        db.session.delete(policy)
        db.session.commit()


class MedicalAidScheme(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    direct_billing_enabled = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


def list_medical_aid_schemes():
    return MedicalAidScheme.query.order_by(MedicalAidScheme.name).all()


def add_medical_aid_scheme(name: str) -> MedicalAidScheme:
    scheme = MedicalAidScheme(name=name)
    db.session.add(scheme)
    db.session.commit()
    return scheme


def delete_medical_aid_scheme(scheme_id: int) -> None:
    scheme = db.session.get(MedicalAidScheme, scheme_id)
    if scheme:
        db.session.delete(scheme)
        db.session.commit()


def toggle_direct_billing(scheme_id: int) -> None:
    scheme = db.session.get(MedicalAidScheme, scheme_id)
    if scheme:
        scheme.direct_billing_enabled = not scheme.direct_billing_enabled
        db.session.commit()


def seed_medical_aid_schemes(names: list) -> None:
    """Called once at startup. Adds any scheme names not already present;
    never overwrites or removes existing schemes."""
    existing = {s.name for s in MedicalAidScheme.query.all()}
    for name in names:
        if name not in existing:
            db.session.add(MedicalAidScheme(name=name))
    db.session.commit()


class MedicalAidRate(db.Model):
    """A negotiated rate for one service under one scheme. Absent here means
    the scheme pays the standard ServiceTariff.price for that service."""

    id = db.Column(db.Integer, primary_key=True)
    scheme_id = db.Column(db.Integer, db.ForeignKey("medical_aid_scheme.id"), nullable=False)
    tariff_id = db.Column(db.Integer, db.ForeignKey("service_tariff.id"), nullable=False)
    rate = db.Column(db.Float, nullable=False)

    scheme = db.relationship("MedicalAidScheme")
    tariff = db.relationship("ServiceTariff")

    __table_args__ = (db.UniqueConstraint("scheme_id", "tariff_id"),)


def list_medical_aid_rates():
    return MedicalAidRate.query.join(MedicalAidScheme).join(ServiceTariff).order_by(
        MedicalAidScheme.name, ServiceTariff.name
    ).all()


def set_medical_aid_rate(scheme_id: int, tariff_id: int, rate: float) -> MedicalAidRate:
    existing = MedicalAidRate.query.filter_by(scheme_id=scheme_id, tariff_id=tariff_id).first()
    if existing:
        existing.rate = rate
        db.session.commit()
        return existing
    entry = MedicalAidRate(scheme_id=scheme_id, tariff_id=tariff_id, rate=rate)
    db.session.add(entry)
    db.session.commit()
    return entry


def delete_medical_aid_rate(rate_id: int) -> None:
    rate = db.session.get(MedicalAidRate, rate_id)
    if rate:
        db.session.delete(rate)
        db.session.commit()
