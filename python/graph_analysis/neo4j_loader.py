"""
Neo4j loader for Cornell Course Navigator.
Implements MERGE operations for idempotent imports (criticism #2).
Transforms clean course data into graph format.
"""

import csv
import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from python.data_ingestion.processor import load_clean_courses
from python.graph_analysis.neo4j_schema import get_schema_queries, get_validation_queries

logging.basicConfig(level=logging.INFO)

def export_courses_to_csv(output_dir: str = "data/neo4j", confidence_threshold: float = 0.35) -> Dict[str, int]:
    """
    Export clean course data to Neo4j-compatible CSV files.
    Returns count of exported records.
    
    Args:
        output_dir: Directory to write CSV files
        confidence_threshold: Minimum confidence for prerequisite edges. 
                            Edges below this threshold are marked as "UNSURE"
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    courses = load_clean_courses()
    logging.info(f"Exporting {len(courses)} courses to CSV files")
    
    # Build performance index for course lookups - O(1) instead of O(N)
    course_index = {}
    for course in courses:
        # Index by (subject, catalog_nbr, roster) for exact matches
        course_index[(course.subject, course.catalog_nbr, course.roster)] = course
        # Also index without roster for cross-semester fallback
        course_index[(course.subject, course.catalog_nbr, None)] = course
    
    # Export courses
    courses_file = output_path / "courses.csv"
    courses_exported = 0
    
    with open(courses_file, 'w', newline='', encoding='utf-8') as f:
        fieldnames = [
            'id', 'subject', 'catalogNbr', 'roster', 'title', 
            'prereq_text', 'prereq_ast', 'prereq_confidence',
            'unitsMin', 'unitsMax'
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for course in courses:
            writer.writerow({
                'id': course.id,
                'subject': course.subject,
                'catalogNbr': course.catalog_nbr,
                'roster': course.roster,
                'title': course.title,
                'prereq_text': course.prerequisite_text or '',
                'prereq_ast': json.dumps(course.prereq_ast) if course.prereq_ast else '',
                'prereq_confidence': course.prereq_confidence or 0.0,
                'unitsMin': course.units_min,
                'unitsMax': course.units_max
            })
            courses_exported += 1
    
    # Export aliases (cross-listings)
    aliases_file = output_path / "aliases.csv"
    aliases_exported = 0
    
    with open(aliases_file, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['code', 'course_id']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for course in courses:
            for alias in course.cross_listings:
                writer.writerow({
                    'code': alias,
                    'course_id': course.id
                })
                aliases_exported += 1
    
    # Export prerequisite edges with deduplication using fast lookup
    edges_file = output_path / "prerequisite_edges.csv"
    missing_courses = []  # Track missing courses for debugging
    
    # Collect all edges first to deduplicate
    all_edges = []
    for course in courses:
        if course.prereq_ast and course.prereq_ast.get('courses'):
            relationship_type = course.prereq_ast.get('type', 'MANDATORY')
            confidence = course.prereq_confidence or 0.0
            
            # Apply confidence threshold - mark low-confidence edges as UNSURE
            if confidence < confidence_threshold:
                relationship_type = 'UNSURE'
            
            for prereq_code in course.prereq_ast['courses']:
                # Use fast lookup with O(1) performance
                prereq_course = find_course_by_code_fast(course_index, prereq_code, course.roster)
                if prereq_course:
                    edge = {
                        'from_course_id': course.id,
                        'to_course_id': prereq_course.id,
                        'type': relationship_type,
                        'confidence': round(confidence, 3)  # Store actual confidence score
                    }
                    all_edges.append(edge)
                else:
                    # Track missing course for debugging
                    missing_courses.append({
                        'course_id': course.id,
                        'missing_prereq': prereq_code,
                        'roster': course.roster
                    })
                    logging.warning(f"Could not find prerequisite course {prereq_code} for {course.id}")
    
    # Deduplicate edges using a set of tuples (include confidence in deduplication)
    unique_edges = []
    seen_edges = set()
    for edge in all_edges:
        edge_tuple = (edge['from_course_id'], edge['to_course_id'], edge['type'], edge['confidence'])
        if edge_tuple not in seen_edges:
            seen_edges.add(edge_tuple)
            unique_edges.append(edge)
    
    # Write deduplicated edges to CSV
    edges_exported = 0
    with open(edges_file, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['from_course_id', 'to_course_id', 'type', 'confidence']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for edge in unique_edges:
            writer.writerow(edge)
            edges_exported += 1
    
    # Count edge types for reporting
    edge_type_counts = {}
    for edge in unique_edges:
        edge_type = edge['type']
        edge_type_counts[edge_type] = edge_type_counts.get(edge_type, 0) + 1
    
    logging.info(f"Deduplicated {len(all_edges)} edges to {edges_exported} unique edges")
    logging.info(f"Edge type distribution: {edge_type_counts}")
    
    if 'UNSURE' in edge_type_counts:
        logging.info(f"Marked {edge_type_counts['UNSURE']} edges as UNSURE due to confidence < {confidence_threshold}")
    
    # Export missing courses for debugging
    missing_courses_file = output_path / "missing_courses.csv"
    missing_exported = 0
    if missing_courses:
        with open(missing_courses_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['course_id', 'missing_prereq', 'roster']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for missing in missing_courses:
                writer.writerow(missing)
                missing_exported += 1
        
        logging.info(f"Exported {missing_exported} missing course references to {missing_courses_file}")
    
    export_summary = {
        'courses': courses_exported,
        'aliases': aliases_exported,
        'edges': edges_exported,
        'missing_courses': missing_exported
    }
    
    logging.info(f"Export complete: {export_summary}")
    return export_summary

def get_neo4j_import_queries(csv_dir: str = "/var/lib/neo4j/import/course_data") -> List[str]:
    """
    Generate Neo4j LOAD CSV queries for importing course data.
    Uses MERGE operations for idempotent imports.
    
    Args:
        csv_dir: Directory path where CSV files are located (Neo4j import directory)
        
    Returns:
        List of Cypher queries to execute in order
    """
    
    import_queries = [
        # 1. Import courses
        f"""
        LOAD CSV WITH HEADERS FROM 'file:///{csv_dir}/courses.csv' AS row
        MERGE (c:Course {{id: row.id}})
        SET c.subject = row.subject,
            c.catalogNbr = row.catalogNbr,
            c.roster = row.roster,
            c.title = row.title,
            c.prereq_text = row.prereq_text,
            c.prereq_ast = row.prereq_ast,
            c.prereq_confidence = toFloat(row.prereq_confidence),
            c.unitsMin = toInteger(row.unitsMin),
            c.unitsMax = toInteger(row.unitsMax)
        """,
        
        # 2. Import course aliases
        f"""
        LOAD CSV WITH HEADERS FROM 'file:///{csv_dir}/course_aliases.csv' AS row
        MERGE (a:Alias {{code: row.code}})
        WITH a, row
        MATCH (c:Course {{id: row.course_id}})
        MERGE (c)-[:HAS_ALIAS]->(a)
        """,
        
        # 3. Import prerequisite edges with confidence scores
        f"""
        LOAD CSV WITH HEADERS FROM 'file:///{csv_dir}/prerequisite_edges.csv' AS row
        MATCH (from_course:Course {{id: row.from_course_id}})
        MATCH (to_course:Course {{id: row.to_course_id}})
        MERGE (from_course)-[r:REQUIRES]->(to_course)
        SET r.type = row.type, 
            r.confidence = toFloat(row.confidence)
        """
    ]
    
    return import_queries

def generate_import_script(csv_dir: str = "/var/lib/neo4j/import/course_data", output_file: str = "data/neo4j/import_script.cypher") -> str:
    """
    Generate a complete Cypher script for importing data into Neo4j.
    Includes schema setup, data import, and validation queries.
    """
    from python.graph_analysis.neo4j_schema import get_schema_queries, get_validation_queries
    
    script_lines = [
        "// Cornell Course Navigator - Neo4j Import Script",
        "// Generated automatically - includes schema, data import, and validation",
        "",
        "// ===== SCHEMA SETUP =====",
        ""
    ]
    
    # Add schema queries
    for i, query in enumerate(get_schema_queries(), 1):
        script_lines.append(f"// Schema Query {i}")
        script_lines.append(query.strip())
        script_lines.append("")
    
    script_lines.extend([
        "// ===== DATA IMPORT =====",
        ""
    ])
    
    # Add import queries
    for i, query in enumerate(get_neo4j_import_queries(csv_dir), 1):
        script_lines.append(f"// Import Query {i}")
        script_lines.append(query.strip())
        script_lines.append("")
    
    script_lines.extend([
        "// ===== VALIDATION QUERIES =====",
        "// Run these after import to verify data integrity",
        ""
    ])
    
    # Add validation queries as comments (user can uncomment to run)
    for i, query in enumerate(get_validation_queries(), 1):
        script_lines.append(f"// Validation Query {i} (uncomment to run)")
        for line in query.strip().split('\n'):
            script_lines.append(f"// {line}")
        script_lines.append("")
    
    script_content = "\n".join(script_lines)
    
    # Write to file
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        f.write(script_content)
    
    logging.info(f"Generated Neo4j import script: {output_file}")
    return script_content

def find_course_by_code_fast(course_index: Dict, course_code: str, roster: str) -> Optional[Any]:
    """
    Fast course lookup using pre-built index.
    Handles codes like "CS 2110" -> finds course with subject="CS", catalog_nbr="2110"
    O(1) lookup instead of O(N) linear scan.
    """
    parts = course_code.strip().split()
    if len(parts) != 2:
        return None
    
    subject, catalog_nbr = parts
    
    # First try exact match in same roster
    course = course_index.get((subject, catalog_nbr, roster))
    if course:
        return course
    
    # If not found in same roster, try cross-semester fallback
    course = course_index.get((subject, catalog_nbr, None))
    if course:
        return course
    
    return None

def find_course_by_code(courses: List, course_code: str, roster: str) -> Optional[Any]:
    """
    Legacy linear search function - kept for compatibility.
    Use find_course_by_code_fast for better performance.
    """
    parts = course_code.strip().split()
    if len(parts) != 2:
        return None
    
    subject, catalog_nbr = parts
    
    # First try exact match in same roster
    for course in courses:
        if (course.subject == subject and 
            course.catalog_nbr == catalog_nbr and 
            course.roster == roster):
            return course
    
    # If not found in same roster, try any roster (for cross-semester references)
    for course in courses:
        if course.subject == subject and course.catalog_nbr == catalog_nbr:
            return course
    
    return None

def get_neo4j_import_queries(csv_dir: str = "data/neo4j") -> List[str]:
    """
    Generate Neo4j import queries using MERGE for idempotent operations.
    Implements criticism #2: Use MERGE instead of CREATE.
    """
    import_queries = []
    
    # Import courses with MERGE (criticism #2)
    import_queries.append(f"""
    LOAD CSV WITH HEADERS FROM 'file:///{csv_dir}/courses.csv' AS row
    MERGE (c:Course {{id: row.id}})
    SET c.subject = row.subject,
        c.catalogNbr = row.catalogNbr,
        c.roster = row.roster,
        c.title = row.title,
        c.prereq_text = row.prereq_text,
        c.prereq_ast = CASE 
                        WHEN row.prereq_ast IS NOT NULL AND row.prereq_ast <> '' 
                        THEN apoc.convert.fromJsonMap(row.prereq_ast) 
                        ELSE null 
                       END,
        c.prereq_confidence = toFloat(row.prereq_confidence),
        c.unitsMin = toInteger(row.unitsMin),
        c.unitsMax = toInteger(row.unitsMax)
    """)
    
    # Import aliases with MERGE (criticism #2)
    import_queries.append(f"""
    LOAD CSV WITH HEADERS FROM 'file:///{csv_dir}/aliases.csv' AS row
    MATCH (c:Course {{id: row.course_id}})
    MERGE (a:Alias {{code: row.code}})
    MERGE (c)-[:HAS_ALIAS]->(a)
    """)
    
    # Import prerequisite relationships with MERGE (criticism #2)
    import_queries.append(f"""
    LOAD CSV WITH HEADERS FROM 'file:///{csv_dir}/prerequisite_edges.csv' AS row
    MATCH (from_course:Course {{id: row.from_course_id}})
    MATCH (to_course:Course {{id: row.to_course_id}})
    MERGE (from_course)-[:REQUIRES {{type: row.type}}]->(to_course)
    """)
    
    return import_queries

def setup_neo4j_schema(session) -> None:
    """Create constraints and indexes in Neo4j"""
    logging.info("Setting up Neo4j schema...")
    
    schema_queries = get_schema_queries()
    for query in schema_queries:
        try:
            session.run(query)
            logging.debug(f"Executed schema query: {query.strip()[:50]}...")
        except Exception as e:
            logging.warning(f"Schema query failed (may already exist): {e}")

def import_to_neo4j(neo4j_session, csv_dir: str = "data/neo4j") -> Dict[str, int]:
    """
    Import CSV data to Neo4j using MERGE operations.
    Returns import statistics.
    """
    logging.info("Starting Neo4j import...")
    
    # Setup schema first
    setup_neo4j_schema(neo4j_session)
    
    # Get import queries
    import_queries = get_neo4j_import_queries(csv_dir)
    
    import_stats = {}
    
    for i, query in enumerate(import_queries, 1):
        logging.info(f"Executing import query {i}/{len(import_queries)}...")
        try:
            result = neo4j_session.run(query)
            # Get statistics from Neo4j result
            summary = result.consume()
            import_stats[f"query_{i}"] = {
                'nodes_created': summary.counters.nodes_created,
                'relationships_created': summary.counters.relationships_created,
                'properties_set': summary.counters.properties_set
            }
            logging.info(f"Query {i} complete: {import_stats[f'query_{i}']}")
        except Exception as e:
            logging.error(f"Import query {i} failed: {e}")
            import_stats[f"query_{i}"] = {'error': str(e)}
    
    return import_stats

def validate_neo4j_import(neo4j_session) -> Dict[str, Any]:
    """
    Run validation queries to check import success.
    Returns validation results.
    """
    logging.info("Validating Neo4j import...")
    
    validation_queries = get_validation_queries()
    validation_results = {}
    
    for i, query in enumerate(validation_queries, 1):
        try:
            result = neo4j_session.run(query)
            records = [record.data() for record in result]
            validation_results[f"validation_{i}"] = records
            logging.info(f"Validation {i}: {len(records)} records")
        except Exception as e:
            logging.error(f"Validation query {i} failed: {e}")
            validation_results[f"validation_{i}"] = {'error': str(e)}
    
    return validation_results

def full_neo4j_pipeline(neo4j_session, csv_dir: str = "data/neo4j") -> Dict[str, Any]:
    """
    Complete pipeline: export CSV -> import to Neo4j -> validate.
    Returns comprehensive results.
    """
    pipeline_results = {}
    
    # Step 1: Export to CSV
    logging.info("Step 1: Exporting courses to CSV...")
    export_stats = export_courses_to_csv(csv_dir)
    pipeline_results['export'] = export_stats
    
    # Step 2: Import to Neo4j
    logging.info("Step 2: Importing to Neo4j...")
    import_stats = import_to_neo4j(neo4j_session, csv_dir)
    pipeline_results['import'] = import_stats
    
    # Step 3: Validate import
    logging.info("Step 3: Validating import...")
    validation_results = validate_neo4j_import(neo4j_session)
    pipeline_results['validation'] = validation_results
    
    logging.info("Full Neo4j pipeline complete!")
    return pipeline_results

# Connection helper (to be used with actual Neo4j driver)
def get_neo4j_session():
    """
    Helper function to get Neo4j session.
    Requires environment variables: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    """
    try:
        from neo4j import GraphDatabase
        
        uri = os.getenv('NEO4J_URI')
        user = os.getenv('NEO4J_USER') 
        password = os.getenv('NEO4J_PASSWORD')
        
        if not all([uri, user, password]):
            raise ValueError("Neo4j connection requires NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD environment variables")
        
        driver = GraphDatabase.driver(uri, auth=(user, password))
        return driver.session()
    except ImportError:
        logging.error("neo4j package not installed. Run: poetry add neo4j")
        return None
    except Exception as e:
        logging.error(f"Failed to connect to Neo4j: {e}")
        return None

if __name__ == "__main__":
    # Test CSV export
    logging.info("Testing CSV export...")
    export_stats = export_courses_to_csv()
    print(f"Export results: {export_stats}")
    
    # Print sample import queries
    print("\\nSample Neo4j import queries:")
    queries = get_neo4j_import_queries()
    for i, query in enumerate(queries, 1):
        print(f"Query {i}:")
        print(query.strip())
        print()