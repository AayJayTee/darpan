#Import necessary libraries
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Project, Log
from forms import LoginForm, ProjectForm
import datetime
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from pytz import timezone

from io import BytesIO
from flask import send_file
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from flask_migrate import Migrate
from collections import Counter, defaultdict
import calendar
import os

import uuid
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage

# Initialize Flask app and database
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'site.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

#Flas-Migrate for database migrations
migrate = Migrate(app, db)


UPLOAD_FOLDER = os.path.join(app.instance_path, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def save_pdf(file):
    if file and file.filename and file.filename.endswith('.pdf'):
        filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        print(f"Saving file to: {filepath}")  # Debug line
        file.save(filepath)
        return filename
    return None


# Initialize Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def log_action(user, action):
    tz = timezone('Asia/Kolkata')
    now = datetime.now(tz)
    log = Log(user_id=user.id, action=action, timestamp=now)
    db.session.add(log)
    db.session.commit()

# Route for the login page
@app.route('/', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            log_action(user, "User logged in")
            flash(f"Welcome, {user.username}!", "success")
            return redirect(url_for('home'))
        flash('Invalid username or password', 'danger')
    return render_template('login.html', form=form)

# Route for the project search
# AJAX search route for dynamic filtering
@app.route('/ajax_search_projects')
@login_required
def ajax_search_projects():
    query = request.args.get('query', '').strip()
    if query:
        projects = Project.query.filter(
            (Project.serial_no.ilike(f"%{query}%")) |
            (Project.title.ilike(f"%{query}%"))
        ).all()
    else:
        projects = Project.query.all()

    return render_template('partials/project_table_body.html', projects=projects)

# Route for the dashboard
# Dashboard View - List all projects
@app.route('/dashboard')
@login_required
def dashboard():
    query = Project.query
    column = request.args.get('column', '')
    value = request.args.get('value', '').strip()
    cost_min = request.args.get('cost_min', '').strip()
    cost_max = request.args.get('cost_max', '').strip()

    if column and (value or (column == 'cost_lakhs' and (cost_min or cost_max))):
        if column == 'serial_no':
            query = query.filter(Project.serial_no.ilike(f"%{value}%"))
        elif column == 'title':
            query = query.filter(Project.title.ilike(f"%{value}%"))
        elif column == 'vertical':
            query = query.filter(Project.vertical.ilike(f"%{value}%"))
        elif column == 'academia':
            query = query.filter(Project.academia.ilike(f"%{value}%"))
        elif column == 'pi_name':
            query = query.filter(Project.pi_name.ilike(f"%{value}%"))
        elif column == 'coord_lab':
            query = query.filter(Project.coord_lab.ilike(f"%{value}%"))
        elif column == 'scientist':
            query = query.filter(Project.scientist.ilike(f"%{value}%"))
        elif column == 'cost_lakhs':
            try:
                if cost_min:
                    query = query.filter(Project.cost_lakhs >= float(cost_min))
                if cost_max:
                    query = query.filter(Project.cost_lakhs <= float(cost_max))
            except ValueError:
                pass
        elif column in ['sanctioned_date', 'original_pdc', 'revised_pdc']:
            try:
                date_value = datetime.strptime(value, "%Y-%m-%d").date()
                query = query.filter(getattr(Project, column) == date_value)
            except ValueError:
                pass
        elif column == 'administrative_status':
            query = query.filter(Project.administrative_status.ilike(f"%{value}%"))
        elif column == 'sanction_year':
            try:
                year = int(value)
                query = query.filter(db.extract('year', Project.sanctioned_date) == year)
            except ValueError:
                pass

    projects = query.order_by(db.cast(Project.serial_no, db.Integer)).all()

    # --- Reminder Logic ---
    today = datetime.today().date()
    soon = today + timedelta(days=14)

    # Approaching PDC deadline (not completed)
    approaching_pdc = [
        p for p in projects
        if p.revised_pdc and today <= p.revised_pdc <= soon and (not p.administrative_status or p.administrative_status.lower() != "completed")
    ]

    return render_template(
        'dashboard.html',
        projects=projects,
        user=current_user,
        now=datetime.now(),
        approaching_pdc=approaching_pdc
    )


@app.route('/home')
@login_required
def home():
    return render_template('home.html', user=current_user)

@app.route('/visualization')
@login_required
def visualization():
    projects = Project.query.all()

    # Administrative Status Pie Chart
    admin_status_counts = Counter([p.administrative_status for p in projects if p.administrative_status])

    # Projects Sanctioned Per Year
    sanction_years = [p.sanctioned_date.year for p in projects if p.sanctioned_date]
    year_counts = Counter(sanction_years)
    sorted_years = sorted(year_counts.keys())
    year_labels = [str(y) for y in sorted_years]
    year_values = [year_counts[y] for y in sorted_years]

    # Donut Chart Data (Projects per Vertical)
    vertical_counts = Counter([p.vertical for p in projects if p.vertical])

    # Donut Chart Data (Verticals per Institute) - using only the institute after the comma
    institute_verticals = defaultdict(set)
    for p in projects:
        if p.academia and p.vertical:
            # Extract institute after the first comma, or use the whole string if no comma
            if ',' in p.academia:
                institute = p.academia.split(',', 1)[1].strip()
            else:
                institute = p.academia.strip()
            institute_verticals[institute].add(p.vertical)
    institute_vertical_counts = {inst: len(verts) for inst, verts in institute_verticals.items()}
    
    # Cost vs Institute
    cost_vs_institute = defaultdict(float)
    for p in projects:
        if p.academia and p.cost_lakhs:
            # Extract institute after the first comma, or use the whole string if no comma
            if ',' in p.academia:
                institute = p.academia.split(',', 1)[1].strip()
            else:
                institute = p.academia.strip()
            try:
                cost_vs_institute[institute] += float(p.cost_lakhs)
            except ValueError:
                continue  # skip invalid values
    cost_institute_labels = list(cost_vs_institute.keys())
    cost_institute_values = [cost_vs_institute[k] for k in cost_institute_labels]

    # Cost vs Vertical (this was missing)
    cost_vs_vertical = defaultdict(float)
    for p in projects:
        if p.vertical and p.cost_lakhs:
            try:
                cost_vs_vertical[p.vertical] += float(p.cost_lakhs)
            except ValueError:
                continue
    cost_vertical_labels = list(cost_vs_vertical.keys())
    cost_vertical_values = [cost_vs_vertical[k] for k in cost_vertical_labels]

    # Monthly Sanctions by Vertical (Stacked Bar)
    monthly_vertical_counts = defaultdict(lambda: defaultdict(int))
    all_verticals = set()
    for p in projects:
        if p.sanctioned_date and p.vertical:
            month = p.sanctioned_date.strftime('%Y-%m')
            monthly_vertical_counts[month][p.vertical] += 1
            all_verticals.add(p.vertical)

    # Sort and prepare data
    stacked_labels = sorted(monthly_vertical_counts.keys())
    stacked_verticals = sorted(all_verticals)
    stacked_data = []
    for vertical in stacked_verticals:
        data = [monthly_vertical_counts[month].get(vertical, 0) for month in stacked_labels]
        stacked_data.append({'label': vertical, 'data': data})

    # --- Quarterly, Half-Yearly, Yearly Status Counts ---
    def get_financial_year(date):
        if date.month >= 4:
            return f"{date.year}-{str(date.year+1)[-2:]}"
        else:
            return f"{date.year-1}-{str(date.year)[-2:]}"

    def get_financial_quarter(date):
        fy = get_financial_year(date)
        if date.month in [4,5,6]:
            q = "Q1"
        elif date.month in [7,8,9]:
            q = "Q2"
        elif date.month in [10,11,12]:
            q = "Q3"
        else:
            q = "Q4"
        return f"{fy} {q}"

    def get_financial_half(date):
        fy = get_financial_year(date)
        if date.month >= 4 and date.month <= 9:
            h = "H1"
        else:
            h = "H2"
        return f"{fy} {h}"

    # 1. Collect all periods from all projects
    fy_set, fq_set, fh_set = set(), set(), set()
    for p in projects:
        if not p.sanctioned_date:
            continue
        fy_set.add(get_financial_year(p.sanctioned_date))
        fq_set.add(get_financial_quarter(p.sanctioned_date))
        fh_set.add(get_financial_half(p.sanctioned_date))
        closure_date = None
        if getattr(p, 'final_closure_date', None):
            closure_date = p.final_closure_date
        elif getattr(p, 'revised_pdc', None):
            closure_date = p.revised_pdc
        elif getattr(p, 'original_pdc', None):
            closure_date = p.original_pdc
        if closure_date:
            fy_set.add(get_financial_year(closure_date))
            fq_set.add(get_financial_quarter(closure_date))
            fh_set.add(get_financial_half(closure_date))

    # Sort periods
    year_labels_status = sorted(fy_set)
    quarter_labels = sorted(fq_set)
    half_labels = sorted(fh_set)

    # 2. For each period, count status
    status_period_counts = {
        'year': {fy: {'Open':0, 'Running':0, 'Closed':0} for fy in year_labels_status},
        'quarter': {fq: {'Open':0, 'Running':0, 'Closed':0} for fq in quarter_labels},
        'half': {fh: {'Open':0, 'Running':0, 'Closed':0} for fh in half_labels},
    }

    for p in projects:
        if not p.sanctioned_date:
            continue
        # Closure date
        closure_date = None
        if getattr(p, 'final_closure_date', None):
            closure_date = p.final_closure_date
        elif getattr(p, 'revised_pdc', None):
            closure_date = p.revised_pdc
        elif getattr(p, 'original_pdc', None):
            closure_date = p.original_pdc

        # For each period, assign status
        for fy in year_labels_status:
            fy_start = datetime.strptime(fy.split('-')[0] + '-04-01', '%Y-%m-%d').date()
            fy_end = datetime.strptime(str(int(fy.split('-')[0])+1) + '-03-31', '%Y-%m-%d').date()
            if fy_start <= p.sanctioned_date <= fy_end:
                status_period_counts['year'][fy]['Open'] += 1
            elif closure_date and fy_start <= closure_date <= fy_end:
                status_period_counts['year'][fy]['Closed'] += 1
            elif p.sanctioned_date < fy_start and (not closure_date or closure_date > fy_end):
                status_period_counts['year'][fy]['Running'] += 1

        for fq in quarter_labels:
            y, q = fq.split()
            y_start = int(y.split('-')[0])
            if q == "Q1":
                q_start = datetime(y_start, 4, 1).date()
                q_end = datetime(y_start, 6, 30).date()
            elif q == "Q2":
                q_start = datetime(y_start, 7, 1).date()
                q_end = datetime(y_start, 9, 30).date()
            elif q == "Q3":
                q_start = datetime(y_start, 10, 1).date()
                q_end = datetime(y_start, 12, 31).date()
            else: # Q4
                q_start = datetime(y_start+1, 1, 1).date()
                q_end = datetime(y_start+1, 3, 31).date()
            if q_start <= p.sanctioned_date <= q_end:
                status_period_counts['quarter'][fq]['Open'] += 1
            elif closure_date and q_start <= closure_date <= q_end:
                status_period_counts['quarter'][fq]['Closed'] += 1
            elif p.sanctioned_date < q_start and (not closure_date or closure_date > q_end):
                status_period_counts['quarter'][fq]['Running'] += 1

        for fh in half_labels:
            y, h = fh.split()
            y_start = int(y.split('-')[0])
            if h == "H1":
                h_start = datetime(y_start, 4, 1).date()
                h_end = datetime(y_start, 9, 30).date()
            else: # H2
                h_start = datetime(y_start, 10, 1).date()
                h_end = datetime(y_start+1, 3, 31).date()
            if h_start <= p.sanctioned_date <= h_end:
                status_period_counts['half'][fh]['Open'] += 1
            elif closure_date and h_start <= closure_date <= h_end:
                status_period_counts['half'][fh]['Closed'] += 1
            elif p.sanctioned_date < h_start and (not closure_date or closure_date > h_end):
                status_period_counts['half'][fh]['Running'] += 1

    # Prepare data for Chart.js
    quarter_data = {
        'Running': [status_period_counts['quarter'][q]['Running'] for q in quarter_labels],
        'Closed': [status_period_counts['quarter'][q]['Closed'] for q in quarter_labels],
        'Open': [status_period_counts['quarter'][q]['Open'] for q in quarter_labels],
    }
    half_data = {
        'Running': [status_period_counts['half'][h]['Running'] for h in half_labels],
        'Closed': [status_period_counts['half'][h]['Closed'] for h in half_labels],
        'Open': [status_period_counts['half'][h]['Open'] for h in half_labels],
    }
    year_data_status = {
        'Running': [status_period_counts['year'][y]['Running'] for y in year_labels_status],
        'Closed': [status_period_counts['year'][y]['Closed'] for y in year_labels_status],
        'Open': [status_period_counts['year'][y]['Open'] for y in year_labels_status],
    }

    # --- Average Project Duration by Sanction Year (in days) ---
    duration_by_year = {}
    for p in projects:
        if p.sanctioned_date:
            # Use final_closure_date if available, else revised_pdc if available
            end_date = None
            if p.final_closure_date:
                end_date = p.final_closure_date
            elif p.revised_pdc:
                end_date = p.revised_pdc
            # Only calculate if we have both dates
            if end_date:
                year = p.sanctioned_date.year
                duration = (end_date - p.sanctioned_date).days
                duration_by_year.setdefault(year, []).append(duration)
    avg_duration_labels = sorted([str(y) for y in duration_by_year.keys()])
    avg_duration_values = [
        round(sum(duration_by_year[int(y)]) / len(duration_by_year[int(y)]), 1)
        for y in avg_duration_labels
    ]

    # --- Project Status Breakdown by Vertical ---
    vertical_status_counts = defaultdict(lambda: {'Running': 0, 'Closed': 0, 'Open': 0})

    for p in projects:
        if not p.vertical:
            continue
        # Closure date logic
        closure_date = None
        if getattr(p, 'final_closure_date', None):
            closure_date = p.final_closure_date
        elif getattr(p, 'revised_pdc', None):
            closure_date = p.revised_pdc
        elif getattr(p, 'original_pdc', None):
            closure_date = p.original_pdc

        today = datetime.today().date()
        # Status logic: Closed, Open, Running
        if closure_date and closure_date <= today:
            vertical_status_counts[p.vertical]['Closed'] += 1
        elif p.sanctioned_date and p.sanctioned_date.year == today.year and (not closure_date or closure_date > today):
            vertical_status_counts[p.vertical]['Open'] += 1
        else:
            vertical_status_counts[p.vertical]['Running'] += 1

    vertical_status_labels = sorted(vertical_status_counts.keys())
    vertical_status_data = {
        'Running': [vertical_status_counts[v]['Running'] for v in vertical_status_labels],
        'Closed': [vertical_status_counts[v]['Closed'] for v in vertical_status_labels],
        'Open': [vertical_status_counts[v]['Open'] for v in vertical_status_labels],
    }

    # --- Projects by Funding Range (Histogram) ---
    # Define funding brackets in lakhs
    funding_brackets = [
        (0, 50), (50, 100), (100, 200), (200, 500), (500, 1000), (1000, 5000), (5000, 10000)
    ]
    funding_labels = [f"{low}-{high}L" for (low, high) in funding_brackets]
    funding_counts = [0 for _ in funding_brackets]
    for p in projects:
        if p.cost_lakhs is not None:
            for i, (low, high) in enumerate(funding_brackets):
                if low <= p.cost_lakhs < high:
                    funding_counts[i] += 1
                    break

    # --- Top Institutes by Number of Projects ---
    institute_counts = Counter()
    for p in projects:
        if p.academia:
            # Extract name after the first comma, or use the whole string if no comma
            if ',' in p.academia:
                institute = p.academia.split(',', 1)[1].strip()
            else:
                institute = p.academia.strip()
            institute_counts[institute] += 1

    # Get top N (e.g., 10) institutes
    top_n = 10
    top_institutes = institute_counts.most_common(top_n)
    top_institute_labels = [x[0] for x in top_institutes]
    top_institute_values = [x[1] for x in top_institutes]

    pi_names = []
    for p in projects:
        if p.pi_name:
            # Take only before comma
            before_comma = p.pi_name.split(',')[0]
            # Split on '/' and strip spaces
            for name in before_comma.split('/'):
                clean_name = name.strip()
                if clean_name:
                    pi_names.append(clean_name)

    pi_counts = Counter(pi_names)
    top_pis = pi_counts.most_common(10)  # Get top 10 PIs
    top_pis_labels = [pi[0] for pi in top_pis]
    top_pis_values = [pi[1] for pi in top_pis]

    # --- Administrative Status Trend (Line/Area Chart) ---
    status_trend = defaultdict(lambda: defaultdict(int))
    today = datetime.today().date()
    for p in projects:
        if p.sanctioned_date:
            start_year = p.sanctioned_date.year
            # Determine closure year (if any)
            closure_date = None
            if getattr(p, 'final_closure_date', None):
                closure_date = p.final_closure_date
            elif getattr(p, 'revised_pdc', None):
                closure_date = p.revised_pdc
            elif getattr(p, 'original_pdc', None):
                closure_date = p.original_pdc
            end_year = closure_date.year if closure_date and closure_date <= today else today.year

            # Mark as "Ongoing" for every year from sanction to closure (or today)
            for year in range(start_year, end_year + 1):
                if year == end_year and closure_date and closure_date.year == year and closure_date <= today:
                    # If closed in this year, count as "Completed" (or "Closed") for this year
                    status_trend["Completed"][year] += 1
                else:
                    status_trend["Ongoing"][year] += 1

    # Prepare sorted lists for Chart.js
    all_statuses = sorted(status_trend.keys())
    all_years = sorted({year for status in status_trend.values() for year in status.keys()})
    status_trend_labels = [str(y) for y in all_years]
    status_trend_datasets = []
    for i, status in enumerate(all_statuses):
        data = [status_trend[status].get(y, 0) for y in all_years]
        status_trend_datasets.append({
            "label": status,
            "data": data,
            "borderColor": f"rgba({60+i*40},{100+i*30},{200-i*30},0.9)",
            "backgroundColor": f"rgba({60+i*40},{100+i*30},{200-i*30},0.2)",
            "fill": True
        })

    # --- Sanctioned Cost Trend per Year ---
    cost_trend_year = {}
    for p in projects:
        if p.sanctioned_date and p.cost_lakhs is not None:
            year = p.sanctioned_date.year
            try:
                cost_trend_year[year] = cost_trend_year.get(year, 0) + float(p.cost_lakhs)
            except ValueError:
                continue
    cost_trend_year_labels = sorted(cost_trend_year.keys())
    cost_trend_year_values = [cost_trend_year[y] for y in cost_trend_year_labels]

    # Projects by Stakeholder Lab
    stakeholder_counts = Counter()
    for p in projects:
        if p.stakeholders:
            labs = [lab.strip() for lab in str(p.stakeholders).split(',') if lab.strip()]
            for lab in labs:
                stakeholder_counts[lab] += 1
    stakeholder_lab_labels = list(stakeholder_counts.keys())
    stakeholder_lab_values = [stakeholder_counts[k] for k in stakeholder_lab_labels]

    return render_template(
        'visualization.html',
        admin_status_counts=admin_status_counts,
        year_labels=year_labels,
        year_values=year_values,
        vertical_counts=vertical_counts,
        institute_vertical_counts=institute_vertical_counts,
        cost_institute_labels=cost_institute_labels,
        cost_institute_values=cost_institute_values,
        cost_vertical_labels=cost_vertical_labels,
        cost_vertical_values=cost_vertical_values,
        stacked_labels=stacked_labels,
        stacked_verticals=stacked_verticals,
        stacked_data=stacked_data,
        quarter_labels=quarter_labels,
        quarter_data=quarter_data,
        half_labels=half_labels,
        half_data=half_data,
        year_labels_status=year_labels_status,
        year_data_status=year_data_status,
        avg_duration_labels=avg_duration_labels,
        avg_duration_values=avg_duration_values,
        vertical_status_labels=vertical_status_labels,
        vertical_status_data=vertical_status_data,
        funding_labels=funding_labels,
        funding_counts=funding_counts,
        top_institute_labels=top_institute_labels,
        top_institute_values=top_institute_values,
        top_pis_labels=top_pis_labels,
        top_pis_values=top_pis_values,
        status_trend_labels=status_trend_labels,
        status_trend_datasets=status_trend_datasets,
        cost_trend_year_labels=cost_trend_year_labels,
        cost_trend_year_values=cost_trend_year_values,
        stakeholder_lab_labels=stakeholder_lab_labels,
        stakeholder_lab_values=stakeholder_lab_values,
    )

# Route for the add project page (admin only)
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_project():
    if current_user.role != 'admin':
        flash("Unauthorized access. You do not have permission to add projects.", "danger")
        return redirect(url_for('dashboard'))

    form = ProjectForm()
    if form.validate_on_submit():
        # Date validations
        if form.original_pdc.data < form.sanctioned_date.data:
            flash("Original PDC cannot be before the Sanctioned Date.", "danger")
            return render_template('add_project.html', form=form)
        if form.revised_pdc.data < form.original_pdc.data:
            flash("Revised PDC cannot be before the Original PDC.","danger")
            return render_template('add_project.html', form=form)
        # Unique serial number validation
        existing_project = Project.query.filter_by(serial_no=form.serial_no.data).first()
        if existing_project:
            form.serial_no.errors.append("Project with this serial number already exists")
            return render_template('add_project.html', form=form)
        
        rab_filenames = []
        if form.rab_minutes.data:
            for file in form.rab_minutes.data:
                filename = save_pdf(file)
                if filename:
                    rab_filenames.append(filename)
        gc_filenames = []
        if form.gc_minutes.data:
            for file in form.gc_minutes.data:
                filename = save_pdf(file)
                if filename:
                    gc_filenames.append(filename)
        final_report_filenames = []
        if form.final_report.data:
            for file in form.final_report.data:
                filename = save_pdf(file)
                if filename:
                    final_report_filenames.append(filename)

        # Add project
        project = Project(
            serial_no=form.serial_no.data,
            title=form.title.data,
            academia=form.academia.data,
            pi_name=form.pi_name.data,
            coord_lab=form.coord_lab.data,
            scientist=form.scientist.data,
            vertical=form.vertical.data,
            cost_lakhs=form.cost_lakhs.data,
            sanctioned_date=form.sanctioned_date.data, 
            original_pdc=form.original_pdc.data,
            revised_pdc=form.revised_pdc.data,
            stakeholders=form.stakeholders.data,
            scope_objective=form.scope_objective.data,
            expected_deliverables=form.expected_deliverables.data,
            Outcome_Dovetailing_with_Ongoing_Work=form.Outcome_Dovetailing_with_Ongoing_Work.data,
            rab_meeting_date=form.rab_meeting_date.data,
            rab_meeting_held_date=form.rab_meeting_held_date.data,
            rab_minutes=','.join(rab_filenames),
            gc_meeting_date=form.gc_meeting_date.data,
            gc_meeting_held_date=form.gc_meeting_held_date.data,
            technical_status=form.technical_status.data,
            administrative_status=form.administrative_status.data,
            final_closure_date=form.final_closure_date.data,
            final_closure_remarks=form.final_closure_remarks.data,
            final_report=','.join(final_report_filenames)
        )
        db.session.add(project)
        db.session.commit()
        log_action(current_user, f"Added project '{form.title.data}'")
        flash("Project added successfully.", "success")
        return redirect(url_for('dashboard'))

    return render_template('add_project.html', form=form)

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/post_technical_status/<int:project_id>', methods=['POST'])
@login_required
def post_technical_status(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Only admins can update Technical Status.'}), 403
    technical_status = request.form.get('technical_status', '').strip()
    if technical_status:
        # Append technical_status with username and timestamp (optional)
        timestamp = datetime.now(timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M')
        new_technical_status = f"{current_user.username} ({timestamp}): {technical_status}"
        if project.technical_status:
            project.technical_status += "\n" + new_technical_status
        else:
            project.technical_status = new_technical_status
        db.session.commit()
        log_action(current_user, f"Updates technical status of project '{project.title}'")
        return jsonify({'success': True, 'technical_status': new_technical_status})
    return jsonify({'success': False, 'message': 'Technical Status cannot be empty.'}), 400

@app.route('/post_rab_meeting_scheduled_date/<int:project_id>', methods=['POST'])
@login_required
def post_rab_meeting_scheduled_date(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Only admins can update RAB Meeting Scheduled Date.'}), 403
    rab_meeting_date = request.form.get('rab_meeting_date', '').strip()
    if rab_meeting_date:
        new_rab_meeting_date = f"{rab_meeting_date}"
        if project.rab_meeting_date:
            project.rab_meeting_date += "\n" + new_rab_meeting_date
        else:
            project.rab_meeting_date = new_rab_meeting_date
        db.session.commit()
        log_action(current_user, f"Updates RAB Meeting Scheduled Date '{project.title}'")
        return jsonify({'success': True, 'rab_meeting_date': new_rab_meeting_date})
    return jsonify({'success': False, 'message': 'RAB Meeting Scheduled Date cannot be empty.'}), 400


@app.route('/post_rab_meeting_held_date/<int:project_id>', methods=['POST'])
@login_required
def post_rab_meeting_held_date(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Only admins can update RAB Meeting Held Date.'}), 403
    rab_meeting_held_date = request.form.get('rab_meeting_held_date', '').strip()
    if rab_meeting_held_date:
        new_rab_meeting_held_date = f"{rab_meeting_held_date}"
        if project.rab_meeting_held_date:
            project.rab_meeting_held_date += "\n" + new_rab_meeting_held_date
        else:
            project.rab_meeting_held_date = new_rab_meeting_held_date
        db.session.commit()
        log_action(current_user, f"Updates RAB Meeting Held Date '{project.title}'")
        return jsonify({'success': True, 'rab_meeting_held_date': new_rab_meeting_held_date})
    return jsonify({'success': False, 'message': 'RAB Meeting Held Date cannot be empty.'}), 400

@app.route('/post_rab_minutes_of_meeting/<int:project_id>', methods=['POST'])
@login_required
def post_rab_minutes_of_meeting(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Only admins can update RAB Minutes of Meeting.'}), 403
    rab_minutes = request.form.get('rab_minutes', '').strip()
    if rab_minutes:
        new_rab_minutes = f"{rab_minutes}"
        if project.rab_minutes:
            project.rab_minutes += "\n" + new_rab_minutes
        else:
            project.rab_minutes = new_rab_minutes
        db.session.commit()
        log_action(current_user, f"Updates RAB Minutes of Meeting '{project.title}'")
        return jsonify({'success': True, 'rab_minutes': new_rab_minutes})
    return jsonify({'success': False, 'message': 'RAB Minutes of Meeting cannot be empty.'}), 400


@app.route('/post_gc_meeting_scheduled_date/<int:project_id>', methods=['POST'])
@login_required
def post_gc_meeting_scheduled_date(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Only admins can update GC Meeting Scheduled Date.'}), 403
    gc_meeting_date = request.form.get('gc_meeting_date', '').strip()
    if gc_meeting_date:
        new_gc_meeting_date = f"{gc_meeting_date}"
        if project.gc_meeting_date:
            project.gc_meeting_date += "\n" + new_gc_meeting_date
        else:
            project.gc_meeting_date = new_gc_meeting_date
        db.session.commit()
        log_action(current_user, f"Updates GC Meeting Scheduled Date '{project.title}'")
        return jsonify({'success': True, 'gc_meeting_date': new_gc_meeting_date})
    return jsonify({'success': False, 'message': 'GC Meeting Scheduled Date cannot be empty.'}), 400



@app.route('/post_gc_meeting_held_date/<int:project_id>', methods=['POST'])
@login_required
def post_gc_meeting_held_date(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Only admins can update GC Meeting Held Date.'}), 403
    gc_meeting_held_date = request.form.get('gc_meeting_held_date', '').strip()
    if gc_meeting_held_date:
        new_gc_meeting_held_date = f"{gc_meeting_held_date}"
        if project.gc_meeting_held_date:
            project.gc_meeting_held_date += "\n" + new_gc_meeting_held_date
        else:
            project.gc_meeting_held_date = new_gc_meeting_held_date
        db.session.commit()
        log_action(current_user, f"Updates GC Meeting Held Date '{project.title}'")
        return jsonify({'success': True, 'gc_meeting_held_date': new_gc_meeting_held_date})
    return jsonify({'success': False, 'message': 'GC Meeting Held Date cannot be empty.'}), 400


@app.route('/post_gc_minutes_of_meeting/<int:project_id>', methods=['POST'])
@login_required
def post_gc_minutes_of_meeting(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Only admins can update GC Minutes of Meeting.'}), 403
    gc_minutes = request.form.get('gc_minutes', '').strip()
    if gc_minutes:
        new_gc_minutes = f"{gc_minutes}"
        if project.gc_minutes:
            project.gc_minutes += "\n" + new_gc_minutes
        else:
            project.gc_minutes = new_gc_minutes
        db.session.commit()
        log_action(current_user, f"Updates GC Minutes of Meeting '{project.title}'")
        return jsonify({'success': True, 'gc_minutes': new_gc_minutes})
    return jsonify({'success': False, 'message': 'GC Minutes of Meeting cannot be empty.'}), 400

# Route for the modify search page (admin only)
@app.route('/modify_search', methods=['GET'])
@login_required
def modify_search():
    if current_user.role != 'admin':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dashboard'))

    query = Project.query
    column = request.args.get('column', '')
    value = request.args.get('value', '').strip()

    if column and value:
        if column == 'serial_no':
            query = query.filter(Project.serial_no.ilike(f"%{value}%"))
        elif column == 'title':
            query = query.filter(Project.title.ilike(f"%{value}%"))
        elif column == 'vertical':
            query = query.filter(Project.vertical.ilike(f"%{value}%"))
        elif column == 'academia':
            query = query.filter(Project.academia.ilike(f"%{value}%"))
        elif column == 'pi_name':
            query = query.filter(Project.pi_name.ilike(f"%{value}%"))
        elif column == 'coord_lab':
            query = query.filter(Project.coord_lab.ilike(f"%{value}%"))
        elif column == 'scientist':
            query = query.filter(Project.scientist.ilike(f"%{value}%"))
        elif column == 'cost_lakhs':
            try:
                cost = float(value)
                query = query.filter(Project.cost_lakhs == cost)
            except ValueError:
                pass
        elif column == 'sanctioned_date':
            try:
                query = query.filter(Project.sanctioned_date == value)
            except ValueError:
                pass
        elif column == 'original_pdc':
            try:
                query = query.filter(Project.original_pdc == value)
            except ValueError:
                pass
        elif column == 'revised_pdc':
            try:
                query = query.filter(Project.revised_pdc == value)
            except ValueError:
                pass
        elif column == 'administrative_status':
            query = query.filter(Project.administrative_status.ilike(f"%{value}%"))

        projects = query.all()
    else:
        projects = None

    return render_template('modify_search.html', projects=projects)



# Route for the edit project page (Admin only)
@app.route('/edit/<int:project_id>', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    if current_user.role != 'admin':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dashboard'))

    project = Project.query.get_or_404(project_id)
    form = ProjectForm(obj=project)

    if form.validate_on_submit():
        # Date validations (same as in add_project)
        if form.original_pdc.data <= form.sanctioned_date.data:
            flash("Original PDC cannot be before or equal to the Sanctioned Date.", "danger")
            return render_template('edit_project.html', form=form, project=project)
        if form.revised_pdc.data < form.original_pdc.data:
            flash("Revised PDC cannot be before the Original PDC.", "danger")
            return render_template('edit_project.html', form=form, project=project)

        # Append new files to existing list
        rab_filenames = project.rab_minutes.split(',') if project.rab_minutes else []
        if form.rab_minutes.data:
            for file in form.rab_minutes.data:
                # Only save if it's a FileStorage (uploaded file)
                if hasattr(file, "filename") and file.filename:
                    filename = save_pdf(file)
                    if filename:
                        rab_filenames.append(filename)
        project.rab_minutes = ','.join([f for f in rab_filenames if f])

        gc_filenames = project.gc_minutes.split(',') if project.gc_minutes else []
        if form.gc_minutes.data:
            for file in form.gc_minutes.data:
                if hasattr(file, "filename") and file.filename:
                    filename = save_pdf(file)
                    if filename:
                        gc_filenames.append(filename)
        project.gc_minutes = ','.join([f for f in gc_filenames if f])

        final_report_filenames = project.final_report.split(',') if project.final_report else []
        if form.final_report.data:
            for file in form.final_report.data:
                if hasattr(file, "filename") and file.filename:
                    filename = save_pdf(file)
                    if filename:
                        final_report_filenames.append(filename)
        project.final_report = ','.join([f for f in final_report_filenames if f])

        # Update project
        exclude_fields = ['rab_minutes', 'gc_minutes', 'final_report']
        for field in form:
            if field.name not in exclude_fields and hasattr(project, field.name):
                setattr(project, field.name, field.data)

        db.session.commit()
        log_action(current_user, f"Edited project '{project.title}'")
        flash('Project updated successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('edit_project.html', form=form, project=project)


@app.route('/remove_mom_file/<int:project_id>/<mom_type>/<filename>')
@login_required
def remove_mom_file(project_id, mom_type, filename):
    project = Project.query.get_or_404(project_id)
    if current_user.role != 'admin':
        flash("Unauthorized.", "danger")
        return redirect(url_for('dashboard'))
    if mom_type == 'rab':
        files = project.rab_minutes.split(',') if project.rab_minutes else []
        files = [f for f in files if f != filename]
        project.rab_minutes = ','.join(files)
    elif mom_type == 'gc':
        files = project.gc_minutes.split(',') if project.gc_minutes else []
        files = [f for f in files if f != filename]
        project.gc_minutes = ','.join(files)
    elif mom_type == 'final_report':  
        files = project.final_report.split(',') if project.final_report else []
        files = [f for f in files if f != filename]
        project.final_report = ','.join(files)
    # Optionally delete file from disk
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    except Exception:
        pass
    db.session.commit()
    flash("File removed.", "success")
    return redirect(request.referrer or url_for('dashboard'))


# Route for the delete project page (Admin only)
@app.route('/delete', methods=['GET', 'POST'])
@login_required
def delete_project():
    if current_user.role != 'admin':
        flash("Unauthorized access. You do not have permission to delete projects", "danger")
        return redirect(url_for('dashboard'))

    query = Project.query   

    # Dropdown filter logic
    column = request.args.get('column', '')
    value = request.args.get('value', '').strip()
    if column and value:
        if column == 'serial_no':
            query = query.filter(Project.serial_no.ilike(f"%{value}%"))
        elif column == 'title':
            query = query.filter(Project.title.ilike(f"%{value}%"))

    projects = query.order_by(Project.serial_no).all()

    if request.method == 'POST':
        project_id = request.form.get('project_id')
        project = Project.query.get(project_id)
        if project:
            db.session.delete(project)
            db.session.commit()
            log_action(current_user, f"Deleted project '{project.title}'")
            flash("Project deleted successfully.", "success")
            return redirect(url_for('delete_project'))
        else:
            flash("Project not found.", "danger")

    return render_template('delete_proj.html', projects=projects, now=datetime.now())

@app.route('/upload_mom/<int:project_id>/<mom_type>', methods=['POST'])
@login_required
def upload_mom(project_id, mom_type):
    project = Project.query.get_or_404(project_id)
    if current_user.role != 'admin':
        flash("Unauthorized.", "danger")
        return redirect(url_for('dashboard'))
    file = request.files.get('mom_file')
    if file and file.filename.endswith('.pdf'):
        filename = save_pdf(file)
        if mom_type == 'rab':
            files = project.rab_minutes.split(',') if project.rab_minutes else []
            files.append(filename)
            project.rab_minutes = ','.join(files)
        elif mom_type == 'gc':
            files = project.gc_minutes.split(',') if project.gc_minutes else []
            files.append(filename)
            project.gc_minutes = ','.join(files)
        db.session.commit()
        flash("PDF attached successfully.", "success")
    else:
        flash("Please upload a valid PDF file.", "danger")
    return redirect(request.referrer or url_for('dashboard'))

# Route for the download CSV
@app.route('/download_csv', methods=['GET'])
@login_required
def download_csv():
    projects = Project.query.order_by(db.cast(Project.serial_no, db.Integer)).all()
    csv_data = "S. No, Nomenclature, Academia/Institute, PI Name, Coordinating Lab, Coordinating Lab Scientist, Research Vertical, Sanctioned Cost (in Lakhs), Sanctioned Date, Original PDC, Revised PDC, Stake Holding Labs, Scope/Objective of the Project, Expected Deliverables/Technology, Outcome Dovetailing with Ongoing Work, RAB Meeting Scheduled Date, RAB Meeting Held Date, RAB Minutes of Meeting, GC Meeting Scheduled Date, GC Meeting Held Date, GC Minutes of Meeting, Technical Status, Administrative Status, Final Closure Status\n"
    for project in projects:
        def esc(val):
            if val is None:
                return ""
            return str(val).replace('"', '""').replace('\n', ' | ')
        csv_data += (
            f'"{esc(project.serial_no)}","{esc(project.title)}","{esc(project.academia)}","{esc(project.pi_name)}",'
            f'"{esc(project.coord_lab)}","{esc(project.scientist)}","{esc(project.vertical)}","{esc(project.cost_lakhs)}",'
            f'"{esc(project.sanctioned_date)}","{esc(project.original_pdc)}",'
            f'"{esc(project.revised_pdc)}","{esc(project.stakeholders)}",'
            f'"{esc(project.scope_objective)}",'
            f'"{esc(project.expected_deliverables)}",'
            f'"{esc(project.Outcome_Dovetailing_with_Ongoing_Work)}",'
            f'"{esc(project.rab_meeting_date)}","{esc(project.rab_meeting_held_date)}",'
            f'"{esc(project.gc_meeting_date)}","{esc(project.gc_meeting_held_date)}",'
            f'"{esc(project.gc_minutes)}",'
            f'"{esc(project.technical_status)}","{esc(project.administrative_status)}"\n'
            f'"{esc((str(project.final_closure_date) if project.final_closure_date else "") + (" | " + project.final_closure_remarks if project.final_closure_remarks else ""))}",'
        )

    # Ensure no redundant columns are added
    csv_data = csv_data.strip()  

    current_date = datetime.now().strftime("%Y-%m-%d")
    filename = f"DIA_CoE_{current_date}.csv"
    response = app.response_class(
        response=csv_data,
        status=200,
        mimetype='text/csv'
    )
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response

# Route for the download PDF
@app.route('/download_pdf', methods=['GET'])
@login_required
def download_pdf():
    projects = Project.query.order_by(db.cast(Project.serial_no, db.Integer)).all()

    buffer = BytesIO()
    page_width, page_height = landscape(A4)
    margin = 30
    available_width = page_width - 2 * margin

    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=margin, rightMargin=margin)
    elements = []

    styles = getSampleStyleSheet()
    wrap_style = styles['Normal']
    wrap_style.fontSize = 7
    wrap_style.leading = 9

    # Header row using Paragraph for wrapped text
    header_row = [
        Paragraph("S. No.", wrap_style),
        Paragraph("Nomenclature", wrap_style),
        Paragraph("Academia / Institute", wrap_style),
        Paragraph("PI Name", wrap_style),
        Paragraph("Coordinating Lab", wrap_style),
        Paragraph("Coordinating Lab Scientist", wrap_style),
        Paragraph("Research Vertical", wrap_style),
        Paragraph("Cost (Lakhs)", wrap_style),
        Paragraph("Sanctioned Date", wrap_style),
        Paragraph("Original PDC", wrap_style),
        Paragraph("Revised PDC", wrap_style),
        Paragraph("Stake Holding Labs", wrap_style),
        Paragraph("Scope / Objective of the Project", wrap_style),
        Paragraph("Expected Deliverables / Technology", wrap_style),
        Paragraph("Outcome Dovetailing with Ongoing Work", wrap_style),
        Paragraph("RAB Meeting Scheduled Date", wrap_style),
        Paragraph("RAB Meeting Held Date", wrap_style),
        Paragraph("GC Meeting Scheduled Date", wrap_style),
        Paragraph("GC Meeting Held Date", wrap_style),
        Paragraph("Technical Status", wrap_style),
        Paragraph("Administrative Status", wrap_style),
        Paragraph("Final Closure Status", wrap_style)
    ]

    data = [header_row]

    for project in projects:
        data.append([
            str(project.serial_no),
            Paragraph(project.title or '', wrap_style),
            Paragraph(project.academia or '', wrap_style),
            Paragraph(project.pi_name or '', wrap_style),
            Paragraph(project.coord_lab or '', wrap_style),
            Paragraph(project.scientist or '', wrap_style),
            Paragraph(project.vertical or '', wrap_style),
            str(project.cost_lakhs or ''),
            str(project.sanctioned_date or ''),
            str(project.original_pdc or ''),
            str(project.revised_pdc or ''),
            Paragraph(project.stakeholders or '', wrap_style),
            Paragraph(project.scope_objective or '', wrap_style),
            Paragraph(project.expected_deliverables or '', wrap_style),
            Paragraph(project.Outcome_Dovetailing_with_Ongoing_Work or '', wrap_style),
            str(project.rab_meeting_date or ''),
            str(project.rab_meeting_held_date or ''),
            str(project.gc_meeting_date or ''),
            str(project.gc_meeting_held_date or ''),
            Paragraph((project.technical_status or '').replace('\n', '<br/>'), wrap_style),
            Paragraph(project.administrative_status or '', wrap_style),
            Paragraph(
                (project.final_closure_date.strftime('%Y-%m-%d') if project.final_closure_date else '') +
                ('<br/><b>Remarks:</b> ' + project.final_closure_remarks if project.final_closure_remarks else ''),
                wrap_style
            )
        ])

    # Define proportional column widths
    col_widths = [
        20,   # S. No.
        100,  # Nomenclature
        65,   # Academia / Institute
        65,   # PI Name
        60,   # Coordinating Lab
        70,   # Coordinating Lab Scientist
        60,   # Research Vertical
        50,   # Cost (Lakhs)
        75,   # Sanctioned Date
        75,   # Original PDC
        75,   # Revised PDC
        70,   # Stake Holding Labs
        75,   # Scope / Objective of the Project
        75,   # Expected Deliverables / Technology
        75,   # Outcome Dovetailing with Ongoing Work
        75,   # RAB Meeting Scheduled Date
        75,   # RAB Meeting Held Date
        75,   # GC Meeting Scheduled Date
        75,   # GC Meeting Held Date
        70,   # Technical Status
        65,   # Administrative Status
        70,   # Final Closure Status
    ]
    scale_factor = available_width / sum(col_widths)
    col_widths = [w * scale_factor for w in col_widths]

    table = Table(data, colWidths=col_widths, repeatRows=1)

    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)
    filename = f"DIA_CoE_{datetime.now().strftime('%Y-%m-%d')}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

# Route for the view logs page(Admin only)
@app.route('/logs')
@login_required 
def view_logs():
    if current_user.role != 'admin':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dashboard'))
    logs = Log.query.order_by(Log.timestamp.desc()).all()
    return render_template('logs.html', logs=logs, now=datetime.now())


# Route for the view profile page
#Logout user
@app.route('/logout')
@login_required
def logout():
    log_action(current_user, "User logged out")
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

# Auto-create tables and seed default users
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin_user = User(username='admin', password=generate_password_hash('admin123'), role='admin')
        viewer_user = User(username='viewer', password=generate_password_hash('viewer123'), role='viewer')
        db.session.add_all([admin_user, viewer_user])
        db.session.commit()

# Only runs locally, not on Render
if __name__ == '__main__':
    app.run(debug=True)