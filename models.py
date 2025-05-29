from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Job(db.Model):
    __tablename__ = 'job'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    skills_weight = db.Column(db.Float, default=5.0)
    experience_weight = db.Column(db.Float, default=5.0)
    education_weight = db.Column(db.Float, default=5.0)
    overall_weight = db.Column(db.Float, default=1.0)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    cvs = db.relationship('CV', backref='job', lazy=True)
    criteria = db.relationship('ScoringCriteria', backref='job', lazy=True)

class CV(db.Model):
    __tablename__ = 'cv'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    scores = db.relationship('CVScore', backref='cv', lazy=True)

class ScoringCriteria(db.Model):
    __tablename__ = 'scoring_criteria'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    weight = db.Column(db.Float, default=1.0)

class CVScore(db.Model):
    __tablename__ = 'cv_score'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    cv_id = db.Column(db.Integer, db.ForeignKey('cv.id'), nullable=False)
    criteria_id = db.Column(db.Integer, db.ForeignKey('scoring_criteria.id'))
    score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, server_default=db.func.now())