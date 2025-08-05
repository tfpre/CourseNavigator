"""
Neo4j graph database schema design for Cornell Course Navigator.
Implements simplified schema with MERGE operations for safe re-runs.
"""

# Neo4j schema queries with constraints and indexes
NEO4J_SCHEMA_QUERIES = [
    # Node constraints (must be unique)
    """
    CREATE CONSTRAINT course_id IF NOT EXISTS 
    FOR (c:Course) REQUIRE c.id IS UNIQUE
    """,
    
    """
    CREATE CONSTRAINT alias_code IF NOT EXISTS 
    FOR (a:Alias) REQUIRE a.code IS UNIQUE
    """,
    
    # Performance indexes for common queries
    """
    CREATE INDEX course_subject IF NOT EXISTS 
    FOR (c:Course) ON (c.subject)
    """,
    
    """
    CREATE INDEX course_catalog IF NOT EXISTS 
    FOR (c:Course) ON (c.catalogNbr)
    """,
    
    """
    CREATE INDEX course_roster IF NOT EXISTS 
    FOR (c:Course) ON (c.roster)
    """,
]

def get_schema_queries():
    """Return list of schema setup queries"""
    return NEO4J_SCHEMA_QUERIES

# Example Cypher queries for testing and validation
VALIDATION_QUERIES = [
    # Count all nodes and relationships
    """
    MATCH (c:Course) 
    RETURN count(c) as course_count
    """,
    
    """
    MATCH (a:Alias) 
    RETURN count(a) as alias_count
    """,
    
    """
    MATCH ()-[r:REQUIRES]->() 
    RETURN r.type, count(*) as count
    ORDER BY count DESC
    """,
    
    """
    MATCH ()-[r:HAS_ALIAS]->() 
    RETURN count(r) as alias_relationships
    """,
    
    # Find courses with most prerequisites
    """
    MATCH (c:Course)-[:REQUIRES]->(prereq:Course)
    RETURN c.id, c.title, count(prereq) as prereq_count
    ORDER BY prereq_count DESC 
    LIMIT 10
    """,
    
    # Find courses that are prerequisites for many others
    """
    MATCH (prereq:Course)<-[:REQUIRES]-(c:Course)
    RETURN prereq.id, prereq.title, count(c) as dependents
    ORDER BY dependents DESC 
    LIMIT 10
    """,
    
    # Spot check a specific course and its relationships
    """
    MATCH (c:Course {id: 'FA14-CS-2110-1'})
    OPTIONAL MATCH (c)-[:HAS_ALIAS]->(a:Alias)
    OPTIONAL MATCH (c)-[:REQUIRES]->(prereq:Course)
    OPTIONAL MATCH (dependent:Course)-[:REQUIRES]->(c)
    RETURN c.title as course,
           collect(DISTINCT a.code) as aliases,
           collect(DISTINCT prereq.id) as prerequisites,
           collect(DISTINCT dependent.id) as dependents
    """,
]

def get_validation_queries():
    """Return list of validation queries for testing import"""
    return VALIDATION_QUERIES

# Graph schema documentation
SCHEMA_DOCUMENTATION = """
Cornell Course Navigator - Neo4j Graph Schema

## Node Types

### Course
Properties:
- id: String (unique) - e.g., "FA14-CS-2110-1"
- subject: String - e.g., "CS"
- catalogNbr: String - e.g., "2110"
- roster: String - e.g., "FA14"
- title: String - Course title
- prereq_text: String - Raw prerequisite text
- prereq_ast: String - JSON-serialized parsed prerequisite AST
- prereq_confidence: Float - Parser confidence (0-1)
- unitsMin: Integer - Minimum credit units
- unitsMax: Integer - Maximum credit units

### Alias
Properties:
- code: String (unique) - e.g., "ENGRD 2110"

## Relationship Types

### HAS_ALIAS
- Direction: (Course)-[:HAS_ALIAS]->(Alias)
- Purpose: Connect courses to their cross-listings
- Properties: None

### REQUIRES
- Direction: (Course)-[:REQUIRES]->(Course)
- Purpose: Model prerequisite dependencies
- Properties:
  - type: String - "MANDATORY", "OR_GROUP", "AND_GROUP", "CONCURRENT"

## Example Graph Pattern

```
(CS2110:Course {id: "FA14-CS-2110-1"})
  -[:HAS_ALIAS]-> (ENGRD2110:Alias {code: "ENGRD 2110"})
  -[:REQUIRES {type: "OR_GROUP"}]-> (CS1110:Course {id: "FA14-CS-1110-1"})
  -[:REQUIRES {type: "OR_GROUP"}]-> (CS1130:Course {id: "FA14-CS-1130-1"})

(CS3110:Course {id: "FA14-CS-3110-1"})
  -[:REQUIRES {type: "MANDATORY"}]-> (CS2110:Course)
```

## Query Examples

### Find prerequisite path
```cypher
MATCH path = (start:Course {id: "FA14-CS-1110-1"})-[:REQUIRES*]->(end:Course {id: "FA14-CS-4820-1"})
RETURN path
```

### Find courses requiring specific prerequisite
```cypher
MATCH (prereq:Course {subject: "CS", catalogNbr: "2110"})<-[:REQUIRES]-(course:Course)
RETURN course.id, course.title
```

### Find highly connected courses (PageRank candidates)
```cypher
MATCH (c:Course)
OPTIONAL MATCH (c)<-[:REQUIRES]-(dependent)
OPTIONAL MATCH (c)-[:REQUIRES]->(prereq)
RETURN c.id, c.title, 
       count(DISTINCT dependent) as dependents,
       count(DISTINCT prereq) as prerequisites
ORDER BY dependents DESC
```
"""

def print_schema_documentation():
    """Print the schema documentation"""
    print(SCHEMA_DOCUMENTATION)

if __name__ == "__main__":
    print("Neo4j Schema Queries:")
    print("=" * 50)
    for i, query in enumerate(NEO4J_SCHEMA_QUERIES, 1):
        print(f"Query {i}:")
        print(query.strip())
        print()
    
    print("\nValidation Queries:")
    print("=" * 50)
    for i, query in enumerate(VALIDATION_QUERIES, 1):
        print(f"Validation {i}:")
        print(query.strip())
        print()
    
    print_schema_documentation()