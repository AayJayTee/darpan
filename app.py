#Import necessary libraries
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Project, Log
from forms import LoginForm, ProjectForm
import datetime
from datetime import datetime, timedelta
from pytz import timezone

from io import BytesIO
from flask import send_file
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from flask_migrate import Migrate
from collections import Counter, defaultdict

from collections import defaultdict
import calendar

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
        stacked_data=stacked_data
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
            expected_deliverables=form.expected_deliverables.data,
            Outcome_Dovetailing_with_Ongoing_Work=form.Outcome_Dovetailing_with_Ongoing_Work.data,
            rab_meeting_date=form.rab_meeting_date.data,
            rab_meeting_held_date=form.rab_meeting_held_date.data,
            rab_minutes=form.rab_minutes.data,
            gc_meeting_date=form.gc_meeting_date.data,
            gc_meeting_held_date=form.gc_meeting_held_date.data,
            gc_minutes=form.gc_minutes.data,
            technical_status=form.technical_status.data,
            administrative_status=form.administrative_status.data
        )
        db.session.add(project)
        db.session.commit()
        log_action(current_user, f"Added project '{form.title.data}'")
        flash("Project added successfully.", "success")
        return redirect(url_for('dashboard'))

    return render_template('add_project.html', form=form)

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

        # Update project
        form.populate_obj(project)
        db.session.commit()
        log_action(current_user, f"Edited project '{project.title}'")
        flash('Project updated successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('edit_project.html', form=form, project=project)

# Route for the delete project page (Admin only)
@app.route('/delete', methods=['GET', 'POST'])
@login_required
def delete_project():
    if current_user.role != 'admin':
        flash("Unauthorized access. You do not have permission to delete projects", "danger")
        return redirect(url_for('dashboard'))

    projects = Project.query.all()

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


# Route for the download CSV
@app.route('/download_csv', methods=['GET'])
@login_required
def download_csv():
    projects = Project.query.order_by(db.cast(Project.serial_no, db.Integer)).all()
    csv_data = "S. No, Nomenclature, Academia/Institute, PI Name, Coordinating Lab, Coordinating Lab Scientist, Research Vertical, Sanctioned Cost (in Lakhs), Sanctioned Date, Original PDC, Revised PDC, Stake Holding Labs, Expected Deliverables/Technology, Outcome Dovetailing with Ongoing Work, RAB Meeting Scheduled Date, RAB Meeting Held Date, RAB Minutes of Meeting, GC Meeting Scheduled Date, GC Meeting Held Date, GC Minutes of Meeting, Technical Status, Administrative Status\n"
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
            f'"{esc(project.expected_deliverables)}",'
            f'"{esc(project.Outcome_Dovetailing_with_Ongoing_Work)}",'
            f'"{esc(project.rab_meeting_date)}","{esc(project.rab_meeting_held_date)}",'
            f'"{esc(project.gc_meeting_date)}","{esc(project.gc_meeting_held_date)}",'
            f'"{esc(project.gc_minutes)}",'
            f'"{esc(project.technical_status)}","{esc(project.administrative_status)}"\n'
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
        Paragraph("Expected Deliverables / Technology", wrap_style),
        Paragraph("Outcome Dovetailing with Ongoing Work", wrap_style),
        Paragraph("RAB Meeting Scheduled Date", wrap_style),
        Paragraph("RAB Meeting Held Date", wrap_style),
        Paragraph("RAB Minutes of Meeting", wrap_style),
        Paragraph("GC Meeting Scheduled Date", wrap_style),
        Paragraph("GC Meeting Held Date", wrap_style),
        Paragraph("GC Minutes of Meeting", wrap_style),
        Paragraph("Technical Status", wrap_style),
        Paragraph("Administrative Status", wrap_style)
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
            Paragraph(project.expected_deliverables or '', wrap_style),
            Paragraph(project.Outcome_Dovetailing_with_Ongoing_Work or '', wrap_style),
            str(project.rab_meeting_date or ''),
            str(project.rab_meeting_held_date or ''),
            Paragraph(project.rab_minutes or '', wrap_style),
            str(project.gc_meeting_date or ''),
            str(project.gc_meeting_held_date or ''),
            Paragraph(project.gc_minutes or '', wrap_style),
            Paragraph((project.technical_status or '').replace('\n', '<br/>'), wrap_style),
            Paragraph(project.administrative_status or '', wrap_style)
        ])

    # Define proportional column widths
    col_widths = [35, 100, 85, 65, 65, 75, 65, 45, 75, 75, 75, 75, 75, 75, 75, 75, 100, 75, 75, 100, 90, 75]
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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        #initialize default users
        if not User.query.filter_by(username='admin').first():
            admin_user = User(username='admin', password=generate_password_hash('admin123'), role='admin')
            viewer_user = User(username='viewer', password=generate_password_hash('viewer123'), role='viewer')
            db.session.add(admin_user)
            db.session.add(viewer_user)
            db.session.commit()

    app.run(debug=True)
