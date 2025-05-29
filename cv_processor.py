from models import db, CV
from llm_service import process_cv_text
from file_parser import parse_cv_file  # Make sure you have this implemented!
import logging

logger = logging.getLogger(__name__)

def process_cv_batch(valid_files, session_id, job_title, processing_jobs):
    for cv_id, filename, file_path in valid_files:
        try:
            # Use actual CV file parsing logic
            cv_text = parse_cv_file(file_path)  # This should extract text from PDF/DOCX/DOC/TXT
            result = process_cv_text(cv_text, job_title)
            if result:
                processing_jobs[session_id]['results'][filename] = result
                processing_jobs[session_id]['completed'] += 1
                with db.session.begin():
                    cv = CV.query.get(cv_id)
                    cv.status = 'completed'
            else:
                with db.session.begin():
                    cv = CV.query.get(cv_id)
                    cv.status = 'error'
        except Exception as e:
            logger.error(f"Error processing CV {filename}: {e}")
            with db.session.begin():
                cv = CV.query.get(cv_id)
                cv.status = 'error'
    processing_jobs[session_id]['status'] = 'completed'

def get_job_results_from_db(job_id):
    cvs = CV.query.filter_by(job_id=job_id).all()
    return {cv.filename: {"status": cv.status} for cv in cvs}