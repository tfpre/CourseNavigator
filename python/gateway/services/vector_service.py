"""
Vector service for Qdrant integration
Handles semantic search using course embeddings
"""

import logging
import hashlib
import random
from typing import List, Dict, Any, Optional
import asyncio

try:
    from qdrant_client import QdrantClient, AsyncQdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    from qdrant_client.http.exceptions import UnexpectedResponse
except ImportError:
    # Graceful fallback if qdrant-client not available
    QdrantClient = None
    AsyncQdrantClient = None
    Distance = None
    VectorParams = None
    PointStruct = None
    UnexpectedResponse = Exception

try:
    import openai
except ImportError:
    openai = None

from ..models import CourseInfo

logger = logging.getLogger(__name__)

class VectorService:
    """Service for vector similarity search using Qdrant"""
    
    def __init__(
        self, 
        url: str = "http://localhost:6333", 
        collection_name: str = "cornell_courses",
        openai_api_key: Optional[str] = None
    ):
        self.url = url
        self.collection_name = collection_name
        self.client: Optional[AsyncQdrantClient] = None
        self.openai_api_key = openai_api_key
        
        # Determine mock mode based on available dependencies
        qdrant_available = AsyncQdrantClient is not None
        openai_available = openai is not None and openai_api_key is not None
        
        if not qdrant_available:
            logger.warning("qdrant-client not available, vector search will be mocked")
            self._mock_mode = True
        elif not openai_available:
            logger.warning("OpenAI not available, embeddings will be mocked")
            self._mock_mode = True
        else:
            self._mock_mode = False
            # Configure OpenAI client
            openai.api_key = openai_api_key
    
    async def _get_client(self) -> AsyncQdrantClient:
        """Get or create async Qdrant client"""
        if self._mock_mode:
            raise RuntimeError("Qdrant client not available")
            
        if self.client is None:
            self.client = AsyncQdrantClient(url=self.url)
        return self.client
    
    async def health_check(self) -> bool:
        """Check if Qdrant service is healthy"""
        if self._mock_mode:
            logger.info("Vector service in mock mode")
            return True
            
        try:
            client = await self._get_client()
            # Simple health check - list collections
            collections = await client.get_collections()
            logger.info(f"Qdrant health check passed, {len(collections.collections)} collections")
            return True
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            raise
    
    async def search_courses(
        self, 
        query_embedding: List[float], 
        top_k: int = 10,
        score_threshold: float = 0.7
    ) -> List[CourseInfo]:
        """
        Search for courses using vector similarity
        
        Args:
            query_embedding: Query vector embedding
            top_k: Number of results to return
            score_threshold: Minimum similarity score
            
        Returns:
            List of CourseInfo objects with similarity scores
        """
        if self._mock_mode:
            return await self._mock_search_courses(query_embedding, top_k)
            
        try:
            client = await self._get_client()
            
            # Search for similar vectors
            search_result = await client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=top_k,
                score_threshold=score_threshold,
                with_payload=True
            )
            
            courses = []
            for point in search_result:
                payload = point.payload or {}
                
                course = CourseInfo(
                    id=payload.get("id", "unknown"),
                    subject=payload.get("subject", ""),
                    catalog_nbr=payload.get("catalog_nbr", ""),
                    title=payload.get("title", ""),
                    description=payload.get("description"),
                    credits=payload.get("credits"),
                    similarity_score=float(point.score)
                )
                courses.append(course)
            
            logger.info(f"Vector search returned {len(courses)} courses")
            return courses
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            raise
    
    async def _mock_search_courses(
        self, 
        query_embedding: List[float], 
        top_k: int
    ) -> List[CourseInfo]:
        """Mock search for development when Qdrant not available"""
        logger.info(f"Mock vector search for {top_k} courses")
        
        # Return some sample courses for development
        mock_courses = [
            CourseInfo(
                id="FA14-CS-4780-1",
                subject="CS",
                catalog_nbr="4780",
                title="Machine Learning for Intelligent Systems",
                description="Introduction to machine learning and statistical pattern recognition.",
                similarity_score=0.95
            ),
            CourseInfo(
                id="FA14-CS-2110-1", 
                subject="CS",
                catalog_nbr="2110",
                title="Object-Oriented Programming and Data Structures",
                description="Programming methodology and data structures.",
                similarity_score=0.88
            ),
            CourseInfo(
                id="FA14-CS-3110-1",
                subject="CS", 
                catalog_nbr="3110",
                title="Data Structures and Functional Programming",
                description="Advanced programming and data structures using functional programming.",
                similarity_score=0.82
            )
        ]
        
        return mock_courses[:top_k]
    
    async def get_embedding(self, text: str) -> List[float]:
        """
        Get embedding for text using OpenAI API
        
        Uses text-embedding-3-small model as specified in CLAUDE.md
        """
        if self._mock_mode:
            # Return deterministic mock embedding vector (384 dimensions for testing)
            return self._deterministic_mock_embedding(text)
        
        try:
            # Use the OpenAI embeddings API with text-embedding-3-small model
            response = await openai.Embedding.acreate(
                model="text-embedding-3-small",
                input=text
            )
            
            # Extract embedding vector from response
            embedding = response['data'][0]['embedding']
            logger.info(f"Generated OpenAI embedding for text (length: {len(embedding)})")
            return embedding
            
        except Exception as e:
            logger.error(f"OpenAI embedding API call failed: {e}")
            logger.warning("Falling back to mock embedding")
            return self._deterministic_mock_embedding(text)
    
    def _deterministic_mock_embedding(self, text: str) -> List[float]:
        """
        Generate deterministic, high-quality mock embedding using the text's
        SHA1 hash as a seed for a random number generator.
        """
        # Use hashlib for a seed that is stable across Python versions
        hash_object = hashlib.sha1(text.encode('utf-8'))
        seed = int.from_bytes(hash_object.digest(), 'big')
        
        # Use a local Random instance to avoid affecting global state
        rand_gen = random.Random(seed)
        
        # Generate a 384-dimension vector
        embedding = [rand_gen.random() for _ in range(384)]
        
        # Normalize to a unit vector, which is standard for embedding models
        norm = sum(x * x for x in embedding) ** 0.5
        normalized_embedding = [x / norm for x in embedding]
        
        return normalized_embedding

    
    async def close(self):
        """Close the client connection"""
        if self.client:
            await self.client.close()
            self.client = None