"""
Pydantic models for FastAPI gateway request/response cycle.
These models will be exported to JSON Schema for TypeScript sync.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from enum import Enum

class SearchMode(str, Enum):
    """Search mode for different types of queries"""
    SEMANTIC = "semantic"           # Pure vector similarity search
    GRAPH_AWARE = "graph_aware"     # Vector + graph context expansion
    PREREQUISITE_PATH = "prereq_path"  # Show prerequisite chain for specific course

class CourseInfo(BaseModel):
    """Course information returned in search results"""
    id: str
    subject: str
    catalog_nbr: str
    title: str
    description: Optional[str] = None
    credits: Optional[str] = None
    similarity_score: Optional[float] = None
    graph_relevance: Optional[float] = None

class PrerequisiteEdge(BaseModel):
    """Graph edge representing a prerequisite relationship"""
    from_course_id: str
    to_course_id: str
    type: str  # PREREQUISITE, COREQUISITE, etc.
    confidence: float = Field(..., ge=0.0, le=1.0)

class GraphContext(BaseModel):
    """Graph context for a set of courses"""
    nodes: List[CourseInfo]
    edges: List[PrerequisiteEdge]
    centrality_scores: Optional[Dict[str, float]] = None

class RAGRequest(BaseModel):
    """Request for RAG with graph context"""
    query: str = Field(..., min_length=1, max_length=500)
    mode: SearchMode = SearchMode.GRAPH_AWARE
    top_k: int = Field(default=10, ge=1, le=50)
    include_graph_context: bool = True
    max_prerequisite_depth: int = Field(default=3, ge=1, le=10)
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "machine learning courses with programming prerequisites",
                "mode": "graph_aware",
                "top_k": 10,
                "include_graph_context": True,
                "max_prerequisite_depth": 3
            }
        }

class PrerequisitePathRequest(BaseModel):
    """Request for prerequisite path for a specific course"""
    course_id: str = Field(..., min_length=1)
    include_recommendations: bool = True
    max_depth: int = Field(default=5, ge=1, le=10)
    
    class Config:
        json_schema_extra = {
            "example": {
                "course_id": "FA14-CS-4780-1",
                "include_recommendations": True,
                "max_depth": 5
            }
        }

class ErrorDetail(BaseModel):
    """Error detail for API responses"""
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None

class RAGResponse(BaseModel):
    """Response from RAG with graph endpoint"""
    success: bool
    answer: Optional[str] = None
    courses: List[CourseInfo] = []
    graph_context: Optional[GraphContext] = None
    query_metadata: Dict[str, Any] = {}
    error: Optional[ErrorDetail] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "answer": "Based on your query about machine learning courses...",
                "courses": [
                    {
                        "id": "FA14-CS-4780-1",
                        "subject": "CS",
                        "catalog_nbr": "4780",
                        "title": "Machine Learning for Intelligent Systems",
                        "similarity_score": 0.92,
                        "graph_relevance": 0.85
                    }
                ],
                "graph_context": {
                    "nodes": [],
                    "edges": []
                },
                "query_metadata": {
                    "vector_search_time_ms": 45,
                    "graph_query_time_ms": 123,
                    "total_time_ms": 168
                }
            }
        }

class PrerequisitePathResponse(BaseModel):
    """Response for prerequisite path queries"""
    success: bool
    course: Optional[CourseInfo] = None
    prerequisite_path: Optional[GraphContext] = None
    missing_prerequisites: List[str] = []
    recommendations: List[CourseInfo] = []
    path_metadata: Dict[str, Any] = {}
    error: Optional[ErrorDetail] = None

class HealthResponse(BaseModel):
    """Health check response"""
    status: Literal["healthy", "degraded", "unhealthy"]
    services: Dict[str, bool] = {}
    version: str = "1.0.0"
    timestamp: str

# === Graph Algorithms Models ===

class CentralityRequest(BaseModel):
    """Request for course centrality analysis"""
    top_n: int = Field(default=20, ge=1, le=100)
    damping_factor: float = Field(default=0.85, ge=0.1, le=1.0)
    min_betweenness: float = Field(default=0.01, ge=0.0, le=1.0)
    min_in_degree: int = Field(default=2, ge=1, le=20)
    
    class Config:
        json_schema_extra = {
            "example": {
                "top_n": 20,
                "damping_factor": 0.85,
                "min_betweenness": 0.01,
                "min_in_degree": 2
            }
        }

class CourseRanking(BaseModel):
    """Course ranking with centrality score"""
    course_code: str
    course_title: str
    centrality_score: float
    rank: int
    subject: str
    level: int

class CentralityResponse(BaseModel):
    """Response for centrality analysis"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    computation_time_ms: Optional[int] = None
    error: Optional[ErrorDetail] = None

class CommunityRequest(BaseModel):
    """Request for community detection analysis"""
    algorithm: Literal["louvain", "greedy_modularity"] = "louvain"
    
    class Config:
        json_schema_extra = {
            "example": {
                "algorithm": "louvain"
            }
        }

class CommunityResponse(BaseModel):
    """Response for community detection analysis"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    computation_time_ms: Optional[int] = None
    error: Optional[ErrorDetail] = None

class CourseRecommendationRequest(BaseModel):
    """Request for course recommendations"""
    course_code: str = Field(..., min_length=1)
    num_recommendations: int = Field(default=5, ge=1, le=20)
    
    class Config:
        json_schema_extra = {
            "example": {
                "course_code": "CS 2110",
                "num_recommendations": 5
            }
        }

class CourseRecommendationResponse(BaseModel):
    """Response for course recommendations"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    computation_time_ms: Optional[int] = None
    error: Optional[ErrorDetail] = None

class ShortestPathRequest(BaseModel):
    """Request for shortest prerequisite path"""
    target_course: str = Field(..., min_length=1)
    completed_courses: List[str] = Field(default_factory=list)
    
    class Config:
        json_schema_extra = {
            "example": {
                "target_course": "CS 4780",
                "completed_courses": ["CS 2110", "MATH 2940"]
            }
        }

class ShortestPathResponse(BaseModel):
    """Response for shortest prerequisite path"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    computation_time_ms: Optional[int] = None
    error: Optional[ErrorDetail] = None

class AlternativePathsRequest(BaseModel):
    """Request for alternative prerequisite paths"""
    target_course: str = Field(..., min_length=1)
    completed_courses: List[str] = Field(default_factory=list)
    num_alternatives: int = Field(default=3, ge=1, le=10)
    
    class Config:
        json_schema_extra = {
            "example": {
                "target_course": "CS 4780",
                "completed_courses": ["CS 2110", "MATH 2940"],
                "num_alternatives": 3
            }
        }

class AlternativePathsResponse(BaseModel):
    """Response for alternative prerequisite paths"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    computation_time_ms: Optional[int] = None
    error: Optional[ErrorDetail] = None

class SemesterPlanRequest(BaseModel):
    """Request for semester optimization"""
    target_courses: List[str] = Field(..., min_items=1)
    completed_courses: List[str] = Field(default_factory=list)
    semesters_available: int = Field(default=8, ge=1, le=16)
    max_credits_per_semester: int = Field(default=18, ge=6, le=24)
    
    class Config:
        json_schema_extra = {
            "example": {
                "target_courses": ["CS 4780", "CS 4740", "CS 4410"],
                "completed_courses": ["CS 2110", "MATH 2940"],
                "semesters_available": 8,
                "max_credits_per_semester": 18
            }
        }

class SemesterPlanResponse(BaseModel):
    """Response for semester optimization"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    computation_time_ms: Optional[int] = None
    error: Optional[ErrorDetail] = None

class GraphSubgraphRequest(BaseModel):
    """Request for graph subgraph data"""
    max_nodes: int = Field(default=50, ge=5, le=200)
    max_edges: int = Field(default=100, ge=10, le=500)
    include_centrality: bool = Field(default=True)
    include_communities: bool = Field(default=True)
    filter_by_subject: Optional[List[str]] = Field(default=None)
    
    class Config:
        json_schema_extra = {
            "example": {
                "max_nodes": 50,
                "max_edges": 100,
                "include_centrality": True,
                "include_communities": True,
                "filter_by_subject": ["CS", "MATH"]
            }
        }

class GraphSubgraphNode(BaseModel):
    """Node in graph subgraph"""
    course_code: str
    course_title: str
    subject: str
    level: int
    centrality_score: Optional[float] = None
    community_id: Optional[int] = None

class GraphSubgraphEdge(BaseModel):
    """Edge in graph subgraph"""
    from_course: str
    to_course: str
    relationship_type: str

class GraphSubgraphResponse(BaseModel):
    """Response for graph subgraph data"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    computation_time_ms: Optional[int] = None
    error: Optional[ErrorDetail] = None

# Export all models for schema generation
__all__ = [
    "SearchMode",
    "CourseInfo", 
    "PrerequisiteEdge",
    "GraphContext",
    "RAGRequest",
    "PrerequisitePathRequest",
    "ErrorDetail",
    "RAGResponse", 
    "PrerequisitePathResponse",
    "HealthResponse",
    "CentralityRequest",
    "CourseRanking",
    "CentralityResponse",
    "CommunityRequest",
    "CommunityResponse",
    "CourseRecommendationRequest",
    "CourseRecommendationResponse",
    "ShortestPathRequest",
    "ShortestPathResponse",
    "AlternativePathsRequest",
    "AlternativePathsResponse",
    "SemesterPlanRequest",
    "SemesterPlanResponse",
    "GraphSubgraphRequest",
    "GraphSubgraphNode",
    "GraphSubgraphEdge",
    "GraphSubgraphResponse"
]