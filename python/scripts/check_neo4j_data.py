#!/usr/bin/env python3
"""
Check if Neo4j has the Cornell course data loaded
"""

import asyncio
import logging
import os
import sys

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from gateway.services.graph_service import GraphService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_neo4j_data():
    """Check if Neo4j has course data loaded"""
    
    # Initialize Neo4j service 
    neo4j_uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USERNAME", "neo4j") 
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
    
    neo4j_service = GraphService(neo4j_uri, neo4j_user, neo4j_password)
    
    try:
        logger.info("Checking Neo4j connection...")
        
        # Count courses
        course_result = await neo4j_service.execute_query("MATCH (c:Course) RETURN count(c) as course_count")
        course_count = course_result[0]["course_count"] if course_result else 0
        
        # Count prerequisites
        prereq_result = await neo4j_service.execute_query("MATCH ()-[r:REQUIRES]->() RETURN count(r) as prereq_count")
        prereq_count = prereq_result[0]["prereq_count"] if prereq_result else 0
        
        # Count aliases
        alias_result = await neo4j_service.execute_query("MATCH (a:Alias) RETURN count(a) as alias_count")
        alias_count = alias_result[0]["alias_count"] if alias_result else 0
        
        logger.info(f"Neo4j Data Status:")
        logger.info(f"  Courses: {course_count}")
        logger.info(f"  Prerequisites: {prereq_count}")
        logger.info(f"  Aliases: {alias_count}")
        
        if course_count == 0:
            logger.error("❌ No courses found in Neo4j! Data needs to be imported.")
            return False
        elif course_count < 100:
            logger.warning(f"⚠️  Only {course_count} courses found. Expected ~200+")
        else:
            logger.info(f"✅ Found {course_count} courses in Neo4j")
            
        return course_count > 0
        
    except Exception as e:
        logger.error(f"❌ Failed to check Neo4j data: {e}")
        return False
    finally:
        await neo4j_service.close()

if __name__ == "__main__":
    result = asyncio.run(check_neo4j_data())
    sys.exit(0 if result else 1)