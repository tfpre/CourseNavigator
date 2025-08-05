import json
import gzip
import re
import logging
from pathlib import Path
from typing import List, Iterator
from tqdm import tqdm
from python.data_ingestion.models import RawClassesResponse, CleanCourse

logging.basicConfig(level=logging.INFO)

RAW_DATA_DIR = Path("data/raw")
CLEAN_DATA_DIR = Path("data/clean")
OUTPUT_FILE = CLEAN_DATA_DIR / "courses.jsonl"

def process_raw_file(file_path: Path) -> Iterator[CleanCourse]:
    """Process a single raw data file and yield CleanCourse objects."""
    # Extract roster from filename using regex for robustness
    match = re.match(r'^([A-Z0-9]+)_(.+)\.json$', file_path.stem)
    if not match:
        logging.warning(f"Could not parse filename: {file_path.name}")
        return
    
    roster = match.group(1)
    
    try:
        with gzip.open(file_path, 'rt', encoding='utf-8') as f:
            raw_data = json.load(f)
            
        # Parse the API response
        api_response = RawClassesResponse(**raw_data)
        raw_courses = api_response.get_courses()
        
        # Transform each raw course to clean course
        for raw_course in raw_courses:
            try:
                clean_course = CleanCourse.from_raw(raw_course, roster)
                yield clean_course
            except Exception as e:
                logging.warning(f"Could not transform course {raw_course.crseId}: {e}")
                continue
                
    except Exception as e:
        logging.error(f"Error processing file {file_path}: {e}")

def process_all_files(limit: int = None) -> int:
    """Process all raw data files and return count of processed courses."""
    CLEAN_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Get all raw data files
    raw_files = list(RAW_DATA_DIR.glob("*.json.gz"))
    if limit:
        raw_files = raw_files[:limit]
    
    course_count = 0
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as output_file:
        for file_path in tqdm(raw_files, desc="Processing files"):
            for clean_course in process_raw_file(file_path):
                # Write to JSONL file with smaller size (exclude None fields)
                output_file.write(clean_course.model_dump_json(exclude_none=True) + '\n')
                course_count += 1
    
    logging.info(f"Processed {course_count} courses and saved to {OUTPUT_FILE}")
    return course_count

def load_clean_courses(limit: int = None) -> List[CleanCourse]:
    """Load clean courses from the JSONL file."""
    courses = []
    
    if not OUTPUT_FILE.exists():
        logging.error(f"Clean data file {OUTPUT_FILE} does not exist. Run process_all_files() first.")
        return courses
    
    with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            try:
                course_data = json.loads(line.strip())
                course = CleanCourse(**course_data)
                courses.append(course)
            except Exception as e:
                logging.warning(f"Could not parse line {i+1}: {e}")
                continue
    
    return courses

def main():
    """Main function to process raw data and create clean dataset."""
    logging.info("Starting data processing...")
    
    # Process all files (or limit for testing)
    course_count = process_all_files(limit=None)
    
    logging.info(f"Successfully processed {course_count} courses")
    
    # Show sample of first 5 courses
    logging.info("Sample of processed courses:")
    sample_courses = load_clean_courses(limit=5)
    for i, course in enumerate(sample_courses):
        logging.info(f"{i+1}. {course.id}: {course.title}")
        if course.description_text:
            logging.info(f"   Description: {course.description_text[:100]}...")
        if course.prerequisite_text:
            logging.info(f"   Prerequisites: {course.prerequisite_text}")

if __name__ == "__main__":
    main()