#models.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy.orm import validates

# This file contains the database models for the application.
db = SQLAlchemy()

# Define the User(for authentication and role-based access) and Log models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(10), default='viewer')

# Define the relationship between User and Log (track user actions within the system)
class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    user = db.relationship('User', backref='logs')
    
# Define the Project model (for storing project information)
class Project(db.Model):
    id = db.Column(db.Integer, primary_key = True)
    serial_no = db.Column(db.Integer, unique = True, nullable = False)
    title = db.Column(db.String(200), nullable = False)
    academia = db.Column(db.String(200), nullable = False)
    pi_name = db.Column(db.String(100), nullable = False)
    coord_lab = db.Column(db.String(100), nullable = False)
    scientist = db.Column(db.String(100), nullable = False)
    vertical = db.Column(db.String(100), nullable = False)
    cost_lakhs = db.Column(db.Float, nullable = False)
    sanctioned_date = db.Column(db.Date)
    original_pdc = db.Column(db.Date)
    revised_pdc = db.Column(db.Date)
    stakeholders = db.Column(db.String(200))
    scope_objective = db.Column(db.Text, nullable=True)
    expected_deliverables = db.Column(db.String(300))
    Outcome_Dovetailing_with_Ongoing_Work=db.Column(db.Text,nullable = True)
    rab_meeting_date = db.Column(db.Text, nullable = True)   
    rab_meeting_held_date = db.Column(db.Text, nullable = True)
    rab_minutes = db.Column(db.Text)
    gc_meeting_date = db.Column(db.Text, nullable = True)
    gc_meeting_held_date = db.Column(db.Text, nullable = True)   
    gc_minutes = db.Column(db.Text)
    technical_status = db.Column(db.Text, nullable = True)
    administrative_status = db.Column(db.String(50), nullable = False, default = "Ongoing")
    final_closure_date = db.Column(db.Date, nullable=True)
    final_closure_remarks = db.Column(db.Text, nullable=True)
    final_report = db.Column(db.Text, nullable=True) 

    #constraint
    __table_args__ = (
        db.CheckConstraint('original_pdc >= sanctioned_date', name= 'check_original_pdc'),
    )
    
    @validates('original_pdc')
    def validate_original_pdc(self, key, original_pdc):
        if self.sanctioned_date and original_pdc <= self.sanctioned_date:
            raise ValueError("Original PDC cannot be before or equal to the Sanctioned Date.")
        return original_pdc
    
    @validates('revised_pdc')
    def validate_revised_pdc(self, key, revised_pdc):
        if self.original_pdc and revised_pdc < self.original_pdc:
            raise ValueError("Revised PDC cannot be before the Original PDC.")
        return revised_pdc
   