"""
Smoke test for Qdrant integration with course embeddings.
This script tests the end-to-end concept of embedding course descriptions and storing them in Qdrant.
"""

import os
import uuid
from typing import List
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from python.data_ingestion.models import CleanCourse

# Sample course data for testing
SAMPLE_COURSES = [
    CleanCourse(
        id="FA25-CS-2110-1",
        crse_id=12345,
        crse_offer_nbr=1,
        title="Object-Oriented Programming and Data Structures",
        subject="CS",
        catalog_nbr="2110",
        description_text="Introduction to object-oriented programming. Covers classes, inheritance, polymorphism, and basic data structures including lists, trees, and hash tables.",
        prerequisite_text="CS 1110 or CS 1112",
        units_min=4,
        units_max=4,
        roster="FA25"
    ),
    CleanCourse(
        id="FA25-CS-4820-1",
        crse_id=12346,
        crse_offer_nbr=1,
        title="Introduction to Algorithms",
        subject="CS",
        catalog_nbr="4820",
        description_text="Design and analysis of algorithms. Covers sorting, searching, graph algorithms, dynamic programming, and computational complexity.",
        prerequisite_text="CS 2110 and CS 2800",
        units_min=4,
        units_max=4,
        roster="FA25"
    ),
    CleanCourse(
        id="FA25-MATH-1920-1",
        crse_id=12347,
        crse_offer_nbr=1,
        title="Multivariable Calculus",
        subject="MATH",
        catalog_nbr="1920",
        description_text="Calculus of functions of several variables. Covers partial derivatives, multiple integrals, vector fields, and Green's theorem.",
        prerequisite_text="MATH 1910 or equivalent",
        units_min=4,
        units_max=4,
        roster="FA25"
    )
]

def test_qdrant_integration():
    """Test embedding courses and storing them in Qdrant."""
    print("🚀 Starting Qdrant integration test...")
    
    # 1. Initialize embedding model
    print("📊 Loading embedding model...")
    # Use a smaller model for testing
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    # 2. Create embeddings for sample courses
    print("🔤 Creating course embeddings...")
    embeddings = []
    for course in SAMPLE_COURSES:
        # Combine title and description for richer embeddings
        text = f"{course.title}. {course.description_text or ''}"
        embedding = model.encode(text)
        embeddings.append(embedding)
        print(f"   ✓ {course.id}: {course.title}")
    
    # 3. Initialize Qdrant client (in-memory for testing)
    print("🗄️  Initializing Qdrant client...")
    client = QdrantClient(":memory:")  # In-memory for testing
    
    # 4. Create collection
    collection_name = "cornell_courses_test"
    print(f"📝 Setting up collection: {collection_name}")
    
    # Check if collection exists before creating
    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=len(embeddings[0]), distance=Distance.COSINE),
        )
        print(f"   ✓ Created new collection")
    else:
        print(f"   ✓ Using existing collection")
    
    # 5. Upload course embeddings
    print("⬆️  Uploading course embeddings...")
    points = []
    for course, embedding in zip(SAMPLE_COURSES, embeddings):
        point = PointStruct(
            id=str(uuid.uuid4()),  # Use UUID for Qdrant compatibility
            vector=embedding.tolist(),
            payload={
                "course_id": course.id,
                "title": course.title,
                "subject": course.subject,
                "catalog_nbr": course.catalog_nbr,
                "description": course.description_text,
                "prerequisites": course.prerequisite_text,
                "units": f"{course.units_min}-{course.units_max}",
            }
        )
        points.append(point)
    
    client.upsert(collection_name=collection_name, points=points)
    print(f"   ✓ Uploaded {len(points)} courses")
    
    # 6. Test semantic search
    print("🔍 Testing semantic search...")
    test_queries = [
        "object oriented programming",
        "graph algorithms and complexity",
        "calculus multiple variables"
    ]
    
    for query in test_queries:
        print(f"\n🔎 Query: '{query}'")
        
        # Embed the query
        query_embedding = model.encode(query)
        
        # Search for similar courses
        search_results = client.search(
            collection_name=collection_name,
            query_vector=query_embedding.tolist(),
            limit=2
        )
        
        for result in search_results:
            score = result.score
            payload = result.payload
            print(f"   📚 {payload['course_id']}: {payload['title']} (similarity: {score:.3f})")
    
    print("\n✅ Qdrant integration test completed successfully!")
    print("🎯 End-to-end concept verified: Course data → Embeddings → Vector search")

if __name__ == "__main__":
    test_qdrant_integration()