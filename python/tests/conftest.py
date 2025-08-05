"""
Pytest configuration and fixtures for Cornell Course Navigator tests
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from typing import AsyncGenerator

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_neo4j_service():
    """Mock Neo4j service for testing"""
    service = Mock()
    service.execute_query = AsyncMock()
    service.health_check = AsyncMock(return_value=True)
    service.close = AsyncMock()
    return service

@pytest.fixture
def mock_vector_service():
    """Mock Qdrant vector service for testing"""
    service = Mock()
    service.search = AsyncMock()
    service.health_check = AsyncMock(return_value=True)
    service.close = AsyncMock()
    return service

@pytest.fixture
def sample_course_data():
    """Sample course data for testing"""
    return [
        {
            "course_code": "CS 2110",
            "course_title": "Object-Oriented Programming and Data Structures",
            "subject": "CS",
            "level": 2110,
            "centrality_score": 0.856
        },
        {
            "course_code": "CS 3110", 
            "course_title": "Data Structures and Functional Programming",
            "subject": "CS",
            "level": 3110,
            "centrality_score": 0.742
        },
        {
            "course_code": "MATH 2940",
            "course_title": "Linear Algebra for Engineers", 
            "subject": "MATH",
            "level": 2940,
            "centrality_score": 0.634
        }
    ]

@pytest.fixture
def sample_prerequisite_data():
    """Sample prerequisite relationship data for testing"""
    return [
        {
            "from_course": "CS 2110",
            "to_course": "CS 3110", 
            "relationship_type": "PREREQUISITE"
        },
        {
            "from_course": "MATH 2940",
            "to_course": "CS 4780",
            "relationship_type": "PREREQUISITE"
        },
        {
            "from_course": "CS 2110",
            "to_course": "CS 4780",
            "relationship_type": "PREREQUISITE"
        }
    ]