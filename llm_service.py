import requests
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

LLM_API_URL = "http://192.168.111.215:11434/api/generate"

def create_session_with_retries():
    """Create a requests session with retry logic."""
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
    session.mount("http://", HTTPAdapter(max_retries=retries))
    return session

def test_llm_connection():
    """Test connection to the local Ollama LLM."""
    try:
        session = create_session_with_retries()
        response = session.post(
            LLM_API_URL,
            json={"model": "llama3", "prompt": "Test connection"},
            timeout=10  # Increased timeout
        )
        if response.status_code == 200:
            logger.info("Successfully connected to Ollama LLM")
            return True, "Connected to local LLM (Llama 3)"
        else:
            logger.error(f"LLM connection failed: {response.status_code} - {response.text}")
            return False, f"LLM connection failed: {response.status_code}"
    except requests.RequestException as e:
        logger.error(f"LLM connection error: {e}")
        return False, f"LLM connection error: {str(e)}"

def process_cv_text(cv_text, job_title):
    """Send CV text to Ollama LLM for processing."""
    try:
        session = create_session_with_retries()
        prompt = f"Analyze this CV for the job '{job_title}':\n{cv_text}"
        response = session.post(
            LLM_API_URL,
            json={"model": "llama3", "prompt": prompt},
            timeout=30
        )
        if response.status_code == 200:
            result = response.json()
            logger.info(f"CV processed successfully for job: {job_title}")
            return result.get("response", {})
        else:
            logger.error(f"CV processing failed: {response.status_code} - {response.text}")
            return None
    except requests.RequestException as e:
        logger.error(f"CV processing error: {e}")
        return None