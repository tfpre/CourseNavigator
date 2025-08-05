import requests
import time
import json
import gzip
import hashlib
import os
import random
from pathlib import Path
from tqdm import tqdm
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log
import logging

BASE_URL = "https://classes.cornell.edu/api/2.0"
HEADERS = {"User-Agent": "Cornell-Course-Navigator-Project/1.0"}
RAW_DATA_DIR = Path("data/raw")
STATE_FILE = Path("data/scraper_state.json")
RATE_LIMIT_DELAY = float(os.getenv("SCRAPER_RATE_DELAY", "1.1"))

session = requests.Session()
session.headers.update(HEADERS)

logging.basicConfig(level=logging.INFO)

@retry(
    stop=stop_after_attempt(5),  # Stop after 5 failed attempts
    wait=wait_exponential(multiplier=1.2, min=1, max=10),  # Exponential backoff with base rate limiting
    before_sleep=before_sleep_log(logging.getLogger(__name__), logging.INFO),
    reraise=True
)
def make_request(endpoint: str, params: dict = None) -> dict:
    """Makes a GET request with automatic retries on failure."""
    response = session.get(f"{BASE_URL}/{endpoint}.json", params=params, timeout=30)
    response.raise_for_status()
    # No manual sleep - tenacity wait parameter handles all delays
    return response.json()

def calculate_roster_hash(rosters: list) -> str:
    """Calculate a hash of the roster list for state validation."""
    roster_str = json.dumps(sorted(rosters), sort_keys=True)
    return hashlib.sha256(roster_str.encode()).hexdigest()[:12]

def save_state(roster: str, subject_index: int, roster_hash: str):
    """Saves the current progress to the state file."""
    state = {
        "last_completed_roster": roster, 
        "last_completed_subject_index": subject_index,
        "roster_hash": roster_hash
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def load_state() -> dict:
    """Loads progress from the state file if it exists."""
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"last_completed_roster": None, "last_completed_subject_index": -1, "roster_hash": None}

def main():
    logging.info("Starting Hardened Cornell Course Roster Scrape...")
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()

    logging.info("Fetching available rosters...")
    rosters_data = make_request("config/rosters")
    rosters = [r['slug'] for r in rosters_data['data']['rosters']]
    
    # Calculate roster hash for state validation
    current_roster_hash = calculate_roster_hash(rosters)
    
    # Check if we can resume from previous state
    start_roster_index = 0
    if (state["last_completed_roster"] in rosters and 
        state.get("roster_hash") == current_roster_hash):
        start_roster_index = rosters.index(state["last_completed_roster"])
        logging.info(f"Resuming from roster {state['last_completed_roster']} (index {start_roster_index})")
    elif state["last_completed_roster"] is not None:
        logging.warning("Roster list changed since last run. Starting fresh.")

    logging.info("Building roster-subject map...")
    # (For simplicity, we'll rebuild this map each time, but it could be cached)
    roster_subject_map = {r: [s['value'] for s in make_request("config/subjects", {"roster": r})['data']['subjects']] for r in tqdm(rosters, desc="Mapping Subjects")}

    # Main scraping loop with resume logic
    for i in range(start_roster_index, len(rosters)):
        roster = rosters[i]
        subjects = roster_subject_map[roster]
        
        start_subject_index = 0
        if (roster == state["last_completed_roster"] and 
            state.get("roster_hash") == current_roster_hash):
            start_subject_index = state["last_completed_subject_index"] + 1

        for j in range(start_subject_index, len(subjects)):
            subject = subjects[j]
            logging.info(f"Fetching: {roster} -> {subject} ({j+1}/{len(subjects)})")
            
            # Use gzipped files for storage efficiency
            file_path = RAW_DATA_DIR / f"{roster}_{subject}.json.gz"
            if file_path.exists():
                continue

            class_data = make_request("search/classes", {"roster": roster, "subject": subject})
            if class_data and class_data.get('status') == 'success':
                with gzip.open(file_path, 'wt', encoding='utf-8') as f:
                    json.dump(class_data, f)
            
            # Checkpoint after every successful subject download
            save_state(roster, j, current_roster_hash)
            
            # Add jitter to avoid pattern detection (polite scraping)
            time.sleep(RATE_LIMIT_DELAY + random.uniform(0, 0.2))
            
        # After a roster is fully completed, reset subject index for the next one
        save_state(roster, -1, current_roster_hash)

    logging.info("Scraping complete.")

if __name__ == "__main__":
    main()