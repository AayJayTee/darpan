from app import app, db
from sqlalchemy import text

with app.app_context():
    # Check if column already exists (optional, for safety)
    result = db.session.execute(
        text("PRAGMA table_info(project);")
    )
    columns = [row[1] for row in result]
    if 'final_report' not in columns:
        db.session.execute(
            text("ALTER TABLE project ADD COLUMN final_report TEXT;")
        )
        db.session.commit()
        print("final_report column added.")
    else:
        print("final_report column already exists.")