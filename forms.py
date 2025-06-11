#importing necessary libraries
from flask_wtf import FlaskForm
from wtforms import IntegerField, StringField, PasswordField, SubmitField, FloatField, DateField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Length, ValidationError, Optional

# This file is part of the Project Management System.
# LoginForm is used for user authentication on the login page
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=50)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

# This file is part of the Project Management System.
# ProjectForm is used for adding and editing project data
class ProjectForm(FlaskForm):
    # Basic project fields with corresponding validations
    serial_no = IntegerField('S. No.', validators=[DataRequired()])
    title = StringField('Nomenclature', validators=[DataRequired()])
    academia = StringField('Academia/Institute')
    pi_name = StringField('PI Name')
    coord_lab = StringField('Coordinating Lab')
    scientist = StringField('Coordinating Lab Scientist', validators=[DataRequired()])
    vertical = StringField('Research Vertical')
    cost_lakhs = FloatField('Cost (in Lakhs)')
    sanctioned_date = DateField('Sanctioned Date', validators=[DataRequired()])
    original_pdc = DateField('Original PDC')
    revised_pdc = DateField('Revised PDC')
    stakeholders = StringField('Stakeholding Labs')
    scope_objective = TextAreaField('Scope/Objective of Project')
    expected_deliverables = StringField('Expected Deliverables/ Technologies')
    Outcome_Dovetailing_with_Ongoing_Work=TextAreaField('Outcome Dovetailing with Ongoing Work')
    rab_meeting_date = TextAreaField('RAB Meeting Scheduled Date')
    rab_meeting_held_date = TextAreaField('RAB Meeting Held Date')
    rab_minutes = TextAreaField('RAB Minutes of Meeting')
    gc_meeting_date = TextAreaField('GC Meeting Date')
    gc_meeting_held_date = TextAreaField('GC Meeting Scheduled Held Date')
    gc_minutes = TextAreaField('GC Minutes of Meeting')
    technical_status = TextAreaField('Technical Status')
    administrative_status = SelectField('Administrative Status', choices=[('ongoing', 'Ongoing'), ('completed', 'Completed'), ('pending', 'Pending')], validators=[DataRequired()])
    final_closure_date = DateField('Final Closure Date', format='%Y-%m-%d', validators=[Optional()])
    final_closure_remarks = TextAreaField('Final Closure Remarks', validators=[Optional()])
    submit = SubmitField('Submit')
    
    def validate_original_pdc(self, field):
        if self.sanctioned_date.data and field.data <= self.sanctioned_date.data:
            raise ValidationError("Original PDC cannot be before or equal to the Sanctioned Date.")
    
    def validate_revised_pdc(self, field):
        if self.original_pdc.data and field.data < self.original_pdc.data:
            raise ValidationError("Revised PDC cannot be before the Original PDC.")