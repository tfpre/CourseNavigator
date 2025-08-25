import requests
import time
import json
import gzip
import hashlib
import os
import random
import argparse
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

def get_current_roster():
    """Get the most recent roster (current semester)"""
    rosters_data = make_request("config/rosters")
    rosters = [r['slug'] for r in rosters_data['data']['rosters']]
    # Cornell roster format: SP25, FA24, etc. Rosters are in chronological order, get the LAST one
    return rosters[-1] if rosters else None

def scrape_cornell_data(target_rosters=None, subject_filter=None):
    """
    Unified Cornell data scraping with flexible filtering
    
    Args:
        target_rosters: List of rosters to scrape (None = all available)
        subject_filter: List of subjects to scrape (None = all subjects)
    """
    logging.info("Starting Cornell Course Roster Scrape...")
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()

    logging.info("Fetching available rosters...")
    rosters_data = make_request("config/rosters")
    all_rosters = [r['slug'] for r in rosters_data['data']['rosters']]
    
    # Apply roster filtering
    if target_rosters:
        rosters = [r for r in all_rosters if r in target_rosters]
        logging.info(f"Filtering to rosters: {rosters}")
    else:
        rosters = all_rosters
        logging.info(f"Scraping all available rosters: {rosters}")
    
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
    roster_subject_map = {}
    for r in tqdm(rosters, desc="Mapping Subjects"):
        all_subjects = [s['value'] for s in make_request("config/subjects", {"roster": r})['data']['subjects']]
        # Apply subject filtering if specified
        if subject_filter:
            filtered_subjects = [s for s in all_subjects if s in subject_filter]
            roster_subject_map[r] = filtered_subjects
            logging.info(f"Roster {r}: {len(filtered_subjects)} subjects (filtered from {len(all_subjects)})")
        else:
            roster_subject_map[r] = all_subjects
            logging.info(f"Roster {r}: {len(all_subjects)} subjects")

    # Main scraping loop with resume logic
    total_files_created = 0
    for i in range(start_roster_index, len(rosters)):
        roster = rosters[i]
        subjects = roster_subject_map[roster]
        
        if not subjects:
            logging.warning(f"No subjects found for roster {roster} (filtered: {subject_filter})")
            continue
        
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
                logging.info(f"  ✓ Already exists: {file_path.name}")
                continue

            class_data = make_request("search/classes", {"roster": roster, "subject": subject})
            if class_data and class_data.get('status') == 'success':
                with gzip.open(file_path, 'wt', encoding='utf-8') as f:
                    json.dump(class_data, f)
                logging.info(f"  ✓ Saved: {file_path.name}")
                total_files_created += 1
            
            # Checkpoint after every successful subject download
            save_state(roster, j, current_roster_hash)
            
            # Add jitter to avoid pattern detection (polite scraping)
            time.sleep(RATE_LIMIT_DELAY + random.uniform(0, 0.2))
            
        # After a roster is fully completed, reset subject index for the next one
        save_state(roster, -1, current_roster_hash)

    logging.info(f"Scraping complete. Created {total_files_created} new files.")
    return total_files_created

def main():
    """Main function with command line argument support"""
    parser = argparse.ArgumentParser(description="Cornell Course Roster Scraper with Test/Full Mode Support")
    parser.add_argument("--test-mode", action="store_true", 
                       help="Test mode: Current roster, CS+MATH subjects only")
    parser.add_argument("--full-mode", action="store_true",
                       help="Full mode: Current roster, all subjects") 
    parser.add_argument("--roster", type=str,
                       help="Specific roster to scrape (e.g., SP25, FA24)")
    parser.add_argument("--subjects", type=str,
                       help="Comma-separated list of subjects (e.g., CS,MATH,PHYS)")
    
    args = parser.parse_args()
    
    # Determine scraping parameters
    if args.test_mode:
        current_roster = get_current_roster()
        target_rosters = [current_roster] if current_roster else None
        subject_filter = ["CS", "MATH"]
        logging.info(f"🧪 TEST MODE: Roster {current_roster}, Subjects: {subject_filter}")
    elif args.full_mode:
        current_roster = get_current_roster() 
        target_rosters = [current_roster] if current_roster else None
        subject_filter = None
        logging.info(f"🌐 FULL MODE: Roster {current_roster}, All subjects")
    else:
        # Custom parameters
        target_rosters = [args.roster] if args.roster else None
        subject_filter = args.subjects.split(",") if args.subjects else None
        logging.info(f"📋 CUSTOM MODE: Rosters {target_rosters}, Subjects: {subject_filter}")
    
    # Run scraping
    files_created = scrape_cornell_data(target_rosters, subject_filter)

if __name__ == "__main__":
    main()