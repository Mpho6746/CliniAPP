"""
CliniApp — Flask port of the original Flutter app.

Run with:
    pip install -r requirements.txt
    python app.py

Then open http://127.0.0.1:5000
"""

import calendar
import csv
import io
import os
from datetime import datetime, timedelta, date

from flask import Flask, render_template, request, redirect, url_for, session, flash

from models import (
    db,
    Patient,
    PatientFile,
    Doctor,
    Nurse,
    Pharmacist,
    Admin,
    AuditLog,
    HandoverNote,
    ChecklistItem,
    PatientRequest,
    VitalsReading,
    Medication,
    Prescription,
    MedicationAdministration,
    MedicationTrainingExample,
    ClinicSettings,
    Product,
    Appointment,
    find_file,
    find_doctor,
    find_nurse,
    find_pharmacist,
    find_admin,
    log_action,
    recent_audit_log,
    recent_failed_logins,
    get_clinic_settings,
    all_files,
    all_doctors,
    all_nurses,
    all_pharmacists,
    active_doctors,
    active_nurses,
    active_pharmacists,
    create_staff,
    update_staff,
    set_staff_active,
    generate_employee_number,
    find_staff_by_employee_number,
    active_files,
    recent_handover_notes,
    latest_handover_note,
    checklist_for,
    open_requests,
    record_vitals_reading,
    vitals_history,
    latest_vitals_flags,
    migrate_schema,
    seed_medications,
    all_medications,
    find_medication,
    prescriptions_for,
    recent_administrations,
    all_training_examples,
    training_examples_as_tuples,
    add_training_example,
    delete_training_example,
    all_products,
    find_product,
    low_stock_products,
    expiring_soon_products,
    adjust_product_stock,
    delete_product,
    all_appointments,
    upcoming_appointments,
    todays_appointments,
    find_appointment,
    set_appointment_status,
    appointments_on,
    appointment_counts_for_month,
    EXPIRY_WARNING_DAYS,
    APPOINTMENT_SCHEDULED,
    APPOINTMENT_COMPLETED,
    APPOINTMENT_CANCELLED,
    APPOINTMENT_NO_SHOW,
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
from ml.medication_model import (
    predict_medications,
    retrain as retrain_medication_model,
    TRAINING_DATA as MEDICATION_TRAINING_DATA,
    DISCLAIMER as MEDICATION_DISCLAIMER,
)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-me"  # replace with a real secret in production
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "clinic.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
with app.app_context():
    db.create_all()
    migrate_schema()
    seed_medications()
    retrain_medication_model(training_examples_as_tuples())


@app.before_request
def _apply_clinic_settings():
    # Session timeout is admin-configurable (Settings > System > Security),
    # so it's read fresh each request rather than fixed at startup.
    settings = get_clinic_settings()
    app.permanent_session_lifetime = timedelta(minutes=settings.session_timeout_minutes)


@app.context_processor
def _inject_clinic_name():
    return {"clinic_name": get_clinic_settings().clinic_name}


# -------------------- Validation helpers --------------------

def is_valid_id_number(value: str) -> bool:
    return bool(value) and value.isdigit() and len(value) == 13


def is_valid_username(value: str) -> bool:
    return bool(value) and value.isdigit() and len(value) == 6


def is_valid_pin(value: str) -> bool:
    return bool(value) and value.isdigit() and len(value) == 4


_SEQUENTIAL_PINS = {
    "".join(str((start + i) % 10) for i in range(4)) for start in range(10)
} | {
    "".join(str((start - i) % 10) for i in range(4)) for start in range(10)
}


def is_weak_pin(value: str) -> bool:
    """Reject obviously-guessable 4-digit PINs: all-same-digit or a simple
    ascending/descending run (0123, 4321, 9876, ...)."""
    if len(set(value)) == 1:
        return True
    return value in _SEQUENTIAL_PINS


def current_doctor() -> Doctor | None:
    username = session.get("doctor_username")
    if not username:
        return None
    doctor = find_doctor(username)
    return doctor if doctor and doctor.is_active else None


def current_nurse() -> Nurse | None:
    username = session.get("nurse_username")
    if not username:
        return None
    nurse = find_nurse(username)
    return nurse if nurse and nurse.is_active else None


def current_pharmacist() -> Pharmacist | None:
    username = session.get("pharmacist_username")
    if not username:
        return None
    pharmacist = find_pharmacist(username)
    return pharmacist if pharmacist and pharmacist.is_active else None


def check_lockout(role: str, username: str) -> str | None:
    """Return a flash-ready error message if this username is currently
    locked out from repeated failed logins, else None."""
    settings = get_clinic_settings()
    if recent_failed_logins(role, username, settings.login_lockout_window_minutes) >= settings.login_lockout_threshold:
        return f"Too many failed attempts. Try again in {settings.login_lockout_window_minutes} minutes."
    return None


def current_admin() -> Admin | None:
    username = session.get("admin_username")
    if not username:
        return None
    return find_admin(username)


# -------------------- Admin auth --------------------

@app.route("/admin/auth")
def admin_auth():
    if current_admin():
        return redirect(url_for("admin_settings_page"))
    tab = request.args.get("tab", "login")
    return render_template("admin_auth.html", tab=tab)


@app.route("/admin/login", methods=["POST"])
def admin_login():
    username = request.form.get("username", "").strip()
    pin = request.form.get("pin", "").strip()

    if not is_valid_username(username) or not is_valid_pin(pin):
        flash("Enter a 6-digit username and 4-digit PIN.", "error")
        return redirect(url_for("admin_auth", tab="login"))

    lockout_msg = check_lockout("admin", username)
    if lockout_msg:
        flash(lockout_msg, "error")
        return redirect(url_for("admin_auth", tab="login"))

    admin_user = find_admin(username)
    if admin_user is None or admin_user.pin != pin:
        log_action("admin", username, "login_failed")
        flash("Invalid credentials.", "error")
        return redirect(url_for("admin_auth", tab="login"))

    session.permanent = True
    session["admin_username"] = admin_user.username
    log_action("admin", admin_user.username, "login")
    return redirect(url_for("admin_settings_page"))


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
    elif is_weak_pin(pin):
        errors.append("Choose a less predictable PIN — not all the same digit or a simple run like 1234.")

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


# -------------------- Theme --------------------

@app.route("/theme/toggle")
def toggle_theme():
    session["theme"] = "light" if session.get("theme", "light") == "dark" else "dark"
    return redirect(request.referrer or url_for("home"))


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
    known_labels = sorted(set(MEDICATION_TRAINING_DATA.keys()) | {l for l, _ in training_examples_as_tuples()})
    products = all_products()
    low_stock_ids = {p.id for p in low_stock_products()}
    expiring_ids = {p.id for p in expiring_soon_products()}
    return render_template(
        "admin.html", tab=tab, files=all_files(), medications=all_medications(), admin=admin_user,
        training_examples=all_training_examples(), medication_labels=known_labels,
        builtin_example_count=sum(len(v) for v in MEDICATION_TRAINING_DATA.values()),
        products=products, low_stock_ids=low_stock_ids, expiring_ids=expiring_ids,
        expiry_warning_days=EXPIRY_WARNING_DAYS, today=date.today(),
        doctors=active_doctors(),
    )


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
    admin_user = current_admin()
    log_action("admin", admin_user.username, "patient_registered", f"{full_name} ({id_number})")

    scheduled_raw = request.form.get("appt_scheduled_at", "").strip()
    if scheduled_raw:
        try:
            scheduled_at = datetime.strptime(scheduled_raw, "%Y-%m-%dT%H:%M")
        except ValueError:
            flash("Patient registered, but the appointment date/time was invalid — schedule it from Appointments.", "warning")
            return redirect(url_for("admin", tab="list"))

        db.session.add(Appointment(
            patient_id=id_number,
            doctor_username=request.form.get("appt_doctor_username", "").strip() or None,
            scheduled_at=scheduled_at,
            reason=request.form.get("appt_reason", "").strip(),
            created_by=admin_user.username,
        ))
        db.session.commit()
        log_action("admin", admin_user.username, "appointment_scheduled", f"{id_number} at {scheduled_at.strftime('%Y-%m-%d %H:%M')}")
        flash(f"Patient registered and appointment scheduled for {scheduled_at.strftime('%b %d, %H:%M')}.", "success")
        return redirect(url_for("admin", tab="list"))

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


@app.route("/admin/medication-training/add", methods=["POST"])
def admin_add_training_example():
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    label = request.form.get("label", "").strip()
    text = request.form.get("text", "").strip()
    if not label or not text:
        flash("Enter both a medication label and example text.", "error")
        return redirect(url_for("admin", tab="training"))

    add_training_example(label, text, admin_user.username)
    retrain_medication_model(training_examples_as_tuples())
    log_action("admin", admin_user.username, "training_example_added", label)
    flash("Training example added — the medication model has been retrained.", "success")
    return redirect(url_for("admin", tab="training"))


@app.route("/admin/medication-training/upload", methods=["POST"])
def admin_upload_training_data():
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    upload = request.files.get("csv_file")
    if not upload or not upload.filename:
        flash("Choose a CSV file to upload.", "error")
        return redirect(url_for("admin", tab="training"))

    try:
        content = upload.stream.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        flash("Could not read that file — save it as UTF-8 CSV and try again.", "error")
        return redirect(url_for("admin", tab="training"))

    # Skip any blank leading lines, then sniff the delimiter (Excel exports
    # often use ";" instead of ",") rather than assuming comma.
    lines = content.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        flash("That CSV file looks empty.", "error")
        return redirect(url_for("admin", tab="training"))

    sample = "\n".join(lines[:5])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel  # comma-delimited fallback

    rows = list(csv.reader(lines, dialect))
    header = [h.strip().strip('"').lower() for h in rows[0]] if rows else []
    if "label" not in header or "text" not in header:
        flash(
            f"CSV must have 'label' and 'text' columns — found: {', '.join(header) or '(no columns detected)'}.",
            "error",
        )
        return redirect(url_for("admin", tab="training"))

    label_idx = header.index("label")
    text_idx = header.index("text")
    added = 0
    for row in rows[1:]:
        if len(row) <= max(label_idx, text_idx):
            continue
        label = row[label_idx].strip()
        text = row[text_idx].strip()
        if label and text:
            db.session.add(MedicationTrainingExample(label=label, text=text, added_by=admin_user.username))
            added += 1
    db.session.commit()

    if added == 0:
        flash("No valid rows found in that CSV.", "warning")
        return redirect(url_for("admin", tab="training"))

    retrain_medication_model(training_examples_as_tuples())
    log_action("admin", admin_user.username, "training_data_uploaded", f"{added} examples")
    flash(f"Added {added} training examples and retrained the medication model.", "success")
    return redirect(url_for("admin", tab="training"))


@app.route("/admin/medication-training/<int:example_id>/delete", methods=["POST"])
def admin_delete_training_example(example_id):
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    delete_training_example(example_id)
    retrain_medication_model(training_examples_as_tuples())
    log_action("admin", admin_user.username, "training_example_deleted", str(example_id))
    flash("Training example removed and the medication model retrained.", "success")
    return redirect(url_for("admin", tab="training"))


@app.route("/admin/products/add", methods=["POST"])
def admin_add_product():
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip()
    unit = request.form.get("unit", "").strip()
    expiry_raw = request.form.get("expiry_date", "").strip()

    if not name:
        flash("Enter a product name.", "error")
        return redirect(url_for("admin", tab="products"))

    try:
        quantity = int(request.form.get("quantity", "0").strip() or 0)
        reorder_level = int(request.form.get("reorder_level", "0").strip() or 0)
    except ValueError:
        flash("Quantity and reorder level must be whole numbers.", "error")
        return redirect(url_for("admin", tab="products"))

    expiry_date = None
    if expiry_raw:
        try:
            expiry_date = datetime.strptime(expiry_raw, "%Y-%m-%d").date()
        except ValueError:
            flash("Enter a valid expiry date.", "error")
            return redirect(url_for("admin", tab="products"))

    db.session.add(Product(
        name=name, category=category, quantity=quantity, unit=unit,
        reorder_level=reorder_level, expiry_date=expiry_date, added_by=admin_user.username,
    ))
    db.session.commit()
    log_action("admin", admin_user.username, "product_added", name)
    flash(f"{name} added to inventory.", "success")
    return redirect(url_for("admin", tab="products"))


@app.route("/admin/products/<int:product_id>/adjust", methods=["POST"])
def admin_adjust_product(product_id):
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    try:
        change = int(request.form.get("change", "0").strip())
    except ValueError:
        flash("Enter a whole number to adjust stock by.", "error")
        return redirect(url_for("admin", tab="products"))

    product = adjust_product_stock(product_id, change)
    if product is None:
        flash("Product not found.", "error")
        return redirect(url_for("admin", tab="products"))

    log_action("admin", admin_user.username, "product_stock_adjusted", f"{product.name} ({change:+d} -> {product.quantity})")
    flash(f"{product.name} stock updated to {product.quantity}.", "success")
    return redirect(url_for("admin", tab="products"))


@app.route("/admin/products/<int:product_id>/delete", methods=["POST"])
def admin_delete_product(product_id):
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    product = find_product(product_id)
    name = product.name if product else "Product"
    delete_product(product_id)
    log_action("admin", admin_user.username, "product_deleted", name)
    flash(f"{name} removed from inventory.", "success")
    return redirect(url_for("admin", tab="products"))


# -------------------- Appointments --------------------

@app.route("/admin/appointments")
def admin_appointments():
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    today = date.today()

    month_param = request.args.get("month", "")
    try:
        view_year, view_month_num = (int(part) for part in month_param.split("-"))
        view_month = date(view_year, view_month_num, 1)
    except (ValueError, TypeError):
        view_month = today.replace(day=1)

    day_param = request.args.get("day", "")
    try:
        selected_day = datetime.strptime(day_param, "%Y-%m-%d").date()
    except ValueError:
        selected_day = today if view_month == today.replace(day=1) else view_month

    counts = appointment_counts_for_month(view_month.year, view_month.month)
    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(view_month.year, view_month.month):
        weeks.append([
            {
                "date": d,
                "in_month": d.month == view_month.month,
                "count": counts.get(d, 0),
                "is_today": d == today,
                "is_selected": d == selected_day,
            }
            for d in week
        ])

    prev_month = (view_month - timedelta(days=1)).replace(day=1)
    next_month = (view_month.replace(day=28) + timedelta(days=4)).replace(day=1)

    return render_template(
        "appointments.html", admin=admin_user,
        weeks=weeks, view_month=view_month, prev_month=prev_month, next_month=next_month,
        today=today, selected_day=selected_day, day_appointments=appointments_on(selected_day),
        patients=[f.patient for f in all_files()], doctors=active_doctors(),
        preselect_patient_id=request.args.get("patient_id", ""),
    )


@app.route("/admin/appointments/add", methods=["POST"])
def admin_add_appointment():
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    patient_id = request.form.get("patient_id", "").strip()
    doctor_username = request.form.get("doctor_username", "").strip()
    scheduled_raw = request.form.get("scheduled_at", "").strip()
    reason = request.form.get("reason", "").strip()

    if not patient_id or not find_file(patient_id):
        flash("Choose a patient.", "error")
        return redirect(url_for("admin_appointments"))

    try:
        scheduled_at = datetime.strptime(scheduled_raw, "%Y-%m-%dT%H:%M")
    except ValueError:
        flash("Choose a valid date and time.", "error")
        return redirect(url_for("admin_appointments"))

    db.session.add(Appointment(
        patient_id=patient_id,
        doctor_username=doctor_username or None,
        scheduled_at=scheduled_at,
        reason=reason,
        created_by=admin_user.username,
    ))
    db.session.commit()
    log_action("admin", admin_user.username, "appointment_scheduled", f"{patient_id} at {scheduled_at.strftime('%Y-%m-%d %H:%M')}")
    flash("Appointment scheduled.", "success")
    return redirect(url_for("admin_appointments"))


@app.route("/admin/appointments/<int:appointment_id>/status", methods=["POST"])
def admin_update_appointment_status(appointment_id):
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    status = request.form.get("status", "")
    if status not in (APPOINTMENT_COMPLETED, APPOINTMENT_CANCELLED, APPOINTMENT_NO_SHOW, APPOINTMENT_SCHEDULED):
        flash("Unknown appointment status.", "error")
        return redirect(url_for("admin_appointments"))

    appointment = set_appointment_status(appointment_id, status)
    if appointment is None:
        flash("Appointment not found.", "error")
        return redirect(url_for("admin_appointments"))

    log_action("admin", admin_user.username, "appointment_status_changed", f"#{appointment_id} -> {status}")
    flash("Appointment updated.", "success")
    return redirect(url_for("admin_appointments"))


# -------------------- Staff auth (shared: doctor / nurse / pharmacist) --------------------

STAFF_DASHBOARD_ENDPOINT = {"doctor": "doctor_panel", "nurse": "nursing", "pharmacist": "pharmacist"}


def current_staff_role():
    """Which staff role (if any) is currently signed in, and their record."""
    if session.get("doctor_username"):
        return "doctor", current_doctor()
    if session.get("nurse_username"):
        return "nurse", current_nurse()
    if session.get("pharmacist_username"):
        return "pharmacist", current_pharmacist()
    return None, None


def check_staff_lockout(employee_number: str) -> str | None:
    """Lockout check that doesn't yet know which role this employee number
    belongs to — sums failed attempts logged under any staff role."""
    settings = get_clinic_settings()
    total_failed = sum(
        recent_failed_logins(role, employee_number, settings.login_lockout_window_minutes)
        for role in ("doctor", "nurse", "pharmacist")
    )
    if total_failed >= settings.login_lockout_threshold:
        return f"Too many failed attempts. Try again in {settings.login_lockout_window_minutes} minutes."
    return None


@app.route("/staff")
def staff_auth():
    role, staff = current_staff_role()
    if staff:
        return redirect(url_for(STAFF_DASHBOARD_ENDPOINT[role]))
    return render_template("staff_auth.html")


@app.route("/staff/login", methods=["POST"])
def staff_login():
    employee_number = request.form.get("employee_number", "").strip()
    pin = request.form.get("pin", "").strip()

    if not is_valid_username(employee_number) or not is_valid_pin(pin):
        flash("Enter a 6-digit employee number and 4-digit PIN.", "error")
        return redirect(url_for("staff_auth"))

    lockout_msg = check_staff_lockout(employee_number)
    if lockout_msg:
        flash(lockout_msg, "error")
        return redirect(url_for("staff_auth"))

    role, staff = find_staff_by_employee_number(employee_number)
    if staff is None or staff.pin != pin:
        # Log under whichever role owns the number, or "staff" if it belongs to no one.
        log_action(role or "staff", employee_number, "login_failed")
        flash("Invalid credentials.", "error")
        return redirect(url_for("staff_auth"))
    if not staff.is_active:
        flash("This account has been deactivated. Contact an admin.", "error")
        return redirect(url_for("staff_auth"))

    session.permanent = True
    session[f"{role}_username"] = staff.username
    log_action(role, staff.username, "login")
    return redirect(url_for(STAFF_DASHBOARD_ENDPOINT[role]))


@app.route("/staff/logout")
def staff_logout():
    role, staff = current_staff_role()
    if staff:
        log_action(role, staff.username, "logout")
    session.pop("doctor_username", None)
    session.pop("nurse_username", None)
    session.pop("pharmacist_username", None)
    return redirect(url_for("staff_auth"))


@app.route("/doctor/panel")
def doctor_panel():
    doctor = current_doctor()
    if not doctor:
        return redirect(url_for("staff_auth"))
    return render_template("doctor_panel.html", doctor=doctor, files=all_files())


@app.route("/doctor/patient/<id_number>", methods=["GET", "POST"])
def patient_detail(id_number):
    doctor = current_doctor()
    if not doctor:
        return redirect(url_for("staff_auth"))

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
    pharmacist_user = current_pharmacist()
    if not pharmacist_user:
        return redirect(url_for("staff_auth"))

    evaluated = [f for f in all_files() if f.status == STATUS_EVALUATED]

    suggest_for = request.args.get("suggest", "")
    medication_suggestions = None
    if suggest_for:
        target = next((f for f in evaluated if f.patient.id_number == suggest_for), None)
        if target is not None:
            medication_suggestions = predict_medications(target.doctor_notes)

    return render_template(
        "pharmacist.html", pharmacist=pharmacist_user, files=evaluated,
        suggest_for=suggest_for, medication_suggestions=medication_suggestions,
        medication_disclaimer=MEDICATION_DISCLAIMER,
    )


@app.route("/pharmacist/dispense/<id_number>", methods=["POST"])
def dispense(id_number):
    pharmacist_user = current_pharmacist()
    if not pharmacist_user:
        return redirect(url_for("staff_auth"))

    file = find_file(id_number)
    if file:
        file.status = STATUS_DISPENSED
        file.pharmacist_notes = f"Medication dispensed on {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        db.session.commit()
        log_action("pharmacist", pharmacist_user.username, "dispensed", file.patient.full_name)
        flash("Medication dispensed successfully.", "success")
    return redirect(url_for("pharmacist"))


# -------------------- Nursing --------------------

@app.route("/nursing")
def nursing():
    nurse = current_nurse()
    if not nurse:
        return redirect(url_for("staff_auth"))
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
        return redirect(url_for("staff_auth"))

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
        return redirect(url_for("staff_auth"))

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
        return redirect(url_for("staff_auth"))

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
        return redirect(url_for("staff_auth"))

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
        return redirect(url_for("staff_auth"))

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
        return redirect(url_for("staff_auth"))

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
        return redirect(url_for("staff_auth"))

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

def _spark_points(values, width=100, height=32, pad=3):
    """SVG polyline points for a small sparkline, normalized to width x height."""
    if not values:
        return ""
    n = len(values)
    max_v = max(values) or 1
    step = (width - 2 * pad) / max(n - 1, 1)
    points = []
    for i, v in enumerate(values):
        x = pad + i * step
        y = height - pad - (v / max_v) * (height - 2 * pad)
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def _build_dashboard_context():
    files = all_files()
    doctors = all_doctors()
    prescriptions = Prescription.query.all()

    total = len(files)
    registered = sum(1 for f in files if f.status == STATUS_REGISTERED)
    evaluated = sum(1 for f in files if f.status == STATUS_EVALUATED)
    dispensed = sum(1 for f in files if f.status == STATUS_DISPENSED)
    urgent = sum(1 for f in files if f.priority == PRIORITY_URGENT)

    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday_status_counts = [{"registered": 0, "evaluated": 0, "dispensed": 0} for _ in range(7)]
    for f in files:
        weekday_status_counts[f.registered_at.weekday()][f.status] += 1
    max_single = max(
        (weekday_status_counts[i][s] for i in range(7) for s in ("registered", "evaluated", "dispensed")),
        default=0,
    ) or 1
    weekday_status_data = [
        {
            "label": weekday_labels[i],
            "registered": weekday_status_counts[i]["registered"],
            "registered_pct": round(weekday_status_counts[i]["registered"] / max_single * 100),
            "evaluated": weekday_status_counts[i]["evaluated"],
            "evaluated_pct": round(weekday_status_counts[i]["evaluated"] / max_single * 100),
            "dispensed": weekday_status_counts[i]["dispensed"],
            "dispensed_pct": round(weekday_status_counts[i]["dispensed"] / max_single * 100),
        }
        for i in range(7)
    ]

    today = date.today()
    days = [today - timedelta(days=i) for i in range(27, -1, -1)]
    counts_by_day = {d: 0 for d in days}
    for f in files:
        d = f.registered_at.date()
        if d in counts_by_day:
            counts_by_day[d] += 1

    trend_points = _spark_points([counts_by_day[d] for d in days], width=560, height=140, pad=6)
    trend_labels = [days[0].strftime("%b %d"), days[len(days) // 2].strftime("%b %d"), days[-1].strftime("%b %d")]

    last7_days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    last7_counts = [counts_by_day[d] for d in last7_days]
    today_count = counts_by_day[today]
    yesterday_count = counts_by_day[today - timedelta(days=1)]
    total_spark = _spark_points(last7_counts)

    pending_prescriptions = sum(1 for p in prescriptions if p.administrations.count() == 0)
    rx_counts_by_day = {d: 0 for d in last7_days}
    for p in prescriptions:
        d = p.prescribed_at.date()
        if d in rx_counts_by_day:
            rx_counts_by_day[d] += 1
    rx_spark = _spark_points([rx_counts_by_day[d] for d in last7_days])

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

    now = datetime.now()
    queue_raw = sorted(
        (f for f in files if f.status != STATUS_DISPENSED),
        key=lambda f: (f.priority != PRIORITY_URGENT, f.registered_at),
    )[:6]
    queue = [
        dict(
            file=f,
            waiting_minutes=round((now - f.registered_at).total_seconds() / 60) if f.status == STATUS_REGISTERED else None,
        )
        for f in queue_raw
    ]

    recent_activity = recent_audit_log(limit=6)

    def pct(n):
        return round((n / total) * 100, 1) if total else 0.0

    status_pct = {"registered": pct(registered), "evaluated": pct(evaluated), "dispensed": pct(dispensed)}

    cal_counts = appointment_counts_for_month(today.year, today.month)
    cal_weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(today.year, today.month):
        cal_weeks.append([
            {
                "date": d,
                "in_month": d.month == today.month,
                "count": cal_counts.get(d, 0),
                "is_today": d == today,
            }
            for d in week
        ])
    cal_month_start = today.replace(day=1)
    cal_prev_month = (cal_month_start - timedelta(days=1)).replace(day=1)
    cal_next_month = (cal_month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    upcoming_preview = upcoming_appointments()[:6]

    return dict(
        total=total, registered=registered, evaluated=evaluated,
        dispensed=dispensed, urgent=urgent, status_pct=status_pct,
        weekday_status_data=weekday_status_data,
        trend_points=trend_points, trend_labels=trend_labels,
        today_count=today_count, yesterday_count=yesterday_count, total_spark=total_spark,
        pending_prescriptions=pending_prescriptions, rx_spark=rx_spark,
        staff=staff, queue=queue, recent_activity=recent_activity,
        cal_weeks=cal_weeks, cal_month=today, cal_prev_month=cal_prev_month, cal_next_month=cal_next_month,
        upcoming_preview=upcoming_preview,
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


# -------------------- Settings --------------------
# A fixed taxonomy of settings categories. Most leaves map to real,
# working settings in this app; leaves with no backing feature yet render
# an honest "not available in this version" notice rather than a fake form.

SETTINGS_SECTIONS = [
    ("Clinic", [("clinic-general", "General"), ("clinic-operations", "Operations"), ("clinic-contact", "Contact")]),
    ("Staff", [("staff-users", "Users"), ("staff-roles", "Roles"), ("staff-schedules", "Schedules")]),
    ("Patients", [("patients-registration", "Registration"), ("patients-portal", "Portal"), ("patients-privacy", "Privacy")]),
    ("Clinical", [("clinical-vitals", "Vital Signs"), ("clinical-diagnosis", "Diagnosis"), ("clinical-prescriptions", "Prescriptions")]),
    ("Pharmacy", [("pharmacy-inventory", "Inventory"), ("pharmacy-dispensing", "Dispensing"), ("pharmacy-suppliers", "Suppliers")]),
    ("Billing", [("billing-payments", "Payments"), ("billing-insurance", "Insurance"), ("billing-pricing", "Pricing")]),
    ("System", [("system-security", "Security"), ("system-backup", "Backup"), ("system-integrations", "Integrations"), ("system-aiml", "AI/ML")]),
    ("Compliance", [("compliance-regulations", "Regulations"), ("compliance-audit", "Audit"), ("compliance-reports", "Reports")]),
]
SETTINGS_SLUGS = {slug for _, items in SETTINGS_SECTIONS for slug, _ in items}


@app.route("/admin/settings")
def admin_settings_page():
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    section = request.args.get("section", "clinic-general")
    if section not in SETTINGS_SLUGS:
        section = "clinic-general"

    return render_template(
        "settings.html", admin=admin_user, clinic_settings=get_clinic_settings(),
        sections=SETTINGS_SECTIONS, section=section,
        staff_doctors=all_doctors(), staff_nurses=all_nurses(), staff_pharmacists=all_pharmacists(),
        pending_training_count=len(all_training_examples()),
        low_stock_count=len(low_stock_products()), product_count=len(all_products()),
    )


@app.route("/admin/settings/account", methods=["POST"])
def admin_update_account():
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    current_pin = request.form.get("current_pin", "").strip()
    if current_pin != admin_user.pin:
        flash("Current PIN is incorrect.", "error")
        return redirect(url_for("admin_settings_page", section="staff-users"))

    full_name = request.form.get("full_name", "").strip()
    new_pin = request.form.get("new_pin", "").strip()

    if not full_name:
        flash("Enter your full name.", "error")
        return redirect(url_for("admin_settings_page", section="staff-users"))
    if new_pin and not is_valid_pin(new_pin):
        flash("New PIN must be exactly 4 digits.", "error")
        return redirect(url_for("admin_settings_page", section="staff-users"))
    if new_pin and is_weak_pin(new_pin):
        flash("Choose a less predictable PIN — not all the same digit or a simple run like 1234.", "error")
        return redirect(url_for("admin_settings_page", section="staff-users"))

    admin_user.full_name = full_name
    if new_pin:
        admin_user.pin = new_pin
    db.session.commit()
    log_action("admin", admin_user.username, "account_updated")
    flash("Account settings updated.", "success")
    return redirect(url_for("admin_settings_page", section="staff-users"))


@app.route("/admin/settings/clinic", methods=["POST"])
def admin_update_clinic_settings():
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    def parse_number(name):
        try:
            return float(request.form.get(name, "").strip())
        except ValueError:
            return None

    field_names = [
        "temp_low", "temp_high", "pulse_low", "pulse_high",
        "bp_systolic_low", "bp_systolic_high", "bp_diastolic_low", "bp_diastolic_high",
    ]
    values = {name: parse_number(name) for name in field_names}

    if any(v is None for v in values.values()):
        flash("Enter valid numbers for every threshold.", "error")
        return redirect(url_for("admin_settings_page", section="clinical-vitals"))
    if values["temp_low"] >= values["temp_high"]:
        flash("Temperature low must be less than high.", "error")
        return redirect(url_for("admin_settings_page", section="clinical-vitals"))
    if values["pulse_low"] >= values["pulse_high"]:
        flash("Pulse low must be less than high.", "error")
        return redirect(url_for("admin_settings_page", section="clinical-vitals"))
    if values["bp_systolic_low"] >= values["bp_systolic_high"]:
        flash("Systolic BP low must be less than high.", "error")
        return redirect(url_for("admin_settings_page", section="clinical-vitals"))
    if values["bp_diastolic_low"] >= values["bp_diastolic_high"]:
        flash("Diastolic BP low must be less than high.", "error")
        return redirect(url_for("admin_settings_page", section="clinical-vitals"))

    settings = get_clinic_settings()
    settings.temp_low = values["temp_low"]
    settings.temp_high = values["temp_high"]
    settings.pulse_low = int(values["pulse_low"])
    settings.pulse_high = int(values["pulse_high"])
    settings.bp_systolic_low = int(values["bp_systolic_low"])
    settings.bp_systolic_high = int(values["bp_systolic_high"])
    settings.bp_diastolic_low = int(values["bp_diastolic_low"])
    settings.bp_diastolic_high = int(values["bp_diastolic_high"])
    db.session.commit()
    log_action("admin", admin_user.username, "clinic_settings_updated")
    flash("Clinic vitals thresholds updated.", "success")
    return redirect(url_for("admin_settings_page", section="clinical-vitals"))


@app.route("/admin/settings/clinic-general", methods=["POST"])
def admin_update_clinic_general():
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    clinic_name = request.form.get("clinic_name", "").strip()
    if not clinic_name:
        flash("Enter a clinic name.", "error")
        return redirect(url_for("admin_settings_page", section="clinic-general"))

    settings = get_clinic_settings()
    settings.clinic_name = clinic_name
    db.session.commit()
    log_action("admin", admin_user.username, "clinic_name_updated", clinic_name)
    flash("Clinic name updated.", "success")
    return redirect(url_for("admin_settings_page", section="clinic-general"))


@app.route("/admin/settings/clinic-contact", methods=["POST"])
def admin_update_clinic_contact():
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    settings = get_clinic_settings()
    settings.clinic_phone = request.form.get("clinic_phone", "").strip()
    settings.clinic_address = request.form.get("clinic_address", "").strip()
    db.session.commit()
    log_action("admin", admin_user.username, "clinic_contact_updated")
    flash("Clinic contact details updated.", "success")
    return redirect(url_for("admin_settings_page", section="clinic-contact"))


@app.route("/admin/settings/security", methods=["POST"])
def admin_update_security():
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    try:
        minutes = int(request.form.get("session_timeout_minutes", "").strip())
        threshold = int(request.form.get("login_lockout_threshold", "").strip())
        window = int(request.form.get("login_lockout_window_minutes", "").strip())
        if minutes < 1 or threshold < 1 or window < 1:
            raise ValueError
    except ValueError:
        flash("Enter whole numbers of at least 1 for every security setting.", "error")
        return redirect(url_for("admin_settings_page", section="system-security"))

    settings = get_clinic_settings()
    settings.session_timeout_minutes = minutes
    settings.login_lockout_threshold = threshold
    settings.login_lockout_window_minutes = window
    db.session.commit()
    log_action("admin", admin_user.username, "security_settings_updated", f"timeout={minutes}m lockout={threshold}/{window}m")
    flash("Security settings updated.", "success")
    return redirect(url_for("admin_settings_page", section="system-security"))


@app.route("/admin/staff/add", methods=["POST"])
def admin_add_staff():
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    role = request.form.get("role", "")
    full_name = request.form.get("full_name", "").strip()
    pin = request.form.get("pin", "").strip()

    if role not in ("doctor", "nurse", "pharmacist"):
        flash("Choose a valid role.", "error")
        return redirect(url_for("admin_settings_page", section="staff-users"))

    errors = []
    if not full_name:
        errors.append("Enter a full name.")
    if not is_valid_pin(pin):
        errors.append("PIN must be exactly 4 digits.")
    elif is_weak_pin(pin):
        errors.append("Choose a less predictable PIN — not all the same digit or a simple run like 1234.")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("admin_settings_page", section="staff-users"))

    employee_number = generate_employee_number()
    create_staff(role, employee_number, pin, full_name)
    log_action("admin", admin_user.username, "staff_added", f"{role} {full_name} (#{employee_number})")
    flash(f"{full_name} added as a {role}. Employee number: {employee_number} — share this and the PIN with them.", "success")
    return redirect(url_for("admin_settings_page", section="staff-users"))


@app.route("/admin/staff/<role>/<username>/update", methods=["POST"])
def admin_update_staff(role, username):
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    if role not in ("doctor", "nurse", "pharmacist"):
        flash("Unknown role.", "error")
        return redirect(url_for("admin_settings_page", section="staff-users"))

    full_name = request.form.get("full_name", "").strip()
    new_pin = request.form.get("new_pin", "").strip()

    if not full_name:
        flash("Enter a full name.", "error")
        return redirect(url_for("admin_settings_page", section="staff-users"))
    if new_pin and not is_valid_pin(new_pin):
        flash("New PIN must be exactly 4 digits.", "error")
        return redirect(url_for("admin_settings_page", section="staff-users"))
    if new_pin and is_weak_pin(new_pin):
        flash("Choose a less predictable PIN — not all the same digit or a simple run like 1234.", "error")
        return redirect(url_for("admin_settings_page", section="staff-users"))

    staff = update_staff(role, username, full_name=full_name, new_pin=new_pin or None)
    if staff is None:
        flash("Staff member not found.", "error")
        return redirect(url_for("admin_settings_page", section="staff-users"))

    log_action("admin", admin_user.username, "staff_updated", f"{role} #{username}")
    flash(f"{full_name} updated.", "success")
    return redirect(url_for("admin_settings_page", section="staff-users"))


@app.route("/admin/staff/<role>/<username>/toggle-active", methods=["POST"])
def admin_toggle_staff_active(role, username):
    admin_user = current_admin()
    if not admin_user:
        return redirect(url_for("admin_auth"))

    if role not in ("doctor", "nurse", "pharmacist"):
        flash("Unknown role.", "error")
        return redirect(url_for("admin_settings_page", section="staff-users"))

    finder = {"doctor": find_doctor, "nurse": find_nurse, "pharmacist": find_pharmacist}[role]
    staff = finder(username)
    if staff is None:
        flash("Staff member not found.", "error")
        return redirect(url_for("admin_settings_page", section="staff-users"))

    new_state = not staff.is_active
    set_staff_active(role, username, new_state)
    log_action("admin", admin_user.username, "staff_activated" if new_state else "staff_deactivated", f"{role} #{username}")
    flash(f"{staff.full_name} {'reactivated' if new_state else 'deactivated'}.", "success")
    return redirect(url_for("admin_settings_page", section="staff-users"))


if __name__ == "__main__":
    app.run(debug=True)