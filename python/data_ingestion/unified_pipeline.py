#!/usr/bin/env python3
"""
Unified Cornell Data Pipeline
Combines scraping + processing + Neo4j export in a single command

This script provides a simple interface to the complete data pipeline:
1. Scrape Cornell API data 
2. Process raw data to clean format
3. Export to Neo4j import files
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_command(cmd, description):
    """Run a command and handle errors"""
    logger.info(f"🔄 {description}")
    logger.info(f"   Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info(f"✅ {description} - SUCCESS")
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    logger.info(f"   {line}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ {description} - FAILED")
        logger.error(f"   Exit code: {e.returncode}")
        if e.stdout:
            logger.error(f"   STDOUT: {e.stdout}")
        if e.stderr:
            logger.error(f"   STDERR: {e.stderr}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Unified Cornell Course Data Pipeline")
    
    # Mode selection
    parser.add_argument("--test-mode", action="store_true",
                       help="Test mode: Current roster, CS+MATH subjects only")
    parser.add_argument("--full-mode", action="store_true", 
                       help="Full mode: Current roster, all subjects")
    
    # Custom parameters
    parser.add_argument("--roster", type=str,
                       help="Specific roster to process (e.g., SP25)")
    parser.add_argument("--subjects", type=str,
                       help="Comma-separated subjects (e.g., CS,MATH)")
    
    # Processing options
    parser.add_argument("--skip-scraping", action="store_true",
                       help="Skip scraping, just process existing raw data")
    parser.add_argument("--skip-neo4j", action="store_true",
                       help="Skip Neo4j export, just create JSONL")
    parser.add_argument("--neo4j-output", type=str, default="data/neo4j_import",
                       help="Neo4j export directory")
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.test_mode and args.full_mode:
        logger.error("Cannot specify both --test-mode and --full-mode")
        sys.exit(1)
    
    logger.info("🚀 Starting Unified Cornell Data Pipeline")
    
    # Step 1: Scraping (if not skipped)
    if not args.skip_scraping:
        scraper_cmd = ["python", "-m", "python.data_ingestion.scraper"]
        
        if args.test_mode:
            scraper_cmd.append("--test-mode")
        elif args.full_mode:
            scraper_cmd.append("--full-mode")
        else:
            if args.roster:
                scraper_cmd.extend(["--roster", args.roster])
            if args.subjects:
                scraper_cmd.extend(["--subjects", args.subjects])
        
        if not run_command(scraper_cmd, "Scraping Cornell course data"):
            logger.error("Pipeline failed at scraping step")
            sys.exit(1)
    else:
        logger.info("⏭️  Skipping scraping step")
    
    # Step 2: Processing and Neo4j Export
    processor_cmd = ["python", "-m", "python.data_ingestion.processor"]
    
    # Add Neo4j export if not skipped
    if not args.skip_neo4j:
        processor_cmd.append("--neo4j")
        if args.neo4j_output:
            processor_cmd.extend(["--neo4j-output", args.neo4j_output])
    
    # Add roster filter if specified
    if args.roster:
        processor_cmd.extend(["--roster", args.roster])
    elif args.test_mode:
        # Test mode - try to infer current roster
        processor_cmd.extend(["--roster", "SP25"])  # Default to SP25 for now
    
    if not run_command(processor_cmd, "Processing courses and exporting to Neo4j"):
        logger.error("Pipeline failed at processing step")
        sys.exit(1)
    
    # Step 3: Summary
    logger.info("🎉 Unified Cornell Data Pipeline Complete!")
    
    if not args.skip_neo4j:
        neo4j_dir = Path(args.neo4j_output)
        if neo4j_dir.exists():
            logger.info(f"📁 Neo4j import files available in: {neo4j_dir}")
            logger.info("   To import into Neo4j:")
            logger.info(f"   1. Copy {neo4j_dir} to your Neo4j import directory")
            logger.info(f"   2. Run the Cypher script: {neo4j_dir}/import_script.cypher")
    
    clean_file = Path("data/clean/courses.jsonl")
    if clean_file.exists():
        logger.info(f"📋 Clean course data available: {clean_file}")
    
    logger.info("✅ Pipeline completed successfully!")

if __name__ == "__main__":
    main()