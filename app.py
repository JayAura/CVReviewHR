import os
import logging
import uuid
import json
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, has_request_context
from werkzeug.utils import secure_filename
import threading
from file_parser import parse_cv_file
from cv_processor import process_cv_batch
from llm_service import test_llm_connection
from models import db, Job, CV, ScoringCriteria, CVScore

app = Flask(__name__)

# Production configuration
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', str(uuid.uuid4()))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    "DATABASE_URL",
    "postgresql://lottostar:L0tt0CV@localhost:5432/lottocv"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Logging for production (not DEBUG)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')
    ]
)
logger = logging.getLogger(__name__)

# Initialize the database
db.init_app(app)

def init_db():
    with app.app_context():
        try:
            inspector = db.inspect(db.engine)
            if not inspector.has_table("job"):
                db.create_all()
                logger.info("Database tables created successfully")
            else:
                logger.info("Database tables already exist, skipping creation")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise

if __name__ == "__main__" or os.environ.get("GUNICORN_WORKER") != "true":
    init_db()

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'cv_uploads')
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'txt'}
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

processing_jobs = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def wants_json_response():
    if not has_request_context():
        return False
    best = request.accept_mimetypes.best_match(['application/json', 'text/html'])
    return best == 'application/json' and request.accept_mimetypes[best] > request.accept_mimetypes['text/html']

@app.route('/')
def index():
    llm_status, llm_message = test_llm_connection()
    recent_jobs = Job.query.order_by(Job.created_at.desc()).limit(5).all()
    return render_template('index.html', 
                          llm_status=llm_status, 
                          llm_message=llm_message,
                          recent_jobs=recent_jobs)

@app.route('/jobs/new', methods=['GET'])
def new_job():
    return render_template('job_form.html')

@app.route('/jobs', methods=['POST'])
def create_job():
    job_title = request.form.get('job_title', '').strip()
    job_description = request.form.get('job_description', '').strip()
    try:
        skills_weight = float(request.form.get('skills_weight', 5))
        experience_weight = float(request.form.get('experience_weight', 5))
        education_weight = float(request.form.get('education_weight', 5))
        overall_weight = float(request.form.get('overall_weight', 1.0))
    except ValueError:
        skills_weight = 5
        experience_weight = 5
        education_weight = 5
        overall_weight = 1.0
    if not job_title:
        flash('Please provide a job title', 'danger')
        return redirect(url_for('new_job'))
    job = Job(
        title=job_title,
        description=job_description,
        skills_weight=skills_weight,
        experience_weight=experience_weight,
        education_weight=education_weight,
        overall_weight=overall_weight
    )
    db.session.add(job)
    db.session.flush()
    criteria_names = request.form.getlist('criteria_name[]')
    criteria_descriptions = request.form.getlist('criteria_description[]')
    criteria_weights = request.form.getlist('criteria_weight[]')
    for i, (name, desc, weight_str) in enumerate(zip(criteria_names, criteria_descriptions, criteria_weights)):
        if not name.strip():
            continue
        try:
            weight = float(weight_str)
        except ValueError:
            weight = 1.0
        criteria = ScoringCriteria(
            job_id=job.id,
            name=name.strip(),
            description=desc.strip(),
            weight=weight
        )
        db.session.add(criteria)
    db.session.commit()
    logger.info(f'Created job: {job_title} (ID: {job.id})')
    flash(f'Job "{job_title}" created successfully', 'success')
    return redirect(url_for('upload_for_job', job_id=job.id))

@app.route('/jobs/<int:job_id>/upload')
def upload_for_job(job_id):
    job = Job.query.get_or_404(job_id)
    criteria = ScoringCriteria.query.filter_by(job_id=job_id).all()
    llm_status, llm_message = test_llm_connection()
    return render_template('upload_for_job.html', 
                          job=job,
                          criteria=criteria,
                          llm_status=llm_status,
                          llm_message=llm_message)

@app.route('/jobs/<int:job_id>/upload', methods=['POST'])
def upload_files_for_job(job_id):
    job = Job.query.get_or_404(job_id)
    if 'files[]' not in request.files:
        return jsonify({'error': 'No files selected'}), 400
    files = request.files.getlist('files[]')
    if not files or files[0].filename == '':
        return jsonify({'error': 'No files selected'}), 400
    session_id = str(uuid.uuid4())
    valid_files = []
    for file in files:
        if file and file.filename:
            if allowed_file(file.filename):
                original_filename = str(file.filename)
                filename = secure_filename(original_filename)
                unique_filename = f"{session_id}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)
                cv = CV(
                    filename=unique_filename,
                    original_filename=original_filename,
                    job_id=job_id,
                    status='pending'
                )
                db.session.add(cv)
                valid_files.append((cv.id, filename, file_path))
            else:
                return jsonify({'error': f'File {file.filename} has an unsupported format'}), 400
        else:
            return jsonify({'error': 'One or more files were invalid'}), 400
    db.session.commit()
    if not valid_files:
        return jsonify({'error': 'No valid files were uploaded'}), 400
    processing_jobs[session_id] = {
        'status': 'processing',
        'total': len(valid_files),
        'completed': 0,
        'results': {},
        'job_title': job.title,
        'job_id': job_id
    }
    process_thread = threading.Thread(
        target=process_cv_batch,
        args=(valid_files, session_id, job.title, processing_jobs)
    )
    process_thread.daemon = True
    process_thread.start()
    logger.info(f'Started processing {len(valid_files)} files for job ID {job_id}')
    return jsonify({'status': 'processing', 'session_id': session_id, 'job_id': job_id})

@app.route('/upload', methods=['POST'])
def upload_files():
    job_title = request.form.get('job_title', '').strip()
    if not job_title:
        return jsonify({'error': 'Please specify a job title'}), 400
    if 'files[]' not in request.files:
        return jsonify({'error': 'No files selected'}), 400
    files = request.files.getlist('files[]')
    if not files or files[0].filename == '':
        return jsonify({'error': 'No files selected'}), 400
    job = Job(title=job_title)
    db.session.add(job)
    db.session.commit()
    job_id = job.id
    session_id = str(uuid.uuid4())
    valid_files = []
    for file in files:
        if file and file.filename:
            if allowed_file(file.filename):
                original_filename = str(file.filename)
                filename = secure_filename(original_filename)
                unique_filename = f"{session_id}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)
                cv = CV(
                    filename=unique_filename,
                    original_filename=original_filename,
                    job_id=job_id,
                    status='pending'
                )
                db.session.add(cv)
                valid_files.append((cv.id, filename, file_path))
            else:
                return jsonify({'error': f'File {file.filename} has an unsupported format.'}), 400
        else:
            return jsonify({'error': 'One or more files were invalid'}), 400
    db.session.commit()
    if not valid_files:
        return jsonify({'error': 'No valid files were uploaded'}), 400
    processing_jobs[session_id] = {
        'status': 'processing',
        'total': len(valid_files),
        'completed': 0,
        'results': {},
        'job_title': job_title,
        'job_id': job_id
    }
    process_thread = threading.Thread(
        target=process_cv_batch,
        args=(valid_files, session_id, job_title, processing_jobs)
    )
    process_thread.daemon = True
    process_thread.start()
    logger.info(f'Started processing {len(valid_files)} files for job ID {job_id}')
    return jsonify({'status': 'processing', 'session_id': session_id, 'job_id': job_id})

@app.route('/results/<job_id>')
def results(job_id):
    if job_id in processing_jobs:
        job_data = processing_jobs[job_id]
        return render_template('results.html', 
                             job_id=job_id, 
                             job_title=job_data['job_title'],
                             status=job_data['status'],
                             total=job_data['total'],
                             completed=job_data['completed'],
                             db_job_id=job_data.get('job_id'))
    try:
        db_job_id = int(job_id)
        job = Job.query.get(db_job_id)
        if job:
            total_cvs = CV.query.filter_by(job_id=db_job_id).count()
            completed_cvs = CV.query.filter_by(job_id=db_job_id, status='completed').count()
            active_session = None
            for session_id, session_data in processing_jobs.items():
                if session_data.get('job_id') == db_job_id:
                    active_session = session_id
                    break
            if active_session:
                status = processing_jobs[active_session]['status']
                job_title = processing_jobs[active_session]['job_title']
                total = processing_jobs[active_session]['total']
                completed = processing_jobs[active_session]['completed']
            else:
                status = 'completed' if completed_cvs == total_cvs and total_cvs > 0 else 'unknown'
                job_title = job.title
                total = total_cvs
                completed = completed_cvs
            return render_template('results.html', 
                                 job_id=active_session or job_id,
                                 job_title=job_title,
                                 status=status,
                                 total=total,
                                 completed=completed,
                                 db_job_id=db_job_id)
    except (ValueError, TypeError):
        pass
    flash('Job not found', 'danger')
    return redirect(url_for('index'))

@app.route('/job_status/<job_id>')
def job_status(job_id):
    if job_id in processing_jobs:
        return jsonify(processing_jobs[job_id])
    try:
        db_job_id = int(job_id)
        job = Job.query.get(db_job_id)
        if job:
            total_cvs = CV.query.filter_by(job_id=db_job_id).count()
            completed_cvs = CV.query.filter_by(job_id=db_job_id, status='completed').count()
            error_cvs = CV.query.filter_by(job_id=db_job_id, status='error').count()
            active_session = None
            for session_id, session_data in processing_jobs.items():
                if session_data.get('job_id') == db_job_id:
                    active_session = session_id
                    break
            if active_session:
                return jsonify(processing_jobs[active_session])
            status = 'completed' if completed_cvs + error_cvs == total_cvs and total_cvs > 0 else 'unknown'
            return jsonify({
                'status': status,
                'job_title': job.title,
                'total': total_cvs,
                'completed': completed_cvs,
                'job_id': db_job_id
            })
    except (ValueError, TypeError):
        pass
    return jsonify({'error': 'Job not found'}), 404

@app.route('/job_results/<job_id>')
def job_results(job_id):
    if job_id in processing_jobs:
        job = processing_jobs[job_id]
        if job['status'] != 'completed':
            return jsonify({'error': 'Job still processing'}), 400
        return jsonify({
            'status': 'completed',
            'job_title': job['job_title'],
            'results': job['results'],
            'job_id': job.get('job_id')
        })
    try:
        db_job_id = int(job_id)
        job = Job.query.get(db_job_id)
        if job:
            total_cvs = CV.query.filter_by(job_id=db_job_id).count()
            completed_cvs = CV.query.filter_by(job_id=db_job_id, status='completed').count()
            error_cvs = CV.query.filter_by(job_id=db_job_id, status='error').count()
            if completed_cvs + error_cvs < total_cvs:
                return jsonify({'error': 'Job still processing'}), 400
            from cv_processor import get_job_results_from_db
            results = get_job_results_from_db(db_job_id)
            return jsonify({
                'status': 'completed',
                'job_title': job.title,
                'results': results,
                'job_id': db_job_id
            })
    except (ValueError, TypeError):
        pass
    return jsonify({'error': 'Job not found'}), 404

@app.errorhandler(413)
def too_large(e):
    logger.warning('File upload exceeded 16MB limit')
    if wants_json_response():
        return jsonify({'error': 'File too large. Maximum file size is 16MB.'}), 413
    flash('File too large. Maximum file size is 16MB.', 'danger')
    return redirect(url_for('index'))

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {e}")
    if wants_json_response():
        return jsonify({'error': 'Server error occurred. Please try again later.'}), 500
    flash('Server error occurred. Please try again later.', 'danger')
    return redirect(url_for('index'))

@app.before_request
def cleanup_old_files():
    import time
    current_time = time.time()
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.isfile(file_path) and os.stat(file_path).st_mtime < current_time - 3600:
            try:
                os.remove(file_path)
                logger.info(f"Removed old file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to remove old file {file_path}: {e}")
