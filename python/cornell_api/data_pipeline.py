"""
Cornell Data Pipeline
Transforms Cornell Course Roster API data into Neo4j-compatible format
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import hashlib
import json

from .client import CornellAPIClient, CourseInfo
from .prerequisite_parser import CornellPrerequisiteParser, PrerequisiteParseResult

logger = logging.getLogger(__name__)

class CornellDataPipeline:
    """
    End-to-end pipeline for Cornell course data integration
    
    Workflow:
    1. Fetch courses from Cornell API
    2. Parse prerequisites from text descriptions  
    3. Transform to Neo4j-compatible format
    4. Generate import scripts
    """
    
    def __init__(self, roster: str = "SP25"):
        self.roster = roster
        self.prereq_parser = CornellPrerequisiteParser()
        
        # Statistics tracking
        self.stats = {
            "courses_processed": 0,
            "prerequisites_parsed": 0,
            "prerequisite_edges": 0,
            "parsing_errors": 0,
            "start_time": None,
            "end_time": None
        }
    
    async def fetch_cornell_data(self, subject_filter: Optional[List[str]] = None) -> List[CourseInfo]:
        """Fetch course data from Cornell API with optional subject filtering"""
        logger.info(f"Starting Cornell data fetch for {self.roster}")
        self.stats["start_time"] = datetime.utcnow()
        
        async with CornellAPIClient(self.roster) as client:
            courses = await client.get_all_courses(subject_filter)
            
            # Log API usage stats
            api_stats = client.get_stats()
            logger.info(f"Cornell API usage: {api_stats}")
            
            return courses
    
    def process_prerequisites(self, courses: List[CourseInfo]) -> Dict[str, PrerequisiteParseResult]:
        """Parse prerequisites for all courses"""
        logger.info(f"Processing prerequisites for {len(courses)} courses")
        
        prerequisite_results = {}
        
        for course in courses:
            try:
                if course.prerequisite_text:
                    result = self.prereq_parser.parse_prerequisites(course.prerequisite_text)
                    prerequisite_results[course.course_code] = result
                    
                    if result.prerequisites:
                        self.stats["prerequisites_parsed"] += 1
                        self.stats["prerequisite_edges"] += len(result.prerequisites)
                
                self.stats["courses_processed"] += 1
                
            except Exception as e:
                logger.error(f"Failed to process prerequisites for {course.course_code}: {e}")
                self.stats["parsing_errors"] += 1
        
        logger.info(f"Prerequisite processing complete: {len(prerequisite_results)} courses with prerequisites")
        return prerequisite_results
    
    def transform_to_neo4j_format(self, courses: List[CourseInfo], prerequisite_results: Dict[str, PrerequisiteParseResult]) -> Dict[str, List[Dict[str, Any]]]:
        """Transform Cornell data to Neo4j-compatible format"""
        logger.info("Transforming data to Neo4j format")
        
        # Courses for Neo4j import
        neo4j_courses = []
        prerequisite_edges = []
        course_aliases = []
        
        for course in courses:
            # Transform course data
            neo4j_course = {
                "id": course.course_id,
                "subject": course.subject,
                "catalogNbr": course.catalog_nbr,
                "roster": course.roster,
                "title": course.title_long or course.title_short,
                "titleShort": course.title_short,
                "description": course.description or "",
                "prereq_text": course.prerequisite_text or "",
                "coreq_text": course.corequisite_text or "",
                "outcomes": json.dumps(course.outcomes) if course.outcomes else "",
                "instructors": json.dumps(course.instructors) if course.instructors else "",
                "unitsMin": course.units_min or 0,
                "unitsMax": course.units_max or 0,
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Add prerequisite parsing metadata
            if course.course_code in prerequisite_results:
                result = prerequisite_results[course.course_code]
                neo4j_course.update({
                    "prereq_confidence": result.parsing_confidence,
                    "prereq_courses_mentioned": result.total_courses_mentioned,
                    "prereq_has_complex_logic": result.has_complex_logic
                })
            
            neo4j_courses.append(neo4j_course)
            
            # Create course aliases (e.g., "CS 2110" as alias for the full course)
            alias = {
                "code": course.course_code,
                "course_id": course.course_id,
                "type": "primary"
            }
            course_aliases.append(alias)
            
            # Extract prerequisite edges
            if course.course_code in prerequisite_results:
                result = prerequisite_results[course.course_code]
                edges = self.prereq_parser.extract_prerequisite_edges(course.course_code, result)
                
                for prereq_course, target_course, metadata in edges:
                    # Find prerequisite course ID
                    prereq_course_obj = next((c for c in courses if c.course_code == prereq_course), None)
                    target_course_obj = next((c for c in courses if c.course_code == target_course), None)
                    
                    if prereq_course_obj and target_course_obj:
                        edge = {
                            "from_course_id": prereq_course_obj.course_id,
                            "to_course_id": target_course_obj.course_id,
                            "type": metadata["type"],
                            "confidence": metadata["confidence"],
                            "raw_text": metadata["raw_text"]
                        }
                        prerequisite_edges.append(edge)
        
        self.stats["end_time"] = datetime.utcnow()
        
        return {
            "courses": neo4j_courses,
            "prerequisite_edges": prerequisite_edges,
            "aliases": course_aliases
        }
    
    def generate_neo4j_import_script(self, neo4j_data: Dict[str, List[Dict[str, Any]]], output_dir: str = "data/cornell_current") -> str:
        """Generate Neo4j import script for current Cornell data"""
        import os
        from pathlib import Path
        
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Write CSV files
        courses_csv = output_path / "courses.csv"
        edges_csv = output_path / "prerequisite_edges.csv"
        aliases_csv = output_path / "aliases.csv"
        
        # Write courses CSV
        if neo4j_data["courses"]:
            import csv
            
            # Get all possible fieldnames from all courses (some might have extra fields)
            all_fieldnames = set()
            for course in neo4j_data["courses"]:
                all_fieldnames.update(course.keys())
            
            with open(courses_csv, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=sorted(all_fieldnames))
                writer.writeheader()
                writer.writerows(neo4j_data["courses"])
        
        # Write prerequisite edges CSV
        if neo4j_data["prerequisite_edges"]:
            with open(edges_csv, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=neo4j_data["prerequisite_edges"][0].keys())
                writer.writeheader()
                writer.writerows(neo4j_data["prerequisite_edges"])
        
        # Write aliases CSV
        if neo4j_data["aliases"]:
            with open(aliases_csv, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=neo4j_data["aliases"][0].keys())
                writer.writeheader()
                writer.writerows(neo4j_data["aliases"])
        
        # Generate import script
        import_script = f'''// Cornell Course Navigator - {self.roster} Import Script
// Generated from Cornell Course Roster API on {datetime.utcnow().isoformat()}

// ===== SCHEMA SETUP =====

// Course constraints and indexes
CREATE CONSTRAINT course_id_unique IF NOT EXISTS 
FOR (c:Course) REQUIRE c.id IS UNIQUE;

CREATE INDEX course_subject IF NOT EXISTS 
FOR (c:Course) ON (c.subject);

CREATE INDEX course_catalog IF NOT EXISTS 
FOR (c:Course) ON (c.catalogNbr);

CREATE INDEX course_roster IF NOT EXISTS 
FOR (c:Course) ON (c.roster);

// Alias constraints
CREATE CONSTRAINT alias_code_unique IF NOT EXISTS 
FOR (a:Alias) REQUIRE a.code IS UNIQUE;

// ===== DATA IMPORT =====

// Import courses from Cornell API data
LOAD CSV WITH HEADERS FROM 'file:///cornell_current/courses.csv' AS row
MERGE (c:Course {{id: row.id}})
SET c.subject = row.subject,
    c.catalogNbr = row.catalogNbr,
    c.roster = row.roster,
    c.title = row.title,
    c.titleShort = row.titleShort,
    c.description = row.description,
    c.prereq_text = row.prereq_text,
    c.coreq_text = row.coreq_text,
    c.outcomes = row.outcomes,
    c.instructors = row.instructors,
    c.unitsMin = toInteger(row.unitsMin),
    c.unitsMax = toInteger(row.unitsMax),
    c.prereq_confidence = toFloat(row.prereq_confidence),
    c.prereq_courses_mentioned = toInteger(row.prereq_courses_mentioned),
    c.prereq_has_complex_logic = toBoolean(row.prereq_has_complex_logic),
    c.created_at = row.created_at;

// Import course aliases
LOAD CSV WITH HEADERS FROM 'file:///cornell_current/aliases.csv' AS row
MERGE (a:Alias {{code: row.code}})
WITH a, row
MATCH (c:Course {{id: row.course_id}})
MERGE (c)-[:HAS_ALIAS]->(a)
SET a.type = row.type;

// Import prerequisite relationships
LOAD CSV WITH HEADERS FROM 'file:///cornell_current/prerequisite_edges.csv' AS row
MATCH (from_course:Course {{id: row.from_course_id}})
MATCH (to_course:Course {{id: row.to_course_id}})
MERGE (from_course)-[r:REQUIRES]->(to_course)
SET r.type = row.type,
    r.confidence = toFloat(row.confidence),
    r.raw_text = row.raw_text;

// ===== VALIDATION QUERIES =====

// Course count by subject
MATCH (c:Course)
RETURN c.subject, count(c) as course_count
ORDER BY course_count DESC LIMIT 20;

// Prerequisite statistics
MATCH ()-[r:REQUIRES]->()
RETURN r.type, count(*) as count, avg(r.confidence) as avg_confidence
ORDER BY count DESC;

// Most connected courses
MATCH (c:Course)
WITH c, size([(c)-[:REQUIRES]->() | 1]) as prereqs_required,
     size([(c)<-[:REQUIRES]-() | 1]) as courses_unlock
WHERE prereqs_required > 0 OR courses_unlock > 0
RETURN c.subject + " " + c.catalogNbr as course_code, 
       c.title, prereqs_required, courses_unlock
ORDER BY (prereqs_required + courses_unlock) DESC LIMIT 20;
'''
        
        # Write import script
        script_path = output_path / "import_script.cypher"
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(import_script)
        
        logger.info(f"Generated Neo4j import files in {output_path}")
        logger.info(f"  - Courses: {len(neo4j_data['courses'])}")
        logger.info(f"  - Prerequisite edges: {len(neo4j_data['prerequisite_edges'])}")
        logger.info(f"  - Aliases: {len(neo4j_data['aliases'])}")
        
        return str(script_path)
    
    async def run_full_pipeline(self, subject_filter: Optional[List[str]] = None, output_dir: str = "data/cornell_current") -> Dict[str, Any]:
        """
        Run the complete Cornell data integration pipeline
        
        Args:
            subject_filter: Optional list of subjects to process (e.g., ['CS', 'MATH'])
            output_dir: Directory to save Neo4j import files
            
        Returns:
            Pipeline results and statistics
        """
        logger.info(f"Starting Cornell data pipeline for {self.roster}")
        
        try:
            # Step 1: Fetch course data from Cornell API
            courses = await self.fetch_cornell_data(subject_filter)
            
            if not courses:
                raise Exception("No courses fetched from Cornell API")
            
            # Step 2: Process prerequisites
            prerequisite_results = self.process_prerequisites(courses)
            
            # Step 3: Transform to Neo4j format
            neo4j_data = self.transform_to_neo4j_format(courses, prerequisite_results)
            
            # Step 4: Generate import files
            import_script_path = self.generate_neo4j_import_script(neo4j_data, output_dir)
            
            # Calculate final statistics
            pipeline_duration = (self.stats["end_time"] - self.stats["start_time"]).total_seconds()
            
            results = {
                "success": True,
                "roster": self.roster,
                "courses_fetched": len(courses),
                "subjects_processed": len(set(c.subject for c in courses)),
                "prerequisites_parsed": self.stats["prerequisites_parsed"],
                "prerequisite_edges": len(neo4j_data["prerequisite_edges"]),
                "pipeline_duration_seconds": pipeline_duration,
                "import_script_path": import_script_path,
                "output_directory": output_dir,
                "statistics": self.stats
            }
            
            logger.info(f"Cornell data pipeline completed successfully: {results}")
            return results
            
        except Exception as e:
            logger.error(f"Cornell data pipeline failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "statistics": self.stats
            }

# Convenience function for quick testing
async def fetch_cornell_courses_quick_test(subjects: List[str] = ["CS"]) -> Dict[str, Any]:
    """Quick test function for Cornell API integration"""
    pipeline = CornellDataPipeline("SP25")
    return await pipeline.run_full_pipeline(subject_filter=subjects)