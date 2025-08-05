// Cornell Course Navigator - Neo4j Import Script
// Generated for production deployment on Neo4j Aura

// ===== SCHEMA SETUP =====

// Schema Query 1
CREATE CONSTRAINT course_id IF NOT EXISTS 
FOR (c:Course) REQUIRE c.id IS UNIQUE;

// Schema Query 2
CREATE CONSTRAINT alias_code IF NOT EXISTS 
FOR (a:Alias) REQUIRE a.code IS UNIQUE;

// Schema Query 3
CREATE INDEX course_subject IF NOT EXISTS 
FOR (c:Course) ON (c.subject);

// Schema Query 4
CREATE INDEX course_catalog IF NOT EXISTS 
FOR (c:Course) ON (c.catalogNbr);

// Schema Query 5
CREATE INDEX course_roster IF NOT EXISTS 
FOR (c:Course) ON (c.roster);

// ===== DATA IMPORT =====

// Import Query 1 - Import courses
LOAD CSV WITH HEADERS FROM 'file:///courses.csv' AS row
MERGE (c:Course {id: row.id})
SET c.subject = row.subject,
    c.catalogNbr = row.catalogNbr,
    c.roster = row.roster,
    c.title = row.title,
    c.prereq_text = row.prereq_text,
    c.prereq_ast = row.prereq_ast,
    c.prereq_confidence = toFloat(row.prereq_confidence),
    c.unitsMin = toInteger(row.unitsMin),
    c.unitsMax = toInteger(row.unitsMax);

// Import Query 2 - Import course aliases  
LOAD CSV WITH HEADERS FROM 'file:///aliases.csv' AS row
MERGE (a:Alias {code: row.code})
WITH a, row
MATCH (c:Course {id: row.course_id})
MERGE (c)-[:HAS_ALIAS]->(a);

// Import Query 3 - Import prerequisite edges
LOAD CSV WITH HEADERS FROM 'file:///prerequisite_edges.csv' AS row
MATCH (from_course:Course {id: row.from_course_id})
MATCH (to_course:Course {id: row.to_course_id})
MERGE (from_course)-[r:REQUIRES]->(to_course)
SET r.type = row.type;

// ===== VALIDATION QUERIES =====
// Run these after import to verify data integrity

// Validation Query 1 - Count courses
// MATCH (c:Course) RETURN count(c) as course_count;

// Validation Query 2 - Count aliases  
// MATCH (a:Alias) RETURN count(a) as alias_count;

// Validation Query 3 - Count relationships by type
// MATCH ()-[r:REQUIRES]->() RETURN r.type, count(*) as count ORDER BY count DESC;

// Validation Query 4 - Count alias relationships
// MATCH ()-[r:HAS_ALIAS]->() RETURN count(r) as alias_relationships;

// Validation Query 5 - Top courses with most prerequisites
// MATCH (c:Course)-[:REQUIRES]->(prereq:Course)
// RETURN c.id, c.title, count(prereq) as prereq_count
// ORDER BY prereq_count DESC LIMIT 10;

// Validation Query 6 - Most important prerequisite courses
// MATCH (prereq:Course)<-[:REQUIRES]-(c:Course)
// RETURN prereq.id, prereq.title, count(c) as dependents
// ORDER BY dependents DESC LIMIT 10;

// Validation Query 7 - Spot check CS 2110
// MATCH (c:Course {id: 'FA14-CS-2110-1'})
// OPTIONAL MATCH (c)-[:HAS_ALIAS]->(a:Alias)
// OPTIONAL MATCH (c)-[:REQUIRES]->(prereq:Course)
// OPTIONAL MATCH (dependent:Course)-[:REQUIRES]->(c)
// RETURN c.title as course,
//        collect(DISTINCT a.code) as aliases,
//        collect(DISTINCT prereq.id) as prerequisites,
//        collect(DISTINCT dependent.id) as dependents;