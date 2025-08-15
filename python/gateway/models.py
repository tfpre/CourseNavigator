"""
Pydantic models for FastAPI gateway request/response cycle.
These models will be exported to JSON Schema for TypeScript sync.
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Literal, Union
from datetime import datetime
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

class GraphVersionedResponse(BaseModel):
    """Base response model with graph versioning for cache invalidation (Friend's Priority 3)"""
    success: bool
    graph_version: Optional[int] = Field(default=None, description="Graph version for cache invalidation")
    error: Optional[ErrorDetail] = None

class RAGResponse(GraphVersionedResponse):
    """Response from RAG with graph endpoint"""
    answer: Optional[str] = None
    courses: List[CourseInfo] = []
    graph_context: Optional[GraphContext] = None
    query_metadata: Dict[str, Any] = {}
    
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

class PrerequisitePathResponse(GraphVersionedResponse):
    """Response for prerequisite path queries"""
    course: Optional[CourseInfo] = None
    prerequisite_path: Optional[GraphContext] = None
    missing_prerequisites: List[str] = []
    recommendations: List[CourseInfo] = []
    path_metadata: Dict[str, Any] = {}

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

class CentralityResponse(GraphVersionedResponse):
    """Response for centrality analysis"""
    data: Optional[Dict[str, Any]] = None
    computation_time_ms: Optional[int] = None

class CommunityRequest(BaseModel):
    """Request for community detection analysis"""
    algorithm: Literal["louvain", "greedy_modularity"] = "louvain"
    
    class Config:
        json_schema_extra = {
            "example": {
                "algorithm": "louvain"
            }
        }

class CommunityResponse(GraphVersionedResponse):
    """Response for community detection analysis"""
    data: Optional[Dict[str, Any]] = None
    computation_time_ms: Optional[int] = None

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

class CourseRecommendationResponse(GraphVersionedResponse):
    """Response for course recommendations"""
    data: Optional[Dict[str, Any]] = None
    computation_time_ms: Optional[int] = None

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

class ShortestPathResponse(GraphVersionedResponse):
    """Response for shortest prerequisite path"""
    data: Optional[Dict[str, Any]] = None
    computation_time_ms: Optional[int] = None

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

class AlternativePathsResponse(GraphVersionedResponse):
    """Response for alternative prerequisite paths"""
    data: Optional[Dict[str, Any]] = None
    computation_time_ms: Optional[int] = None

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

class SemesterPlanResponse(GraphVersionedResponse):
    """Response for semester optimization"""
    data: Optional[Dict[str, Any]] = None
    computation_time_ms: Optional[int] = None

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

class GraphSubgraphResponse(GraphVersionedResponse):
    """Response for graph subgraph data"""
    data: Optional[Dict[str, Any]] = None
    computation_time_ms: Optional[int] = None

# === Chat & Conversation Models ===

class StudentProfile(BaseModel):
    """
    Student academic profile for personalized recommendations.
    Designed for conversation state and academic planning context.
    
    Future-thinking design: Extensible for multi-major, preferences, and external integrations.
    """
    student_id: str = Field(..., description="Unique student identifier")
    major: Optional[str] = Field(None, description="Primary major (e.g., 'Computer Science')")
    minor: Optional[str] = Field(None, description="Minor field of study")
    year: Optional[Literal["freshman", "sophomore", "junior", "senior", "graduate"]] = Field(None, description="Academic year")
    completed_courses: List[str] = Field(default=[], description="List of completed course codes")
    current_courses: List[str] = Field(default=[], description="Currently enrolled course codes")
    interests: List[str] = Field(default=[], description="Academic interests and career goals")
    gpa: Optional[float] = Field(None, ge=0.0, le=4.0, description="Current GPA")
    preferences: Dict[str, Any] = Field(default={}, description="Learning preferences and constraints")
    
    @validator('completed_courses', 'current_courses', pre=True)
    def normalize_course_codes(cls, v):
        """Normalize course codes to consistent format"""
        if not v:
            return []
        return [course.strip().upper().replace(' ', ' ') for course in v if course.strip()]
    
class ConversationMessage(BaseModel):
    """
    Single message in a conversation thread with metadata for context tracking
    """
    role: Literal["user", "assistant", "system"] = Field(..., description="Message sender role")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Message timestamp")
    metadata: Dict[str, Any] = Field(default={}, description="Additional message metadata")
    token_count: Optional[int] = Field(None, description="Estimated token count for this message")

class ConversationState(BaseModel):
    """
    Persistent conversation state for context continuity.
    
    Best practices: Bounded size, Redis-serializable, conversation memory management.
    """
    conversation_id: str = Field(..., description="Unique conversation identifier")
    student_profile: StudentProfile = Field(..., description="Associated student profile")
    messages: List[ConversationMessage] = Field(default=[], description="Recent conversation history (max 20)")
    context_cache: Dict[str, Any] = Field(default={}, description="Cached context data with TTL metadata")
    active_recommendations: List[Dict[str, Any]] = Field(default=[], description="Current recommendations for /explain command")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    @validator('messages')
    def limit_message_history(cls, v):
        """Keep only last 20 messages for performance"""
        return v[-20:] if len(v) > 20 else v
    
class ChatRequest(BaseModel):
    """
    Chat request with conversation context and intelligent defaults.
    
    Design principles: 
    - Fail-fast validation
    - Reasonable defaults for demo
    - Extensible context preferences
    """
    message: str = Field(..., min_length=1, max_length=500, description="User message/question")
    conversation_id: Optional[str] = Field(None, description="Existing conversation ID for continuity")
    student_profile: Optional[StudentProfile] = Field(None, description="Student academic profile")
    context_preferences: Dict[str, bool] = Field(
        default={
            "include_prerequisites": True,
            "include_professor_ratings": True, 
            "include_difficulty_info": True,
            "include_enrollment_data": True,
            "include_similar_courses": True
        },
        description="Context inclusion preferences for response generation"
    )
    stream: bool = Field(default=True, description="Enable SSE streaming response")
    max_recommendations: int = Field(default=5, ge=1, le=10, description="Maximum course recommendations")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "What CS courses should I take next semester if I've completed CS 2110?",
                "student_profile": {
                    "student_id": "demo_student_1",
                    "major": "Computer Science",
                    "year": "sophomore",
                    "completed_courses": ["CS 1110", "CS 2110", "MATH 1920"]
                },
                "stream": True,
                "max_recommendations": 5
            }
        }
    
class ContextSource(BaseModel):
    """
    Individual context source with performance metadata.
    
    Friend's guidance: Deterministic token budgets with fail-fast timeouts.
    """
    source_type: Literal["vector_search", "graph_analysis", "professor_intel", "difficulty_data", "enrollment_data"] = Field(...)
    data: Dict[str, Any] = Field(..., description="Context data")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Context relevance confidence")
    token_count: int = Field(..., description="Estimated token usage")
    processing_time_ms: int = Field(..., description="Time to fetch this context")
    cache_hit: bool = Field(default=False, description="Whether this was served from cache")
    
# === GRADES AND PROVENANCE MODELS (Ground Truth: Information Reliability) ===

CourseCode = str  # e.g. "CS 4820" - standardized format

class GradeHistogram(BaseModel):
    """Grade distribution histogram with percentage breakdown"""
    grade_a_pct: float = Field(..., ge=0.0, le=100.0, description="A grade percentage")
    grade_b_pct: float = Field(..., ge=0.0, le=100.0, description="B grade percentage") 
    grade_c_pct: float = Field(..., ge=0.0, le=100.0, description="C grade percentage")
    grade_d_pct: float = Field(..., ge=0.0, le=100.0, description="D grade percentage")
    grade_f_pct: float = Field(..., ge=0.0, le=100.0, description="F grade percentage")
    
    @validator("grade_f_pct")
    def validate_total_percentages(cls, v, values):
        """Ensure percentages sum to ~100% (allow small rounding errors)"""
        total = v
        for field in ["grade_a_pct", "grade_b_pct", "grade_c_pct", "grade_d_pct"]:
            if field in values:
                total += values[field]
        if not 95.0 <= total <= 105.0:  # Allow 5% tolerance for rounding
            raise ValueError(f"Grade percentages sum to {total}%, should be ~100%")
        return v

class GradesProvenance(BaseModel):
    """Provenance tracking for grade data - enables trust and auditability"""
    tag: str = Field(..., description="Cache tag (e.g., 'grades')")
    version: int = Field(..., description="Tag version from Redis")
    file_hash: str = Field(..., description="SHA256 of source CSV file")
    refreshed_at: datetime = Field(..., description="When this data was last refreshed")
    record_count: int = Field(..., description="Number of source records")

class CourseGradesStats(BaseModel):
    """
    Complete course grade statistics with provenance.
    Implements Ground Truth: Information Consolidation + Information Reliability
    """
    course_code: CourseCode = Field(..., description="Standardized course code (e.g., 'CS 4820')")
    terms: List[str] = Field(..., description="Terms included in statistics")
    mean_gpa: float = Field(..., ge=0.0, le=4.3, description="Mean GPA across all terms")
    stdev_gpa: float = Field(..., ge=0.0, description="Standard deviation of GPA")
    pass_rate: float = Field(..., ge=0.0, le=1.0, description="Pass rate (D or better)")
    histogram: GradeHistogram = Field(..., description="Grade distribution breakdown")
    enrollment_count: int = Field(..., description="Total enrollment across terms")
    difficulty_percentile: Optional[int] = Field(None, ge=0, le=100, description="Difficulty ranking (higher = harder)")
    provenance: GradesProvenance = Field(..., description="Data source tracking")

class Recommendation(BaseModel):
    """
    Single course recommendation with structured reasoning and provenance.
    Implements Ground Truth: Actionable Prioritization + Information Reliability
    """
    course_code: CourseCode = Field(..., description="Course identifier")
    title: str = Field(..., description="Course title")
    rationale: str = Field(..., description="Why this course is recommended")
    priority: int = Field(..., ge=1, le=5, description="Priority ranking (1 = highest)")
    next_action: Literal["add_to_plan", "check_prereqs", "consider_alternative", "waitlist_monitor"] = Field(
        ..., description="Recommended next step"
    )
    difficulty_warning: Optional[str] = Field(None, description="Workload or difficulty advisory")
    # Reliability: include source blocks with provenance
    source: Dict[str, Dict] = Field(default_factory=dict, description="Source data with provenance")

class ChatResponseJSON(BaseModel):
    """
    Strict JSON envelope for chat responses - enforces structured output.
    Implements Ground Truth: Actionable Prioritization + Information Reliability
    """
    recommendations: List[Recommendation] = Field(..., description="Course recommendations")
    constraints: List[str] = Field(default=[], description="Limitations or conflicts identified")
    next_actions: List[Dict[str, str]] = Field(default=[], description="Actionable follow-up steps")
    notes: Optional[str] = Field(None, description="Additional context or advice")
    provenance: List[Dict[str, Any]] = Field(default=[], description="Data sources used")

class TokenBudget(BaseModel):
    """
    Token budget allocation following friend's deterministic allocation strategy.
    
    Budget allocation:
    - Top-5 vector courses (~150 tok)
    - Graph edges (≤10 edges, 60 tok) 
    - Prof blob (≤120 tok)
    - Difficulty/enrollment (≤80 tok)
    - Student profile (≤200 tok)
    - Template scaffolding (~150 tok)
    Total: ~1.1k tokens
    """
    total_budget: int = Field(default=1000, description="Total token budget")
    allocations: Dict[str, int] = Field(
        default={
            "vector_courses": 150,
            "graph_edges": 60, 
            "professor_intel": 120,
            "difficulty_enrollment": 80,
            "student_profile": 200,
            "template_scaffolding": 150,
            "response_buffer": 240  # Reserve for response generation
        },
        description="Token allocation by context type"
    )
    used_tokens: Dict[str, int] = Field(default={}, description="Actual tokens used by context type")
    remaining_budget: int = Field(default=1000, description="Remaining available tokens")
    
    def allocate_tokens(self, context_type: str, tokens_needed: int) -> bool:
        """Allocate tokens for a specific context type, respecting budget"""
        allocated = self.allocations.get(context_type, 0)
        used = self.used_tokens.get(context_type, 0)
        
        if used + tokens_needed <= allocated:
            self.used_tokens[context_type] = used + tokens_needed
            self.remaining_budget -= tokens_needed
            return True
        return False
    
class ChatContext(BaseModel):
    """
    Aggregated context for LLM prompt construction with performance tracking.
    
    Architecture: Multi-context fusion with fail-fast timeouts (friend's guidance).
    """
    request_id: str = Field(..., description="Unique request identifier for tracing")
    student_profile: Optional[StudentProfile] = Field(None)
    context_sources: List[ContextSource] = Field(default=[], description="All context sources")
    token_budget: TokenBudget = Field(default_factory=TokenBudget, description="Token allocation and tracking")
    processing_metadata: Dict[str, Any] = Field(
        default={"context_fetch_start": None, "context_fetch_end": None}, 
        description="Processing timing and stats"
    )
    prompt_template: Optional[str] = Field(None, description="Generated prompt for LLM")
    
class ChatStreamChunk(BaseModel):
    """
    Single chunk in SSE stream with rich metadata for frontend processing.
    
    Stream types support: tokens, course highlights, context info, errors.
    """
    chunk_id: int = Field(..., description="Chunk sequence number")
    content: str = Field(..., description="Chunk content")
    chunk_type: Literal["token", "course_highlight", "context_info", "thinking", "error", "done"] = Field(...)
    metadata: Dict[str, Any] = Field(default={}, description="Chunk-specific metadata")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
    
class ChatResponse(GraphVersionedResponse):
    """
    Complete chat response with recommendations and context attribution.
    
    Includes conversation state for continuity and explainability data.
    """
    conversation_id: str = Field(..., description="Conversation identifier")
    response_text: str = Field(..., description="Generated response text")
    recommended_courses: List[Dict[str, Any]] = Field(default=[], description="Course recommendations with metadata")
    context_used: List[str] = Field(default=[], description="Context sources that influenced response")
    processing_time_ms: int = Field(..., description="Total processing time")
    token_usage: Dict[str, int] = Field(default={}, description="Token usage breakdown by context type")
    confidence_scores: Dict[str, float] = Field(default={}, description="Recommendation confidence scores")
    conversation_state: Optional[ConversationState] = Field(None, description="Updated conversation state")
    llm_provider: str = Field(default="unknown", description="LLM provider used (phi-3-mini, gpt-4o)")
    fallback_triggered: bool = Field(default=False, description="Whether fallback LLM was used")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

# === Slash Command Models ===

class ExplainRequest(BaseModel):
    """
    Request for /explain command to show recommendation reasoning.
    
    Friend's suggestion: Slack-style slash command for power users.
    """
    conversation_id: str = Field(..., description="Conversation ID")
    recommendation_index: int = Field(..., ge=0, description="Index of recommendation to explain (0-based)")
    explanation_type: Literal["attention", "graph_path", "context_sources", "full"] = Field(
        default="context_sources", 
        description="Type of explanation to provide"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "conversation_id": "conv_123",
                "recommendation_index": 0,
                "explanation_type": "context_sources"
            }
        }
    
class ExplainResponse(GraphVersionedResponse):
    """
    Response for /explain command with visualization data for frontend.
    
    Supports attention heat-maps, graph path highlighting, context attribution.
    """
    explanation_type: str = Field(..., description="Type of explanation provided")
    visualization_data: Dict[str, Any] = Field(..., description="Data for frontend visualization")
    explanation_text: str = Field(..., description="Human-readable explanation")
    recommendation_context: Dict[str, Any] = Field(default={}, description="Original recommendation context")
    processing_time_ms: int = Field(..., description="Time to generate explanation")

# Export all models for schema generation
__all__ = [
    # Core search and graph models
    "SearchMode",
    "CourseInfo", 
    "PrerequisiteEdge",
    "GraphContext",
    "RAGRequest",
    "PrerequisitePathRequest",
    "ErrorDetail",
    "GraphVersionedResponse",
    "RAGResponse", 
    "PrerequisitePathResponse",
    "HealthResponse",
    
    # Graph algorithms models
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
    "GraphSubgraphResponse",
    
    # Chat and conversation models
    "StudentProfile",
    "ConversationMessage",
    "ConversationState",
    "ChatRequest",
    "ContextSource",
    "TokenBudget", 
    "ChatContext",
    "ChatStreamChunk",
    "ChatResponse",
    
    # Slash command models
    "ExplainRequest",
    "ExplainResponse"
]