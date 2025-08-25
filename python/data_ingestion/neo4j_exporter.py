"""
Neo4j Exporter for Cornell Course Data
Extends the existing data_ingestion pipeline with Neo4j export capability
"""

import csv
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from .models import CleanCourse

logger = logging.getLogger(__name__)

class Neo4jExporter:
    """Export CleanCourse data to Neo4j-compatible CSV and Cypher files"""
    
    def __init__(self, output_dir: str = "data/neo4j_import"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # File paths
        self.courses_csv = self.output_dir / "courses.csv"
        self.prerequisite_edges_csv = self.output_dir / "prerequisite_edges.csv"
        self.aliases_csv = self.output_dir / "aliases.csv"
        self.import_script = self.output_dir / "import_script.cypher"
    
    def export_courses_to_neo4j(self, courses: List[CleanCourse]) -> Dict[str, Any]:
        """
        Export CleanCourse data to Neo4j import format
        
        Returns statistics about the export
        """
        logger.info(f"Exporting {len(courses)} courses to Neo4j format")
        
        # Transform courses to Neo4j format
        neo4j_courses = []
        prerequisite_edges = []
        course_aliases = []
        
        # Build course lookup for prerequisite resolution
        course_lookup = {c.subject + " " + c.catalog_nbr: c for c in courses}
        
        for course in courses:
            # Transform course data
            neo4j_course = {
                "id": course.id,
                "subject": course.subject,
                "catalogNbr": course.catalog_nbr,
                "roster": course.roster,
                "title": course.title,
                "titleShort": course.title[:100] if len(course.title) > 100 else course.title,
                "description": course.description_text or "",
                "prereq_text": course.prerequisite_text or "",
                "coreq_text": "",  # Not in current model but keeping for compatibility
                "outcomes": "",    # Not in current model
                "instructors": json.dumps([m.instructor for m in course.meetings if m.instructor]),
                "unitsMin": float(course.units_min),  # Ensure float for fractional credits
                "unitsMax": float(course.units_max),  # Ensure float for fractional credits
                "created_at": datetime.utcnow().isoformat(),
                "course_code": f"{course.subject} {course.catalog_nbr}"
            }
            
            # Add prerequisite parsing metadata if available
            if hasattr(course, 'prereq_confidence') and course.prereq_confidence is not None:
                neo4j_course["prereq_confidence"] = course.prereq_confidence
            else:
                neo4j_course["prereq_confidence"] = 0.0
                
            # Extract prerequisite courses mentioned (simple count)
            prereq_courses_mentioned = 0
            has_complex_logic = False
            if course.prerequisite_text:
                # Simple heuristic: count course code patterns
                import re
                course_pattern = r'\b[A-Z]{2,5}\s+\d{4}\b'
                prereq_courses_mentioned = len(re.findall(course_pattern, course.prerequisite_text))
                has_complex_logic = any(word in course.prerequisite_text.lower() 
                                      for word in ['and', 'or', 'either', 'both', 'permission'])
            
            neo4j_course["prereq_courses_mentioned"] = prereq_courses_mentioned
            neo4j_course["prereq_has_complex_logic"] = has_complex_logic
            
            neo4j_courses.append(neo4j_course)
            
            # Create course alias
            alias = {
                "code": f"{course.subject} {course.catalog_nbr}",
                "course_id": course.id,
                "type": "primary"
            }
            course_aliases.append(alias)
            
            # Add cross-listing aliases
            for cross_listing in course.cross_listings:
                cross_alias = {
                    "code": cross_listing,
                    "course_id": course.id, 
                    "type": "cross_listing"
                }
                course_aliases.append(cross_alias)
            
            # Extract prerequisite edges from AST if available
            if hasattr(course, 'prereq_ast') and course.prereq_ast:
                edges = self._extract_edges_from_ast(course, course.prereq_ast, course_lookup)
                prerequisite_edges.extend(edges)
        
        # Write CSV files
        self._write_courses_csv(neo4j_courses)
        self._write_prerequisite_edges_csv(prerequisite_edges)
        self._write_aliases_csv(course_aliases)
        
        # Generate import script
        self._write_import_script()
        
        stats = {
            "courses_exported": len(neo4j_courses),
            "prerequisite_edges": len(prerequisite_edges), 
            "aliases_created": len(course_aliases),
            "subjects": len(set(c["subject"] for c in neo4j_courses)),
            "output_directory": str(self.output_dir)
        }
        
        logger.info(f"Neo4j export complete: {stats}")
        return stats
    
    def _extract_edges_from_ast(self, course: CleanCourse, ast: Dict[str, Any], 
                               course_lookup: Dict[str, CleanCourse]) -> List[Dict[str, Any]]:
        """Extract prerequisite edges from AST structure"""
        edges = []
        
        if not ast or "courses" not in ast:
            return edges
            
        for prereq_code in ast["courses"]:
            if prereq_code in course_lookup:
                prereq_course = course_lookup[prereq_code]
                edge = {
                    "from_course_id": prereq_course.id,
                    "to_course_id": course.id,
                    "type": ast.get("type", "PREREQUISITE").lower(),
                    "confidence": course.prereq_confidence if hasattr(course, 'prereq_confidence') else 0.5,
                    "raw_text": course.prerequisite_text or ""
                }
                edges.append(edge)
                
        return edges
    
    def _write_courses_csv(self, courses: List[Dict[str, Any]]):
        """Write courses to CSV file"""
        if not courses:
            return
            
        with open(self.courses_csv, 'w', newline='', encoding='utf-8') as f:
            # Get all fieldnames dynamically
            all_fieldnames = set()
            for course in courses:
                all_fieldnames.update(course.keys())
                
            writer = csv.DictWriter(f, fieldnames=sorted(all_fieldnames))
            writer.writeheader()
            writer.writerows(courses)
            
        logger.info(f"Wrote {len(courses)} courses to {self.courses_csv}")
    
    def _write_prerequisite_edges_csv(self, edges: List[Dict[str, Any]]):
        """Write prerequisite edges to CSV file"""
        if not edges:
            # Create empty file with headers
            with open(self.prerequisite_edges_csv, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=["from_course_id", "to_course_id", "type", "confidence", "raw_text"])
                writer.writeheader()
            return
            
        with open(self.prerequisite_edges_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=edges[0].keys())
            writer.writeheader()
            writer.writerows(edges)
            
        logger.info(f"Wrote {len(edges)} prerequisite edges to {self.prerequisite_edges_csv}")
    
    def _write_aliases_csv(self, aliases: List[Dict[str, Any]]):
        """Write course aliases to CSV file"""
        if not aliases:
            return
            
        with open(self.aliases_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=aliases[0].keys())
            writer.writeheader()
            writer.writerows(aliases)
            
        logger.info(f"Wrote {len(aliases)} aliases to {self.aliases_csv}")
    
    def _write_import_script(self):
        """Generate Neo4j import script"""
        import_script = f'''// Cornell Course Navigator - Neo4j Import Script
// Generated from Cornell Course Data on {datetime.utcnow().isoformat()}

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

CREATE INDEX course_code IF NOT EXISTS 
FOR (c:Course) ON (c.course_code);

// Alias constraints
CREATE CONSTRAINT alias_code_unique IF NOT EXISTS 
FOR (a:Alias) REQUIRE a.code IS UNIQUE;

// ===== DATA IMPORT =====

// Import courses
LOAD CSV WITH HEADERS FROM 'file:///neo4j_import/courses.csv' AS row
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
    c.course_code = row.course_code,
    c.created_at = row.created_at;

// Import course aliases
LOAD CSV WITH HEADERS FROM 'file:///neo4j_import/aliases.csv' AS row
MERGE (a:Alias {{code: row.code}})
WITH a, row
MATCH (c:Course {{id: row.course_id}})
MERGE (c)-[:HAS_ALIAS]->(a)
SET a.type = row.type;

// Import prerequisite relationships
LOAD CSV WITH HEADERS FROM 'file:///neo4j_import/prerequisite_edges.csv' AS row
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

// Most connected courses (by prerequisite requirements)
MATCH (c:Course)
WITH c, size([(c)-[:REQUIRES]->() | 1]) as prereqs_required,
     size([(c)<-[:REQUIRES]-() | 1]) as courses_unlock
WHERE prereqs_required > 0 OR courses_unlock > 0
RETURN c.course_code, c.title, prereqs_required, courses_unlock
ORDER BY (prereqs_required + courses_unlock) DESC LIMIT 20;

// Total counts
MATCH (c:Course) 
WITH count(c) as total_courses
MATCH ()-[r:REQUIRES]->()
WITH total_courses, count(r) as total_prereqs
MATCH (a:Alias)
RETURN total_courses, total_prereqs, count(a) as total_aliases;
'''
        
        with open(self.import_script, 'w', encoding='utf-8') as f:
            f.write(import_script)
            
        logger.info(f"Generated Neo4j import script: {self.import_script}")