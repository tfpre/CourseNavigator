#!/usr/bin/env python3
"""
Load major requirements data into Neo4j.
Reads the JSON fixture and executes the Cypher migration.
"""

import json
import os
import asyncio
import sys

# Add parent directory to path so we can import from the project
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from neo4j import AsyncGraphDatabase
except ImportError:
    print("neo4j package not installed. Run: poetry add neo4j")
    sys.exit(1)

async def load_major_requirements():
    """Load major requirements into Neo4j"""
    
    # Get Neo4j connection details from environment
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j") 
    password = os.environ.get("NEO4J_PASSWORD")
    
    if not password:
        print("Error: NEO4J_PASSWORD environment variable is required")
        sys.exit(1)
    
    # Read the JSON fixture
    fixture_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data/degree/majors_cs_v1.json")
    try:
        with open(fixture_path, "r") as f:
            majors_json = f.read()
    except FileNotFoundError:
        print(f"Error: Could not find fixture file at {fixture_path}")
        sys.exit(1)
    
    # Read the migration Cypher
    migration_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations/09_requirements.cypher")
    try:
        with open(migration_path, "r") as f:
            cypher = f.read()
    except FileNotFoundError:
        print(f"Error: Could not find migration file at {migration_path}")
        sys.exit(1)
    
    print(f"Connecting to Neo4j at {uri}...")
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    
    try:
        async with driver.session() as session:
            print("Testing APOC availability...")
            try:
                await session.run("CALL apoc.schema.assert({},{},true)")
                print("APOC is available ✓")
            except Exception as e:
                print(f"Warning: APOC may not be available: {e}")
            
            print("Loading major requirements...")
            result = await session.run(cypher, majorsJson=majors_json)
            
            # Get summary info
            summary = await result.consume()
            print(f"Migration completed successfully!")
            print(f"Nodes created: {summary.counters.nodes_created}")
            print(f"Relationships created: {summary.counters.relationships_created}")
            print(f"Properties set: {summary.counters.properties_set}")
            
            # Verify the data was loaded
            print("\nVerifying data...")
            verify_result = await session.run("""
                MATCH (m:Major)-[:REQUIRES]->(r:Requirement)
                RETURN m.name, count(r) as req_count
                ORDER BY m.name
            """)
            
            async for record in verify_result:
                print(f"  {record['m.name']}: {record['req_count']} requirements")
                
    finally:
        await driver.close()
    
    print("\nMajor requirements loaded successfully! 🎓")

if __name__ == "__main__":
    print("Loading major requirements into Neo4j...")
    asyncio.run(load_major_requirements())