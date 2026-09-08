"""
MediCare Clinic — Flask port of the original Flutter app.

Run with:
    pip install -r requirements.txt
    python app.py

Then open http://127.0.0.1:5000
"""

import os
from datetime import datetime, timedelta, date

from flask import Flask, render_template, request, redirect, url_for, session, flash

from models import (
    db,
    Patient,
    PatientFile,
    Doctor,
    Nurse,
    Admin,
    AuditLog,
    HandoverNote,
    ChecklistItem,
    PatientRequest,
    VitalsReading,
    Medication,
    Prescription,
    MedicationAdministration,
    find_file,
    find_doctor,
    find_nurse,
    find_admin,
    log_action,
    recent_audit_log,
    all_files,
    all_doctors,
    active_files,
    recent_handover_notes,
    latest_handover_note,
    checklist_for,
    open_requests,
    record_vitals_reading,
    vitals_history,
    latest_vitals_flags,
    seed_medications,
    all_medications,
    find_medication,
    prescriptions_for,
    recent_administrations,
    ROUTINE_TASKS,
    REQUEST_CATEGORIES,
    REQUEST_STATUS_OPEN,
    REQUEST_STATUS_DONE,
    STATUS_REGISTERED,
    STATUS_EVALUATED,
    STATUS_DISPENSED,
    PRIORITY_NORMAL,
    PRIORITY_URGENT,
)
from ml.diagnosis_model import predict_diagnoses, DISCLAIMER as DIAGNOSIS_DISCLAIMER
from ml.medication_model import predict_medications, DISCLAIMER as MEDICATION_DISCLAIMER

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

SESSION_TIMEOUT_MINUTES = 30

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-me"  # replace with a real secret in production
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "clinic.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Sessions expire after SESSION_TIMEOUT_MINUTES of inactivity (refreshed on
# every request by Flask's default SESSION_REFRESH_EACH_REQUEST behavior).
app.permanent_session_lifetime = timedelta(minutes=SESSION_TIMEOUT_MINUTES)

db.init_app(app)
with app.app_context():
    db.create_all()
    seed_medications()


# -------------------- Validation helpers --------------------

def is_valid_id_number(value: str) -> bool:
    return bool(value) and value.isdigit() and len(value) == 13


def is_valid_username(value: str) -> bool:
    return bool(value) and value.isdigit() and len(value) == 6


def is_valid_pin(value: str) -> bool:
    return bool(value) and value.isdigit() and len(value) == 4


def current_doctor() -> Doctor | None:
    username = session.get("doctor_username")
    if not username:
        return None
    return find_doctor(username)


def current_nurse() -> Nurse | None:
    username = session.get("nurse_username")
    if not username:
        return None
    return find_nurse(username)


def current_admin() -> Admin | None:
    username = session.get("admin_username")
    if not username:
        return None
    return find_admin(username)


# -------------------- Admin auth --------------------

@app.route("/admin/auth")
def admin_auth():
    if current_admin():
        return redirect(url_for("admin_dashboard"))
    tab = request.args.get("tab", "login")
    return render_template("admin_auth.html", tab=tab)


@app.route("/admin/login", methods=["POST"])
def admin_login():
    username = request.form.get("username", "").strip()
    pin = request.form.get("pin", "").strip()

    if not is_valid_username(username) or not is_valid_pin(pin):
        flash("Enter a 6-digit username and 4-digit PIN.", "error")
        return redirect(url_for("admin_auth", tab="login"))

    admin_user = find_admin(username)
    if admin_user is None or admin_user.pin != pin:
        log_action("admin", username, "login_failed")
        flash("Invalid credentials.", "error")
        return redirect(url_for("admin_auth", tab="login"))

    session.permanent = True
    session["admin_username"] = admin_user.username
    log_action("admin", admin_user.username, "login")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/register-account", methods=["POST"])
def admin_register_account():
    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip()
    pin = request.form.get("pin", "").strip()

    errors = []
    if not full_name:
        errors.append("Enter your full name.")
    if not is_valid_username(username):
        errors.append("Username must be exactly 6 digits.")
    if not is_valid_pin(pin):
        errors.append("PIN must be exactly 4 digits.")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("admin_auth", tab="register"))

    if find_admin(username):
        flash("Username already taken.", "warning")
        return redirect(url_for("admin_auth", tab="register"))

    db.session.add(Admin(username=username, pin=pin, full_name=full_name))
    db.session.commit()
    log_action("admin", username, "account_registered")
    flash("Admin account registered successfully. You can now log in.", "success")
    return redirect(url_for("admin_auth", tab="login"))


@app.route("/admin/logout")
def admin_logout():
    admin_user = current_admin()
    if admin_user:
        log_action("admin", admin_user.username, "logout")
    session.pop("admin_username", None)
    return redirect(url_for("admin_auth"))


# -------------------- Home --------------------

@app.route("/")
def home():
    return render_template("stations.html")


# -------------------- Admin --------------------

@app.route("/admin")
def admin():
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))
    tab = request.args.get("tab", "register")
    return render_template("admin.html", tab=tab, files=all_files(), medications=all_medications(), admin=admin_user)


@app.route("/admin/register", methods=["POST"])
def admin_register():
    if not current_admin():
        return redirect(url_for("admin_auth"))

    id_number = request.form.get("id_number", "").strip()
    full_name = request.form.get("full_name", "").strip()
    age = request.form.get("age", "").strip()
    gender = request.form.get("gender", "Male")
    phone = request.form.get("phone", "").strip()
    street = request.form.get("street", "").strip()
    city = request.form.get("city", "").strip()
    province = request.form.get("province", "").strip()
    postal_code = request.form.get("postal_code", "").strip()

    errors = []
    if not is_valid_id_number(id_number):
        errors.append("Enter a valid 13-digit ID number.")
    if not full_name:
        errors.append("Enter the patient's full name.")
    if not age:
        errors.append("Enter the patient's age.")
    if not phone:
        errors.append("Enter a phone number.")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("admin", tab="register"))

    if find_file(id_number):
        flash("Patient already exists!", "warning")
        return redirect(url_for("admin", tab="register"))

    new_patient = Patient(
        id_number=id_number,
        full_name=full_name,
        age=age,
        gender=gender,
        phone=phone,
        street=street,
        city=city,
        province=province,
        postal_code=postal_code,
    )
    db.session.add(new_patient)
    db.session.add(PatientFile(patient=new_patient))
    db.session.commit()
    log_action("admin", current_admin().username, "patient_registered", f"{full_name} ({id_number})")

    flash("Patient registered successfully.", "success")
    return redirect(url_for("admin", tab="list"))


@app.route("/admin/medications/add", methods=["POST"])
def admin_add_medication():
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    name = request.form.get("name", "").strip()
    common_dosage = request.form.get("common_dosage", "").strip()
    form = request.form.get("form", "").strip()
    category = request.form.get("category", "").strip()

    if not name:
        flash("Enter a medication name.", "error")
        return redirect(url_for("admin", tab="medications"))

    if Medication.query.filter_by(name=name).first():
        flash("That medication is already in the catalog.", "warning")
        return redirect(url_for("admin", tab="medications"))

    db.session.add(Medication(name=name, common_dosage=common_dosage, form=form, category=category))
    db.session.commit()
    log_action("admin", admin_user.username, "medication_added", name)
    flash(f"{name} added to the medication catalog.", "success")
    return redirect(url_for("admin", tab="medications"))


# -------------------- Doctor auth --------------------

@app.route("/doctor")
def doctor_auth():
    if current_doctor():
        return redirect(url_for("doctor_panel"))
    tab = request.args.get("tab", "login")
    return render_template("doctor_auth.html", tab=tab)


@app.route("/doctor/login", methods=["POST"])
def doctor_login():
    username = request.form.get("username", "").strip()
    pin = request.form.get("pin", "").strip()

    if not is_valid_username(username) or not is_valid_pin(pin):
        flash("Enter a 6-digit username and 4-digit PIN.", "error")
        return redirect(url_for("doctor_auth", tab="login"))

    doctor = find_doctor(username)
    if doctor is None or doctor.pin != pin:
        log_action("doctor", username, "login_failed")
        flash("Invalid credentials.", "error")
        return redirect(url_for("doctor_auth", tab="login"))

    session.permanent = True
    session["doctor_username"] = doctor.username
    log_action("doctor", doctor.username, "login")
    return redirect(url_for("doctor_panel"))


@app.route("/doctor/register", methods=["POST"])
def doctor_register():
    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip()
    pin = request.form.get("pin", "").strip()

    errors = []
    if not full_name:
        errors.append("Enter your full name.")
    if not is_valid_username(username):
        errors.append("Username must be exactly 6 digits.")
    if not is_valid_pin(pin):
        errors.append("PIN must be exactly 4 digits.")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("doctor_auth", tab="register"))

    if find_doctor(username):
        flash("Username already taken.", "warning")
        return redirect(url_for("doctor_auth", tab="register"))

    db.session.add(Doctor(username=username, pin=pin, full_name=full_name))
    db.session.commit()
    flash("Doctor registered successfully. You can now log in.", "success")
    return redirect(url_for("doctor_auth", tab="login"))


@app.route("/doctor/logout")
def doctor_logout():
    doctor = current_doctor()
    if doctor:
        log_action("doctor", doctor.username, "logout")
    session.pop("doctor_username", None)
    return redirect(url_for("doctor_auth"))


@app.route("/doctor/panel")
def doctor_panel():
    doctor = current_doctor()
    if not doctor:
        return redirect(url_for("doctor_auth"))
    return render_template("doctor_panel.html", doctor=doctor, files=all_files())


@app.route("/doctor/patient/<id_number>", methods=["GET", "POST"])
def patient_detail(id_number):
    doctor = current_doctor()
    if not doctor:
        return redirect(url_for("doctor_auth"))

    file = find_file(id_number)
    if file is None:
        flash("Patient file not found.", "error")
        return redirect(url_for("doctor_panel"))

    suggestions = None

    if request.method == "POST":
        action = request.form.get("action")
        if action == "toggle_priority":
            file.priority = PRIORITY_URGENT if file.priority == PRIORITY_NORMAL else PRIORITY_NORMAL
            db.session.commit()
            return redirect(url_for("patient_detail", id_number=id_number))
        elif action == "update":
            file.doctor_notes = request.form.get("doctor_notes", "").strip()
            file.status = STATUS_EVALUATED
            file.evaluated_by = doctor.username
            db.session.commit()
            log_action("doctor", doctor.username, "patient_evaluated", file.patient.full_name)
            flash("Patient file updated successfully.", "success")
            return redirect(url_for("doctor_panel"))
        elif action == "suggest":
            entered = request.form.get("symptoms", "").strip()
            if entered:
                file.symptoms = entered
                db.session.commit()
                suggestions = predict_diagnoses(file.symptoms, top_n=3)
            else:
                flash("Enter symptoms before requesting suggestions.", "warning")
        elif action == "prescribe":
            medication_id = request.form.get("medication_id", "")
            medication = find_medication(int(medication_id)) if medication_id.isdigit() else None
            if medication is None:
                flash("Choose a medication to prescribe.", "error")
            else:
                db.session.add(Prescription(
                    patient_id=id_number,
                    medication_id=medication.id,
                    dosage=request.form.get("dosage", "").strip() or medication.common_dosage,
                    frequency=request.form.get("frequency", "").strip(),
                    duration=request.form.get("duration", "").strip(),
                    instructions=request.form.get("instructions", "").strip(),
                    prescribed_by=doctor.username,
                ))
                db.session.commit()
                log_action("doctor", doctor.username, "prescribed", f"{medication.name} for {file.patient.full_name}")
                flash(f"{medication.name} prescribed for {file.patient.full_name}.", "success")
            return redirect(url_for("patient_detail", id_number=id_number))

    return render_template(
        "patient_detail.html",
        file=file,
        doctor=doctor,
        suggestions=suggestions,
        diagnosis_disclaimer=DIAGNOSIS_DISCLAIMER,
        medications=all_medications(),
        prescriptions=prescriptions_for(id_number),
    )


# -------------------- Pharmacist --------------------

@app.route("/pharmacist")
def pharmacist():
    evaluated = [f for f in all_files() if f.status == STATUS_EVALUATED]

    suggest_for = request.args.get("suggest", "")
    medication_suggestions = None
    if suggest_for:
        target = next((f for f in evaluated if f.patient.id_number == suggest_for), None)
        if target is not None:
            medication_suggestions = predict_medications(target.doctor_notes)

    return render_template(
        "pharmacist.html", files=evaluated,
        suggest_for=suggest_for, medication_suggestions=medication_suggestions,
        medication_disclaimer=MEDICATION_DISCLAIMER,
    )


@app.route("/pharmacist/dispense/<id_number>", methods=["POST"])
def dispense(id_number):
    file = find_file(id_number)
    if file:
        file.status = STATUS_DISPENSED
        file.pharmacist_notes = f"Medication dispensed on {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        db.session.commit()
        log_action("pharmacist", "", "dispensed", file.patient.full_name)
        flash("Medication dispensed successfully.", "success")
    return redirect(url_for("pharmacist"))


# -------------------- Nurse auth --------------------

@app.route("/nurse")
def nurse_auth():
    if current_nurse():
        return redirect(url_for("nursing"))
    tab = request.args.get("tab", "login")
    return render_template("nurse_auth.html", tab=tab)


@app.route("/nurse/login", methods=["POST"])
def nurse_login():
    username = request.form.get("username", "").strip()
    pin = request.form.get("pin", "").strip()

    if not is_valid_username(username) or not is_valid_pin(pin):
        flash("Enter a 6-digit username and 4-digit PIN.", "error")
        return redirect(url_for("nurse_auth", tab="login"))

    nurse = find_nurse(username)
    if nurse is None or nurse.pin != pin:
        log_action("nurse", username, "login_failed")
        flash("Invalid credentials.", "error")
        return redirect(url_for("nurse_auth", tab="login"))

    session.permanent = True
    session["nurse_username"] = nurse.username
    log_action("nurse", nurse.username, "login")
    return redirect(url_for("nursing"))


@app.route("/nurse/register", methods=["POST"])
def nurse_register():
    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip()
    pin = request.form.get("pin", "").strip()

    errors = []
    if not full_name:
        errors.append("Enter your full name.")
    if not is_valid_username(username):
        errors.append("Username must be exactly 6 digits.")
    if not is_valid_pin(pin):
        errors.append("PIN must be exactly 4 digits.")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("nurse_auth", tab="register"))

    if find_nurse(username):
        flash("Username already taken.", "warning")
        return redirect(url_for("nurse_auth", tab="register"))

    db.session.add(Nurse(username=username, pin=pin, full_name=full_name))
    db.session.commit()
    flash("Nurse registered successfully. You can now log in.", "success")
    return redirect(url_for("nurse_auth", tab="login"))


@app.route("/nurse/logout")
def nurse_logout():
    nurse = current_nurse()
    if nurse:
        log_action("nurse", nurse.username, "logout")
    session.pop("nurse_username", None)
    return redirect(url_for("nurse_auth"))


# -------------------- Nursing --------------------

@app.route("/nursing")
def nursing():
    nurse = current_nurse()
    if not nurse:
        return redirect(url_for("nurse_auth"))
    files = all_files()
    latest_notes = {f.patient.id_number: latest_handover_note(f.patient.id_number) for f in files}
    checklists = {f.patient.id_number: checklist_for(f.patient.id_number) for f in files}
    vitals_flags = {f.patient.id_number: latest_vitals_flags(f.patient.id_number) for f in files}
    prescriptions = {f.patient.id_number: prescriptions_for(f.patient.id_number) for f in files}
    administrations = {
        p.id: recent_administrations(p.id, limit=3)
        for plist in prescriptions.values() for p in plist
    }
    return render_template(
        "nursing.html", nurse=nurse, files=files,
        latest_notes=latest_notes, checklists=checklists, vitals_flags=vitals_flags,
        prescriptions=prescriptions, administrations=administrations,
        requests=open_requests(), request_labels=dict(REQUEST_CATEGORIES),
    )


@app.route("/nursing/vitals/<id_number>", methods=["POST"])
def record_vitals(id_number):
    nurse = current_nurse()
    if not nurse:
        return redirect(url_for("nurse_auth"))

    file = find_file(id_number)
    if file is None:
        flash("Patient file not found.", "error")
        return redirect(url_for("nursing"))

    temperature = request.form.get("temperature", "").strip()
    blood_pressure = request.form.get("blood_pressure", "").strip()
    pulse = request.form.get("pulse", "").strip()

    if not (temperature or blood_pressure or pulse):
        flash("Enter at least one vital before saving.", "warning")
        return redirect(url_for("nursing"))

    file.temperature = temperature
    file.blood_pressure = blood_pressure
    file.pulse = pulse
    file.vitals_recorded_at = datetime.now()
    file.vitals_recorded_by = nurse.username

    reading = record_vitals_reading(id_number, temperature, blood_pressure, pulse, nurse.username)
    db.session.commit()
    log_action("nurse", nurse.username, "vitals_recorded", file.patient.full_name)

    if reading.flags:
        flash(f"⚠ Abnormal vitals for {file.patient.full_name}: {reading.flags}", "error")
    else:
        flash(f"Vitals recorded for {file.patient.full_name}.", "success")
    return redirect(url_for("nursing"))


def _vitals_pct(value, lo, hi):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    v = max(lo, min(hi, v))
    return round((v - lo) / (hi - lo) * 100)


@app.route("/nursing/vitals/<id_number>/history")
def vitals_history_page(id_number):
    nurse = current_nurse()
    if not nurse:
        return redirect(url_for("nurse_auth"))

    file = find_file(id_number)
    if file is None:
        flash("Patient file not found.", "error")
        return redirect(url_for("nursing"))

    readings = vitals_history(id_number)
    chart_rows = [
        {
            "reading": r,
            "temp_pct": _vitals_pct(r.temperature, 35, 40),
            "pulse_pct": _vitals_pct(r.pulse, 40, 140),
        }
        for r in reversed(readings)  # oldest first, left to right
    ]

    return render_template(
        "vitals_history.html", nurse=nurse, file=file,
        readings=readings, chart_rows=chart_rows,
    )


# -------------------- Shift handover --------------------

STALE_VITALS_MINUTES = 240  # vitals older than this are flagged as stale for the next shift


@app.route("/nursing/handover")
def nursing_handover():
    nurse = current_nurse()
    if not nurse:
        return redirect(url_for("nurse_auth"))

    now = datetime.now()
    entries = []
    for f in active_files():
        if f.vitals_recorded_at is None:
            vitals_state = "missing"
        elif (now - f.vitals_recorded_at).total_seconds() / 60 > STALE_VITALS_MINUTES:
            vitals_state = "stale"
        else:
            vitals_state = "fresh"

        pending = []
        if vitals_state != "fresh":
            pending.append("Vitals " + ("never recorded" if vitals_state == "missing" else "need re-check"))
        flags = latest_vitals_flags(f.patient.id_number)
        if flags:
            pending.append("⚠ Abnormal vitals: " + ", ".join(flags))
        if f.status == STATUS_REGISTERED:
            pending.append("Not yet seen by a doctor")
        elif f.status == STATUS_EVALUATED:
            pending.append("Awaiting pharmacy dispense")

        checklist = checklist_for(f.patient.id_number)
        incomplete = [t for t in checklist if not t["completed"]]
        if incomplete:
            pending.append(f"{len(incomplete)} of {len(checklist)} checklist tasks pending today")

        entries.append({
            "file": f,
            "vitals_state": vitals_state,
            "pending": pending,
            "notes": recent_handover_notes(f.patient.id_number),
        })

    return render_template("handover.html", nurse=nurse, entries=entries)


@app.route("/nursing/handover/<id_number>", methods=["POST"])
def add_handover_note(id_number):
    nurse = current_nurse()
    if not nurse:
        return redirect(url_for("nurse_auth"))

    next_url = request.form.get("next") or url_for("nursing_handover")

    file = find_file(id_number)
    if file is None:
        flash("Patient file not found.", "error")
        return redirect(next_url)

    note = request.form.get("note", "").strip()
    if not note:
        flash("Enter a note before saving.", "warning")
        return redirect(next_url)

    db.session.add(HandoverNote(patient_id=id_number, note=note, created_by=nurse.username))
    db.session.commit()
    flash(f"Handover note added for {file.patient.full_name}.", "success")
    return redirect(next_url)


@app.route("/nursing/checklist/<id_number>/<task_key>", methods=["POST"])
def toggle_checklist_item(id_number, task_key):
    nurse = current_nurse()
    if not nurse:
        return redirect(url_for("nurse_auth"))

    next_url = request.form.get("next") or url_for("nursing")

    if task_key not in dict(ROUTINE_TASKS):
        flash("Unknown checklist task.", "error")
        return redirect(next_url)

    today = date.today()
    item = ChecklistItem.query.filter_by(patient_id=id_number, task_key=task_key, task_date=today).first()
    if item is None:
        item = ChecklistItem(patient_id=id_number, task_key=task_key, task_date=today)
        db.session.add(item)

    item.completed = not item.completed
    item.completed_by = nurse.username if item.completed else ""
    item.completed_at = datetime.now() if item.completed else None
    db.session.commit()

    return redirect(next_url)


@app.route("/nursing/medications/<int:prescription_id>/administer", methods=["POST"])
def administer_medication(prescription_id):
    nurse = current_nurse()
    if not nurse:
        return redirect(url_for("nurse_auth"))

    next_url = request.form.get("next") or url_for("nursing")

    prescription = db.session.get(Prescription, prescription_id)
    if prescription is None:
        flash("Prescription not found.", "error")
        return redirect(next_url)

    db.session.add(MedicationAdministration(prescription_id=prescription_id, administered_by=nurse.username))
    db.session.commit()
    log_action("nurse", nurse.username, "medication_administered", f"{prescription.medication.name} to {prescription.patient.full_name}")
    flash(f"{prescription.medication.name} administered to {prescription.patient.full_name}.", "success")
    return redirect(next_url)


@app.route("/nursing/requests/<int:request_id>/resolve", methods=["POST"])
def resolve_patient_request(request_id):
    nurse = current_nurse()
    if not nurse:
        return redirect(url_for("nurse_auth"))

    next_url = request.form.get("next") or url_for("nursing")

    req = db.session.get(PatientRequest, request_id)
    if req is not None and req.status == REQUEST_STATUS_OPEN:
        req.status = REQUEST_STATUS_DONE
        req.resolved_by = nurse.username
        req.resolved_at = datetime.now()
        db.session.commit()

    return redirect(next_url)


# -------------------- Patient call button --------------------
# Public, no login required — meant to be opened on a bedside tablet or via a
# QR code tied to the patient's file, not something staff need to authenticate into.

@app.route("/patient/<id_number>/request")
def patient_request_page(id_number):
    file = find_file(id_number)
    if file is None:
        flash("Patient file not found.", "error")
        return redirect(url_for("home"))
    return render_template("patient_request.html", file=file, categories=REQUEST_CATEGORIES)


@app.route("/patient/<id_number>/request", methods=["POST"])
def submit_patient_request(id_number):
    file = find_file(id_number)
    if file is None:
        flash("Patient file not found.", "error")
        return redirect(url_for("home"))

    category = request.form.get("category", "")
    if category not in dict(REQUEST_CATEGORIES):
        flash("Choose a request type.", "error")
        return redirect(url_for("patient_request_page", id_number=id_number))

    db.session.add(PatientRequest(patient_id=id_number, category=category))
    db.session.commit()
    flash("A nurse has been notified.", "success")
    return redirect(url_for("patient_request_page", id_number=id_number))


# -------------------- Records --------------------

@app.route("/records")
def records():
    query = request.args.get("q", "").strip().lower()
    files = all_files()
    if query:
        files = [
            f for f in files
            if query in f.patient.full_name.lower()
            or query in f.patient.id_number
            or query in f.status.lower()
            or query in f.priority.lower()
        ]
    return render_template("records.html", files=files, query=query)


# -------------------- Statistics --------------------

@app.route("/statistics")
def statistics():
    files = all_files()
    stats = {
        "total": len(files),
        "registered": sum(1 for f in files if f.status == STATUS_REGISTERED),
        "evaluated": sum(1 for f in files if f.status == STATUS_EVALUATED),
        "dispensed": sum(1 for f in files if f.status == STATUS_DISPENSED),
        "urgent": sum(1 for f in files if f.priority == PRIORITY_URGENT),
    }
    return render_template("statistics.html", stats=stats)


# -------------------- Admin dashboard --------------------

def _build_dashboard_context():
    files = all_files()
    doctors = all_doctors()

    total = len(files)
    registered = sum(1 for f in files if f.status == STATUS_REGISTERED)
    evaluated = sum(1 for f in files if f.status == STATUS_EVALUATED)
    dispensed = sum(1 for f in files if f.status == STATUS_DISPENSED)
    urgent = sum(1 for f in files if f.priority == PRIORITY_URGENT)

    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday_counts = [0] * 7
    for f in files:
        weekday_counts[f.registered_at.weekday()] += 1
    max_weekday = max(weekday_counts) or 1
    weekday_data = [
        {"label": weekday_labels[i], "count": weekday_counts[i], "pct": round(weekday_counts[i] / max_weekday * 100)}
        for i in range(7)
    ]

    today = date.today()
    days = [today - timedelta(days=i) for i in range(27, -1, -1)]
    counts_by_day = {d: 0 for d in days}
    for f in files:
        d = f.registered_at.date()
        if d in counts_by_day:
            counts_by_day[d] += 1
    attendance = [
        {"date": d.strftime("%b %d"), "count": counts_by_day[d], "level": min(counts_by_day[d], 4)}
        for d in days
    ]

    now = datetime.now()
    waiting_raw = sorted(
        (
            {"name": f.patient.full_name, "minutes": round((now - f.registered_at).total_seconds() / 60)}
            for f in files if f.status == STATUS_REGISTERED
        ),
        key=lambda w: -w["minutes"],
    )[:8]
    max_wait = max((w["minutes"] for w in waiting_raw), default=0) or 1
    waiting = [dict(w, pct=round(w["minutes"] / max_wait * 100)) for w in waiting_raw]

    staff = sorted(
        (
            {
                "name": d.full_name,
                "username": d.username,
                "evaluated": sum(1 for f in files if f.evaluated_by == d.username),
            }
            for d in doctors
        ),
        key=lambda s: -s["evaluated"],
    )

    queue = sorted(
        (f for f in files if f.status != STATUS_DISPENSED),
        key=lambda f: (f.priority != PRIORITY_URGENT, f.registered_at),
    )[:6]

    def pct(n):
        return round((n / total) * 100, 1) if total else 0.0

    status_pct = {"registered": pct(registered), "evaluated": pct(evaluated), "dispensed": pct(dispensed)}

    return dict(
        total=total, registered=registered, evaluated=evaluated,
        dispensed=dispensed, urgent=urgent, status_pct=status_pct,
        weekday_data=weekday_data,
        attendance=attendance, waiting=waiting, staff=staff, queue=queue,
    )


@app.route("/admin/dashboard")
def admin_dashboard():
    if not current_admin():
        return redirect(url_for("admin_auth"))
    return render_template("admin_dashboard.html", admin=current_admin(), **_build_dashboard_context())


@app.route("/admin/audit-log")
def audit_log_page():
    if not current_admin():
        return redirect(url_for("admin_auth"))
    return render_template("audit_log.html", admin=current_admin(), entries=recent_audit_log())


if __name__ == "__main__":
    app.run(debug=True)