import random
import csv
import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Any
# from python.data_ingestion.processor import load_clean_courses  # No longer needed - using streaming approach

logging.basicConfig(level=logging.INFO)

def extract_prereq_data(sample_size: int = 2000) -> List[Dict[str, Any]]:
    """Extract prerequisite strings and course IDs from existing clean course data using streaming approach"""
    # Use streaming approach to avoid loading all courses into memory
    import json
    from pathlib import Path
    from python.data_ingestion.models import CleanCourse
    
    output_file = Path("data/clean/courses.jsonl")
    if not output_file.exists():
        logging.error(f"Clean data file {output_file} does not exist. Run process_all_files() first.")
        return []
    
    # Stream courses and collect those with prerequisites
    courses_with_prereqs = []
    total_courses = 0
    
    with open(output_file, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            total_courses += 1
            try:
                course_data = json.loads(line.strip())
                # Check if course has prerequisite text
                if course_data.get('prerequisite_text') and course_data.get('prerequisite_text').strip():
                    course_info = {
                        "course_id": course_data.get('id'),
                        "prereq_text": course_data.get('prerequisite_text'),
                        "title": course_data.get('title')
                    }
                    courses_with_prereqs.append(course_info)
                    
                    # Early termination if we already have enough samples
                    if len(courses_with_prereqs) >= sample_size * 2:  # Collect 2x samples for better randomness
                        break
                        
            except Exception as e:
                logging.warning(f"Could not parse line {i+1}: {e}")
                continue
    
    logging.info(f"Found {len(courses_with_prereqs)} courses with prerequisites from {total_courses} total courses")
    
    # Sample if we have more than requested
    if len(courses_with_prereqs) > sample_size:
        random.seed(42)  # For reproducible results
        sampled = random.sample(courses_with_prereqs, sample_size)
        logging.info(f"Sampled {sample_size} courses for validation")
        return sampled
    else:
        logging.info(f"Using all {len(courses_with_prereqs)} courses with prerequisites")
        return courses_with_prereqs

def regex_parse_prereq(text: str) -> Dict[str, Any]:
    """
    Simple regex parser for course codes like 'CS 2110'
    Returns success, found courses, and confidence
    """
    if not text or not text.strip():
        return {
            'success': False,
            'courses_found': [],
            'confidence': 0.0,
            'pattern_matches': []
        }
    
    # Primary pattern: Department + Number (e.g., "CS 2110", "MATH 1920")
    primary_pattern = r'([A-Z]{2,5})\s+(\d{3,4})'
    primary_matches = re.findall(primary_pattern, text)
    
    # Secondary patterns for edge cases
    # Pattern for ranges: "CS 2110-2800" 
    range_pattern = r'([A-Z]{2,5})\s+(\d{3,4})-(\d{3,4})'
    range_matches = re.findall(range_pattern, text)
    
    # Pattern for courses with letters: "CS 2110A"
    letter_pattern = r'([A-Z]{2,5})\s+(\d{3,4}[A-Z])'
    letter_matches = re.findall(letter_pattern, text)
    
    all_courses = []
    
    # Process primary matches
    for subj, num in primary_matches:
        all_courses.append(f"{subj} {num}")
    
    # Process range matches (expand ranges)
    for subj, start, end in range_matches:
        start_num = int(start)
        end_num = int(end)
        # Expand range to individual course numbers
        for num in range(start_num, end_num + 1):
            all_courses.append(f"{subj} {num}")
    
    # Process letter matches
    for subj, num in letter_matches:
        all_courses.append(f"{subj} {num}")
    
    # Calculate confidence based on content analysis
    confidence = calculate_confidence(text, all_courses)
    
    return {
        'success': len(all_courses) > 0,
        'courses_found': all_courses,
        'confidence': confidence,
        'pattern_matches': {
            'primary': len(primary_matches),
            'range': len(range_matches), 
            'letter': len(letter_matches)
        }
    }

def calculate_confidence(text: str, courses_found: List[str]) -> float:
    """
    Calculate confidence score based on text analysis
    Higher confidence for simple, clear prerequisites
    Lower confidence for complex logic or ambiguous text
    """
    if not courses_found:
        return 0.0
    
    text_lower = text.lower()
    
    # Start with base confidence
    confidence = 0.8
    
    # Reduce confidence for complex logic
    if any(word in text_lower for word in ['or', 'and', 'either', 'both']):
        confidence -= 0.2
    
    # Reduce confidence for parentheses (complex grouping)
    if '(' in text or ')' in text:
        confidence -= 0.1
    
    # Reduce confidence for ambiguous terms
    ambiguous_terms = ['permission', 'equivalent', 'placement', 'advisor', 'instructor']
    if any(term in text_lower for term in ambiguous_terms):
        confidence -= 0.3
    
    # Reduce confidence for very long prerequisite strings (likely complex)
    if len(text) > 100:
        confidence -= 0.1
    
    # Increase confidence for simple, single course prerequisites
    if len(courses_found) == 1 and len(text) < 30:
        confidence += 0.1
    
    # Ensure confidence stays in [0, 1] range
    return max(0.0, min(1.0, confidence))

def run_spike(sample_size: int = 2000) -> Dict[str, Any]:
    """
    Run validation spike on prerequisite parsing
    Incorporates criticism #1: Include course_id in CSV export
    """
    logging.info("Starting prerequisite validation spike...")
    
    # Extract prerequisite data
    prereq_data = extract_prereq_data(sample_size)
    
    if not prereq_data:
        logging.error("No prerequisite data found. Run the data processor first.")
        return {"error": "No prerequisite data available"}
    
    # Process each prerequisite string
    results = []
    for item in prereq_data:
        parse_result = regex_parse_prereq(item['prereq_text'])
        
        # Combine course data with parse results
        result_row = {
            'course_id': item['course_id'],           # Criticism #1: Include course ID
            'course_title': item['title'],
            'prereq_text': item['prereq_text'],
            'success': parse_result['success'],
            'courses_found': '; '.join(parse_result['courses_found']),
            'confidence': parse_result['confidence'],
            'primary_matches': parse_result['pattern_matches']['primary'],
            'range_matches': parse_result['pattern_matches']['range'],
            'letter_matches': parse_result['pattern_matches']['letter']
        }
        results.append(result_row)
    
    # Calculate overall metrics
    successful_parses = sum(1 for r in results if r['success'])
    total_parses = len(results)
    recall = successful_parses / total_parses if total_parses > 0 else 0
    
    # Calculate confidence distribution
    high_confidence = sum(1 for r in results if r['confidence'] >= 0.7)
    medium_confidence = sum(1 for r in results if 0.3 <= r['confidence'] < 0.7)
    low_confidence = sum(1 for r in results if r['confidence'] < 0.3)
    
    # Export results to CSV
    output_dir = Path("data")
    output_dir.mkdir(exist_ok=True)
    
    csv_path = output_dir / "spike_results.csv"
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = [
            'course_id', 'course_title', 'prereq_text', 'success', 
            'courses_found', 'confidence', 'primary_matches', 
            'range_matches', 'letter_matches'
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    
    # Generate summary report
    summary = {
        'total_samples': total_parses,
        'successful_parses': successful_parses,
        'recall_percentage': recall * 100,
        'confidence_distribution': {
            'high_confidence': high_confidence,
            'medium_confidence': medium_confidence,
            'low_confidence': low_confidence
        },
        'csv_export_path': str(csv_path)
    }
    
    # Log results
    logging.info(f"Spike Results Summary:")
    logging.info(f"  Total samples: {total_parses}")
    logging.info(f"  Successful parses: {successful_parses}")
    logging.info(f"  Recall: {recall:.2%}")
    logging.info(f"  High confidence (≥0.7): {high_confidence}")
    logging.info(f"  Medium confidence (0.3-0.7): {medium_confidence}")
    logging.info(f"  Low confidence (<0.3): {low_confidence}")
    logging.info(f"  Results exported to: {csv_path}")
    
    return summary

def analyze_failures(csv_path: str = "data/spike_results.csv") -> None:
    """Analyze failed parses to understand common patterns"""
    if not Path(csv_path).exists():
        logging.error(f"CSV file not found: {csv_path}")
        return
    
    failures = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['success'] == 'False' or float(row['confidence']) < 0.3:
                failures.append(row)
    
    logging.info(f"Found {len(failures)} failed/low-confidence parses")
    
    if failures:
        logging.info("Sample failure cases:")
        for i, failure in enumerate(failures[:10]):  # Show first 10
            logging.info(f"  {i+1}. {failure['course_id']}: {failure['prereq_text']}")
    
    return failures

if __name__ == "__main__":
    # Run the validation spike
    summary = run_spike(sample_size=2000)
    
    if "error" not in summary:
        # Analyze failures
        analyze_failures()
        
        # Decision guidance based on recall
        recall = summary['recall_percentage']
        logging.info(f"\nDecision Guidance:")
        if recall >= 75:
            logging.info("✅ Regex recall ≥75% - Use T0 (regex) + T2 (GPT fallback)")
        elif recall >= 50:
            logging.info("⚠️  Regex recall 50-75% - Add T1 (grammar parser)")
        else:
            logging.info("❌ Regex recall <50% - Invest in PEG parser (lark/pyparsing)")
        
        logging.info(f"Next step: Review {summary['csv_export_path']} for failure patterns")