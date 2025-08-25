"""
FastAPI Gateway for Cornell Course Navigator
Combines Qdrant vector search with Neo4j graph queries
"""

import os
import time
import logging
import asyncio
import contextlib
import json
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.security import HTTPBearer
import uvicorn
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter

from .models import (
    RAGRequest, RAGResponse, PrerequisitePathRequest, PrerequisitePathResponse,
    HealthResponse, ErrorDetail, CourseInfo, GraphContext, PrerequisiteEdge,
    CentralityRequest, CentralityResponse, CommunityRequest, CommunityResponse,
    CourseRecommendationRequest, CourseRecommendationResponse,
    ShortestPathRequest, ShortestPathResponse, AlternativePathsRequest, AlternativePathsResponse,
    SemesterPlanRequest, SemesterPlanResponse,
    GraphSubgraphRequest, GraphSubgraphResponse,
    # Chat and conversation models
    ChatRequest, ChatResponse, ChatStreamChunk, ExplainRequest, ExplainResponse,
    StudentProfile, ConversationState,
    # Grades and provenance models
    CourseGradesStats, GradeHistogram, GradesProvenance, ChatResponseJSON
)
from .services.vector_service import VectorService
from .services.graph_service import GraphService
from .services.rag_service import RAGService
# FACADE PATTERN: Use decomposed service facade instead of God Object
from .services.graph_algorithms_facade import GraphAlgorithmsFacade as GraphAlgorithmsService
from .services.performance_service import performance_service
# CHAT ORCHESTRATOR: Multi-context conversation AI
from .services.chat_orchestrator import ChatOrchestratorService
from .services.grades_service import GradesService
from .services.tag_cache import TagCache
from .routes import profiles as profiles_router
from .routes import calendar_export as calendar_router

# Import graph metadata service for cache versioning (Friend's Priority 3)
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from graph_analysis.graph_metadata import GraphMetadataService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# HTTP request counter metric for observability (following newfix.md guidance)
# Reload-safe metric registration to prevent uvicorn --reload errors
try:
    from prometheus_client import REGISTRY
    if 'http_requests_total' not in {m._name for m in REGISTRY._collector_to_names.keys()}:
        http_requests_total = Counter(
            'http_requests_total',
            'Total HTTP requests by method, path template, and status',
            ['method', 'route', 'status']
        )
    else:
        # Metric already registered, find the existing one
        for collector in REGISTRY._collector_to_names.keys():
            if hasattr(collector, '_name') and collector._name == 'http_requests_total':
                http_requests_total = collector
                break
except:
    # Fallback: create metric normally (first run or prometheus not available)
    http_requests_total = Counter(
        'http_requests_total',
        'Total HTTP requests by method, path template, and status',
        ['method', 'route', 'status']
    )

# Initialize FastAPI app
app = FastAPI(
    title="Cornell Course Navigator Gateway",
    description="FastAPI gateway combining vector search and graph queries",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://nextjs:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# HTTP request counter middleware for observability
@app.middleware("http")
async def http_request_counter_middleware(request, call_next):
    """Count all HTTP requests with method, route template, and status labels"""
    response = await call_next(request)
    
    # Extract route template (path pattern) for better aggregation
    route = request.url.path
    if request.scope.get("route"):
        route = request.scope["route"].path
    
    # Count the request
    http_requests_total.labels(
        method=request.method,
        route=route, 
        status=str(response.status_code)
    ).inc()
    
    return response

# Global service instances (will be initialized on startup)
vector_service: Optional[VectorService] = None
graph_service: Optional[GraphService] = None
rag_service: Optional[RAGService] = None
graph_algorithms_service: Optional[GraphAlgorithmsService] = None
graph_metadata_service: Optional[GraphMetadataService] = None
chat_orchestrator_service: Optional[ChatOrchestratorService] = None
grades_service: Optional[GradesService] = None
redis_client = None

# Security for chat endpoints
security = HTTPBearer(auto_error=False)

# get_redis moved to dependencies.py to avoid circular imports

async def get_vector_service() -> VectorService:
    """Dependency to get vector service instance"""
    if vector_service is None:
        raise HTTPException(
            status_code=503, 
            detail="Vector service not available"
        )
    return vector_service

async def get_graph_service() -> GraphService:
    """Dependency to get graph service instance"""
    if graph_service is None:
        raise HTTPException(
            status_code=503,
            detail="Graph service not available"
        )
    return graph_service

async def get_rag_service() -> RAGService:
    """Dependency to get RAG service instance"""
    if rag_service is None:
        raise HTTPException(
            status_code=503,
            detail="RAG service not available"
        )
    return rag_service

async def get_graph_algorithms_service() -> GraphAlgorithmsService:
    """Dependency to get graph algorithms service instance"""
    if graph_algorithms_service is None:
        raise HTTPException(
            status_code=503,
            detail="Graph algorithms service not available"
        )
    return graph_algorithms_service

async def get_graph_metadata_service() -> GraphMetadataService:
    """Dependency to get graph metadata service instance"""
    if graph_metadata_service is None:
        raise HTTPException(
            status_code=503,
            detail="Graph metadata service not available"
        )
    return graph_metadata_service

async def get_chat_orchestrator_service() -> ChatOrchestratorService:
    """Dependency to get chat orchestrator service instance"""
    if chat_orchestrator_service is None:
        raise HTTPException(
            status_code=503,
            detail="Chat service not available"
        )
    return chat_orchestrator_service

async def get_grades_service() -> GradesService:
    """Dependency to get grades service instance"""
    if grades_service is None:
        raise HTTPException(
            status_code=503,
            detail="Grades service not available"
        )
    return grades_service

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global vector_service, graph_service, rag_service, graph_algorithms_service, graph_metadata_service, chat_orchestrator_service, grades_service, redis_client
    
    logger.info("Initializing Cornell Course Navigator Gateway...")
    
    # Check for production safety - no accidental mocks in prod
    use_mock_services = os.getenv("USE_MOCK_SERVICES", "false").lower() == "true"
    environment = os.getenv("ENVIRONMENT", "development")
    
    if environment == "production" and use_mock_services:
        logger.error("CRITICAL: Mock services enabled in production environment!")
        raise RuntimeError("Production deployment cannot use mock services. Check USE_MOCK_SERVICES and ENVIRONMENT variables.")
    
    try:
        # Initialize Redis client for caching (PERFORMANCE CRITICAL)
        redis_client = None
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis.asyncio as redis
                redis_client = redis.from_url(redis_url, decode_responses=True)
                # Test connection
                await redis_client.ping()
                logger.info(f"Redis connected successfully: {redis_url}")
            except Exception as e:
                logger.warning(f"Redis connection failed, continuing without cache: {e}")
                redis_client = None
        else:
            logger.warning("REDIS_URL not set, services will run without caching")
        
        # Initialize services with Redis caching
        vector_service = VectorService(
            url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            collection_name=os.getenv("QDRANT_COLLECTION_NAME", "cornell_courses"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            redis_client=redis_client
        )
        
        graph_service = GraphService(
            uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            username=os.getenv("NEO4J_USERNAME", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD", "password"),
            redis_client=redis_client
        )
        
        rag_service = RAGService(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            vector_service=vector_service,
            graph_service=graph_service
        )
        
        graph_algorithms_service = GraphAlgorithmsService(
            graph_service=graph_service
        )
        
        # Initialize graph metadata service for cache versioning (Priority 3)
        graph_metadata_service = GraphMetadataService(
            neo4j_service=graph_service
        )
        
        # Initialize chat orchestrator service for conversational AI
        chat_orchestrator_service = ChatOrchestratorService(
            vector_service=vector_service,
            graph_service=graph_service,
            rag_service=rag_service,
            redis_client=redis_client,  # FIXED: Redis client now initialized
            local_llm_client=None,  # TODO: Initialize local LLM
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # Initialize grades service for real Cornell data with provenance tracking
        grades_service = GradesService(
            redis_client=redis_client,
            csv_path=os.getenv("GRADES_CSV", "data/cornell_grades.csv"),
            tag="grades",
            ttl_seconds=24 * 3600  # 24 hour cache
        )
        
        # Test connections in non-development mode
        try:
            await vector_service.health_check()
            await graph_service.health_check()
        except Exception as e:
            if environment == "production":
                logger.exception(f"CRITICAL: Service health checks failed in production: {e}")
                raise RuntimeError(f"Production services unavailable: {e}")
            else:
                logger.warning(f"Service health checks failed, enabling mock mode: {e}")
                # Enable mock mode for graph service when health check fails
                graph_service.enable_mock_mode()
        
        # Initialize GDS graph projections at startup (V2 Architecture)
        # This eliminates race conditions and cold-start latency per request
        logger.info("Creating GDS graph projections for production stability...")
        
        try:
            # Initialize centrality service projections
            if hasattr(graph_algorithms_service, 'centrality_service'):
                await graph_algorithms_service.centrality_service._ensure_graph_exists()
                logger.info("✅ Prerequisite graph projection created")
            
            # Initialize community service projections  
            if hasattr(graph_algorithms_service, 'community_service'):
                await graph_algorithms_service.community_service._ensure_similarity_graph_exists()
                logger.info("✅ Similarity graph projection created")
                
            # Initialize pathfinding service projections
            if hasattr(graph_algorithms_service, 'pathfinding_service'):
                await graph_algorithms_service.pathfinding_service._ensure_prerequisite_graph_exists()
                logger.info("✅ Pathfinding graph projection verified")
                
            logger.info("All GDS graph projections ready - eliminating per-request overhead")
            
        except Exception as e:
            logger.warning(f"GDS projection initialization failed (will retry per-request): {e}")
            # Don't fail startup - algorithms can still create projections on-demand
        
        # Start background task for SCARD reconciliation (prevents Redis index drift)
        # Following newfix.md guidance: prevent silent drift/redis noise during demo
        if grades_service and grades_service.provenance:
            async def reconcile_scard_background():
                """Background task to reconcile provenance index sizes every minute"""
                while True:
                    try:
                        await asyncio.sleep(60)  # Wait 60 seconds
                        await grades_service.provenance.reconcile_index_sizes()
                    except Exception as e:
                        logger.warning(f"SCARD reconciliation background task failed: {e}")
            
            # Start the background task
            asyncio.create_task(reconcile_scard_background())
            logger.info("SCARD reconciliation background task started (60s interval)")
        
        logger.info("All services initialized successfully")
        
    except Exception as e:
        logger.exception(f"Failed to initialize services: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown - prevents connection leaks"""
    global vector_service, graph_service, rag_service, redis_client, chat_orchestrator_service
    
    logger.info("Shutting down Cornell Course Navigator Gateway...")
    
    # CRITICAL: Close all connections to prevent resource leaks
    try:
        if graph_service:
            await graph_service.close()
            logger.info("Graph service connections closed")
    except Exception as e:
        logger.error(f"Error closing graph service: {e}")
    
    try:
        if vector_service:
            await vector_service.close()
            logger.info("Vector service connections closed")
    except Exception as e:
        logger.error(f"Error closing vector service: {e}")
    
    try:
        if chat_orchestrator_service and hasattr(chat_orchestrator_service, "llm_router"):
            await chat_orchestrator_service.llm_router.close()
            logger.info("LLM router clients closed")
    except Exception as e:
        logger.error(f"Error closing LLM router: {e}")

    try:
        if chat_orchestrator_service:
            await chat_orchestrator_service.close()
            logger.info("Chat orchestrator service connections closed")
    except Exception as e:
        logger.error(f"Error closing chat orchestrator service: {e}")
    
    try:
        if redis_client:
            await redis_client.close()
            logger.info("Redis connections closed")
    except Exception as e:
        logger.error(f"Error closing Redis: {e}")
    
    logger.info("Shutdown complete")

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    services = {}
    overall_status = "healthy"
    
    # Check vector service
    try:
        if vector_service:
            await vector_service.health_check()
            services["qdrant"] = True
        else:
            services["qdrant"] = False
            overall_status = "unhealthy"
    except Exception:
        services["qdrant"] = False
        overall_status = "degraded"
    
    # Check graph service  
    try:
        if graph_service:
            await graph_service.health_check()
            services["neo4j"] = True
        else:
            services["neo4j"] = False
            overall_status = "unhealthy"
    except Exception:
        services["neo4j"] = False
        overall_status = "degraded"
    
    return HealthResponse(
        status=overall_status,
        services=services,
        timestamp=datetime.utcnow().isoformat()
    )

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

app.include_router(profiles_router.router)
app.include_router(calendar_router.router)

@app.post("/api/rag_with_graph", response_model=RAGResponse)
async def rag_with_graph(
    request: RAGRequest,
    rag_svc: RAGService = Depends(get_rag_service)
):
    """
    Main RAG endpoint combining vector search with graph context.
    
    This endpoint:
    1. Queries Qdrant for semantically similar courses
    2. Expands context using Neo4j graph relationships  
    3. Generates response using LLM with combined context
    """
    start_time = time.time()
    
    try:
        logger.info(f"Processing RAG query: {request.query[:50]}...")
        
        # Execute RAG with graph enhancement
        result = await rag_svc.process_query(request)
        
        # Add timing metadata
        total_time_ms = int((time.time() - start_time) * 1000)
        result.query_metadata["total_time_ms"] = total_time_ms
        
        logger.info(f"RAG query completed in {total_time_ms}ms")
        return result
        
    except Exception as e:
        logger.exception(f"RAG query failed: {e}")
        
        return RAGResponse(
            success=False,
            error=ErrorDetail(
                code="RAG_PROCESSING_ERROR",
                message="Failed to process RAG query",
                details={"error": str(e)}
            )
        )

@app.post("/api/prerequisite_path", response_model=PrerequisitePathResponse)
async def prerequisite_path(
    request: PrerequisitePathRequest,
    graph_svc: GraphService = Depends(get_graph_service)
):
    """
    Get prerequisite path for a specific course. 
    
    Returns the full dependency chain needed to take the target course.
    """
    start_time = time.time()
    
    try:
        logger.info(f"Getting prerequisite path for: {request.course_id}")
        
        # Get prerequisite path from graph
        result = await graph_svc.get_prerequisite_path(request)
        
        # Add timing metadata
        total_time_ms = int((time.time() - start_time) * 1000)
        result.path_metadata["total_time_ms"] = total_time_ms
        
        logger.info(f"Prerequisite path query completed in {total_time_ms}ms")
        return result
        
    except Exception as e:
        logger.exception(f"Prerequisite path query failed: {e}")
        
        return PrerequisitePathResponse(
            success=False,
            error=ErrorDetail(
                code="PREREQ_PATH_ERROR", 
                message="Failed to get prerequisite path",
                details={"error": str(e)}
            )
        )

# === Graph Algorithms Endpoints ===

@app.post("/api/centrality", response_model=CentralityResponse)
async def get_course_centrality(
    request: CentralityRequest,
    service: GraphAlgorithmsService = Depends(get_graph_algorithms_service),
    metadata_service: GraphMetadataService = Depends(get_graph_metadata_service)
):
    """
    Get course centrality analysis including PageRank, bridge courses, and gateway courses.
    
    This endpoint calculates:
    - PageRank centrality (most important courses in curriculum)
    - Bridge courses (high betweenness centrality)
    - Gateway courses (high prerequisite requirements)
    
    PRIORITY 3 IMPLEMENTATION: Includes graph_version for cache invalidation
    """
    try:
        logger.info(f"Processing centrality request: top_n={request.top_n}")
        
        # Get current graph metadata for versioning (Friend's Priority 3)
        graph_metadata = await metadata_service.get_current_metadata()
        
        result = await service.get_course_centrality(
            top_n=request.top_n,
            damping_factor=request.damping_factor,
            min_betweenness=request.min_betweenness,
            min_in_degree=request.min_in_degree
        )
        
        # Inject graph version for cache invalidation
        response = CentralityResponse(**result)
        response.graph_version = graph_metadata.version
        
        return response
        
    except Exception as e:
        logger.exception(f"Centrality analysis failed: {e}")
        return CentralityResponse(
            success=False,
            graph_version=1,  # Fallback version on error
            error=ErrorDetail(
                code="CENTRALITY_ERROR",
                message="Failed to compute centrality analysis",
                details={"error": str(e)}
            )
        )

@app.post("/api/communities", response_model=CommunityResponse)
async def get_course_communities(
    request: CommunityRequest,
    service: GraphAlgorithmsService = Depends(get_graph_algorithms_service)
):
    """
    Get course community detection analysis.
    
    This endpoint performs:
    - Community detection using Louvain or greedy modularity algorithms
    - Department overlap analysis
    - Course clustering with modularity scores
    """
    try:
        logger.info(f"Processing community detection request: algorithm={request.algorithm}")
        
        result = await service.get_course_communities(algorithm=request.algorithm)
        
        return CommunityResponse(**result)
        
    except Exception as e:
        logger.exception(f"Community detection failed: {e}")
        return CommunityResponse(
            success=False,
            error=ErrorDetail(
                code="COMMUNITY_ERROR",
                message="Failed to compute community analysis",
                details={"error": str(e)}
            )
        )

@app.post("/api/course_recommendations", response_model=CourseRecommendationResponse)
async def get_course_recommendations(
    request: CourseRecommendationRequest,
    service: GraphAlgorithmsService = Depends(get_graph_algorithms_service)
):
    """
    Get course recommendations based on community membership and graph proximity.
    """
    try:
        logger.info(f"Processing recommendation request for: {request.course_code}")
        
        result = await service.get_course_recommendations(
            course_code=request.course_code,
            num_recommendations=request.num_recommendations
        )
        
        return CourseRecommendationResponse(**result)
        
    except Exception as e:
        logger.exception(f"Course recommendation failed: {e}")
        return CourseRecommendationResponse(
            success=False,
            error=ErrorDetail(
                code="RECOMMENDATION_ERROR",
                message="Failed to generate recommendations",
                details={"error": str(e)}
            )
        )

@app.post("/api/shortest_path", response_model=ShortestPathResponse)
async def get_shortest_prerequisite_path(
    request: ShortestPathRequest,
    service: GraphAlgorithmsService = Depends(get_graph_algorithms_service)
):
    """
    Get shortest prerequisite path to target course using Dijkstra's algorithm.
    """
    try:
        logger.info(f"Processing shortest path request to: {request.target_course}")
        
        result = await service.get_shortest_path(
            target_course=request.target_course,
            completed_courses=request.completed_courses
        )
        
        return ShortestPathResponse(**result)
        
    except Exception as e:
        logger.exception(f"Shortest path calculation failed: {e}")
        return ShortestPathResponse(
            success=False,
            error=ErrorDetail(
                code="SHORTEST_PATH_ERROR",
                message="Failed to compute shortest path",
                details={"error": str(e)}
            )
        )

@app.post("/api/alternative_paths", response_model=AlternativePathsResponse)
async def get_alternative_prerequisite_paths(
    request: AlternativePathsRequest,
    service: GraphAlgorithmsService = Depends(get_graph_algorithms_service)
):
    """
    Get multiple alternative prerequisite paths to target course.
    """
    try:
        logger.info(f"Processing alternative paths request to: {request.target_course}")
        
        result = await service.get_alternative_paths(
            target_course=request.target_course,
            completed_courses=request.completed_courses,
            num_alternatives=request.num_alternatives
        )
        
        return AlternativePathsResponse(**result)
        
    except Exception as e:
        logger.exception(f"Alternative paths calculation failed: {e}")
        return AlternativePathsResponse(
            success=False,
            error=ErrorDetail(
                code="ALTERNATIVE_PATHS_ERROR",
                message="Failed to compute alternative paths",
                details={"error": str(e)}
            )
        )

@app.post("/api/semester_plan", response_model=SemesterPlanResponse)
async def optimize_semester_plan(
    request: SemesterPlanRequest,
    service: GraphAlgorithmsService = Depends(get_graph_algorithms_service)
):
    """
    Optimize course sequence across multiple semesters for graduation planning.
    """
    try:
        logger.info(f"Processing semester optimization for {len(request.target_courses)} courses")
        
        result = await service.optimize_semester_plan(
            target_courses=request.target_courses,
            completed_courses=request.completed_courses,
            semesters_available=request.semesters_available,
            max_credits_per_semester=request.max_credits_per_semester
        )
        
        return SemesterPlanResponse(**result)
        
    except Exception as e:
        logger.exception(f"Semester optimization failed: {e}")
        return SemesterPlanResponse(
            success=False,
            error=ErrorDetail(
                code="SEMESTER_OPTIMIZATION_ERROR",
                message="Failed to optimize semester plan",
                details={"error": str(e)}
            )
        )

@app.post("/api/graph/subgraph", response_model=GraphSubgraphResponse)
async def get_graph_subgraph(
    request: GraphSubgraphRequest,
    service: GraphAlgorithmsService = Depends(get_graph_algorithms_service),
    metadata_service: GraphMetadataService = Depends(get_graph_metadata_service)
):
    """
    Get graph subgraph data for visualization with graph versioning.
    
    This endpoint provides:
    - Course nodes with centrality scores and community assignments
    - Prerequisite edges filtered by importance
    - Optimized for frontend visualization performance
    - PRIORITY 3: Includes graph_version for React layout cache invalidation
    """
    try:
        logger.info(f"Processing graph subgraph request: max_nodes={request.max_nodes}, max_edges={request.max_edges}")
        
        # Get current graph metadata for versioning (Critical for frontend cache!)
        graph_metadata = await metadata_service.get_current_metadata()
        
        result = await service.get_graph_subgraph(
            max_nodes=request.max_nodes,
            max_edges=request.max_edges,
            include_centrality=request.include_centrality,
            include_communities=request.include_communities,
            filter_by_subject=request.filter_by_subject
        )
        
        # Inject graph version for React layout cache invalidation
        response = GraphSubgraphResponse(**result)
        response.graph_version = graph_metadata.version
        
        # Add metadata to help with debugging cache issues
        if 'metadata' not in response.data:
            response.data['metadata'] = {}
        response.data['metadata']['graph_version'] = graph_metadata.version
        response.data['metadata']['last_updated'] = graph_metadata.last_updated.isoformat()
        
        return response
        
    except Exception as e:
        logger.exception(f"Graph subgraph failed: {e}")
        return GraphSubgraphResponse(
            success=False,
            graph_version=1,  # Fallback version on error
            error=ErrorDetail(
                code="GRAPH_SUBGRAPH_ERROR",
                message="Failed to get graph subgraph",
                details={"error": str(e)}
            )
        )

# === Performance Monitoring Endpoints ===

@app.get("/api/performance/metrics")
async def get_performance_metrics(endpoint: Optional[str] = None):
    """
    Get performance metrics for API endpoints.
    Optionally filter by specific endpoint.
    """
    try:
        metrics = performance_service.get_performance_metrics(endpoint)
        return {
            "success": True,
            "data": {
                "metrics": {ep: {
                    "endpoint": metric.endpoint,
                    "request_count": metric.request_count,
                    "avg_response_time_ms": round(metric.avg_response_time_ms, 2),
                    "min_response_time_ms": round(metric.min_response_time_ms, 2),
                    "max_response_time_ms": round(metric.max_response_time_ms, 2),
                    "p95_response_time_ms": round(metric.p95_response_time_ms, 2),
                    "error_rate": round(metric.error_rate, 4),
                    "last_24h_requests": metric.last_24h_requests
                } for ep, metric in metrics.items()},
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    except Exception as e:
        logger.exception(f"Failed to get performance metrics: {e}")
        return {
            "success": False,
            "error": {
                "code": "METRICS_ERROR",
                "message": "Failed to retrieve performance metrics",
                "details": {"error": str(e)}
            }
        }

@app.get("/api/performance/health")
async def get_system_health():
    """
    Get current system health and performance status.
    """
    try:
        health = performance_service.get_system_health()
        status_check = performance_service.check_performance_thresholds()
        recommendations = performance_service.get_optimization_recommendations()
        
        return {
            "success": True,
            "data": {
                "system_health": {
                    "cpu_usage_percent": round(health.cpu_usage_percent, 1),
                    "memory_usage_percent": round(health.memory_usage_percent, 1),
                    "disk_usage_percent": round(health.disk_usage_percent, 1),
                    "active_connections": health.active_connections,
                    "cache_hit_rate": round(health.cache_hit_rate, 3),
                    "uptime_seconds": round(health.uptime_seconds, 1)
                },
                "performance_status": status_check,
                "optimization_recommendations": recommendations,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    except Exception as e:
        logger.exception(f"Failed to get system health: {e}")
        return {
            "success": False,
            "error": {
                "code": "HEALTH_CHECK_ERROR",
                "message": "Failed to retrieve system health",
                "details": {"error": str(e)}
            }
        }

@app.post("/api/performance/reset")
async def reset_performance_metrics():
    """
    Reset all performance metrics (admin endpoint).
    """
    try:
        performance_service.reset_metrics()
        return {
            "success": True,
            "message": "Performance metrics reset successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.exception(f"Failed to reset performance metrics: {e}")
        return {
            "success": False,
            "error": {
                "code": "RESET_ERROR",
                "message": "Failed to reset performance metrics",
                "details": {"error": str(e)}
            }
        }

# === Chat & Conversational AI Endpoints ===

@app.post("/api/chat")
async def chat_stream(
    request: ChatRequest,
    chat_service: ChatOrchestratorService = Depends(get_chat_orchestrator_service)
):
    """
    Conversational AI endpoint with robust Server-Sent Events streaming.
    
    Implements UX Friction Minimization ground truth:
    - <500ms perceived latency via streaming
    - Resilient SSE with heartbeats and auto-reconnection
    - Client disconnect detection and graceful cancellation
    - Multi-context fusion with deterministic token budgets
    
    Performance target: First chunk <200ms, full response <450ms P95
    """
    from .utils.sse import resilient_sse_stream, create_sse_response_headers
    
    async def content_generator():
        """Convert chat service chunks to SSE-compatible string stream"""
        try:
            async for chunk in chat_service.process_chat_request(request):
                # Convert ChatStreamChunk to JSON string for SSE
                yield chunk.json()
        except Exception as e:
            logger.exception(f"Chat processing error: {e}")
            # Yield error as JSON
            error_chunk = {
                "chunk_id": 999,
                "content": "I encountered an error processing your request. Please try again.",
                "chunk_type": "error",
                "metadata": {
                    "error": str(e),
                    "recoverable": True,
                    "retry_suggested": True
                },
                "timestamp": time.time()
            }
            yield json.dumps(error_chunk)
    
    return StreamingResponse(
        resilient_sse_stream(content_generator(), request, event_type="message"),
        media_type="text/event-stream",
        headers=create_sse_response_headers()
    )

@app.post("/api/chat/explain", response_model=ExplainResponse)
async def explain_recommendation(
    request: ExplainRequest,
    chat_service: ChatOrchestratorService = Depends(get_chat_orchestrator_service)
):
    """
    /explain slash command for power users - show recommendation reasoning. 
    
    Friend's suggestion: Slack-style command showing attention heat-maps, 
    graph paths, and context attribution for course recommendations.
    """
    try:
        logger.info(f"Processing /explain command: conv={request.conversation_id}, idx={request.recommendation_index}")
        
        result = await chat_service.generate_explanation(
            conversation_id=request.conversation_id,
            recommendation_index=request.recommendation_index,
            explanation_type=request.explanation_type
        )
        
        if result.get("success"):
            return ExplainResponse(
                success=True,
                explanation_type=result["explanation_type"],
                visualization_data=result["visualization_data"],
                explanation_text=result["explanation_text"],
                recommendation_context=result["recommendation_context"],
                processing_time_ms=int(time.time() * 1000)  # TODO: Track actual processing time
            )
        else:
            return ExplainResponse(
                success=False,
                error=ErrorDetail(
                    code="EXPLAIN_ERROR",
                    message=result.get("error", "Failed to generate explanation"),
                    details={"recommendation_index": request.recommendation_index}
                ),
                explanation_type=request.explanation_type,
                visualization_data={},
                explanation_text="",
                processing_time_ms=0
            )
            
    except Exception as e:
        logger.exception(f"Explain recommendation failed: {e}")
        return ExplainResponse(
            success=False,
            error=ErrorDetail(
                code="EXPLAIN_ERROR",
                message="Failed to generate explanation",
                details={"error": str(e)}
            ),
            explanation_type=request.explanation_type,
            visualization_data={},
            explanation_text="",
            processing_time_ms=0
        )

@app.get("/api/chat/conversation/{conversation_id}")
async def get_conversation_history(
    conversation_id: str,
    chat_service: ChatOrchestratorService = Depends(get_chat_orchestrator_service)
):
    """
    Retrieve conversation history for UI state restoration and context display.
    """
    try:
        conversation_state = await chat_service.get_conversation_state(conversation_id)
        
        if conversation_state:
            return {
                "success": True,
                "conversation_id": conversation_id,
                "data": {
                    "student_profile": conversation_state.student_profile.dict(),
                    "message_count": len(conversation_state.messages),
                    "last_messages": conversation_state.messages[-10:],  # Last 10 for UI
                    "active_recommendations": conversation_state.active_recommendations,
                    "created_at": conversation_state.created_at.isoformat(),
                    "updated_at": conversation_state.updated_at.isoformat()
                }
            }
        else:
            return {
                "success": False,
                "error": {
                    "code": "CONVERSATION_NOT_FOUND",
                    "message": f"Conversation {conversation_id} not found"
                }
            }
            
    except Exception as e:
        logger.exception(f"Failed to retrieve conversation: {e}")
        return {
            "success": False,
            "error": {
                "code": "CONVERSATION_ERROR",
                "message": "Failed to retrieve conversation history",
                "details": {"error": str(e)}
            }
        }

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """Handle request validation errors with structured 422 responses"""
    # Extract validation error details
    error_details = []
    for error in exc.errors():
        error_details.append({
            "field": " -> ".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    
    logger.warning(f"Request validation failed: {error_details}")
    
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": {
                    "validation_errors": error_details,
                    "error_count": len(error_details)
                }
            }
        }
    )

# === GRADES API ENDPOINTS (Ground Truth: Information Consolidation + Reliability) ===

@app.get("/grades/{course_code}", response_model=CourseGradesStats)
async def get_course_grades(
    course_code: str,
    grades_svc: GradesService = Depends(get_grades_service)
):
    """
    Get comprehensive grade statistics for a specific course. 
    
    Implements Ground Truth: Information Consolidation + Information Reliability
    - Real Cornell grade data with provenance tracking
    - TagCache versioning for performance and reliability
    - Full grade distribution, difficulty metrics, and pass rates
    
    Example: /grades/CS%204820
    """
    stats = await grades_svc.get_course_stats(course_code.upper())
    if not stats:
        raise HTTPException(
            status_code=404, 
            detail=f"No grade data found for course: {course_code}"
        )
    return stats

@app.post("/admin/cache/invalidate/{tag}")
async def invalidate_cache_tag(tag: str):
    """
    Administrative endpoint to invalidate cached data by tag. 
    
    Supports versioned tag invalidation strategy:
    - Increments tag version instead of deleting keys
    - Prevents cache storms and improves performance
    - Essential for data freshness during development
    
    Example: POST /admin/cache/invalidate/grades
    """
    if not redis_client:
        raise HTTPException(
            status_code=503,
            detail="Redis not available for cache invalidation"
        )
    
    try:
        tag_cache = TagCache(redis_client)
        await tag_cache.invalidate(tag)
        
        # Get current version for response
        current_version = await tag_cache._get_tag_version(tag)
        
        return {
            "success": True,
            "tag": tag,
            "new_version": current_version,
            "message": f"Cache tag '{tag}' invalidated, version bumped to {current_version}"
        }
    except Exception as e:
        logger.exception(f"Failed to invalidate cache tag {tag}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Cache invalidation failed: {str(e)}"
        )

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": "HTTP_ERROR",
                "message": exc.detail,
                "details": {"status_code": exc.status_code}
            }
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """General exception handler for unhandled errors"""
    logger.exception(f"Unhandled exception: {exc}")
    
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "details": {"error": str(exc)}
            }
        }
    )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )