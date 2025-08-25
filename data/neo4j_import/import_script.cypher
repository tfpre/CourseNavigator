// Cornell Course Navigator - Neo4j Import Script
// Generated from Cornell Course Data on 2025-08-17T20:38:24.958910

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
MERGE (c:Course {id: row.id})
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
MERGE (a:Alias {code: row.code})
WITH a, row
MATCH (c:Course {id: row.course_id})
MERGE (c)-[:HAS_ALIAS]->(a)
SET a.type = row.type;

// Import prerequisite relationships
LOAD CSV WITH HEADERS FROM 'file:///neo4j_import/prerequisite_edges.csv' AS row
MATCH (from_course:Course {id: row.from_course_id})
MATCH (to_course:Course {id: row.to_course_id})
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
