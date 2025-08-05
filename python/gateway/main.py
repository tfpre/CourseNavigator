"""
FastAPI Gateway for Cornell Course Navigator
Combines Qdrant vector search with Neo4j graph queries
"""

import os
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from .models import (
    RAGRequest, RAGResponse, PrerequisitePathRequest, PrerequisitePathResponse,
    HealthResponse, ErrorDetail, CourseInfo, GraphContext, PrerequisiteEdge,
    CentralityRequest, CentralityResponse, CommunityRequest, CommunityResponse,
    CourseRecommendationRequest, CourseRecommendationResponse,
    ShortestPathRequest, ShortestPathResponse, AlternativePathsRequest, AlternativePathsResponse,
    SemesterPlanRequest, SemesterPlanResponse,
    GraphSubgraphRequest, GraphSubgraphResponse
)
from .services.vector_service import VectorService
from .services.graph_service import GraphService
from .services.rag_service import RAGService
from .services.graph_algorithms_service import GraphAlgorithmsService
from .services.performance_service import performance_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# Global service instances (will be initialized on startup)
vector_service: Optional[VectorService] = None
graph_service: Optional[GraphService] = None
rag_service: Optional[RAGService] = None
graph_algorithms_service: Optional[GraphAlgorithmsService] = None

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

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global vector_service, graph_service, rag_service, graph_algorithms_service
    
    logger.info("Initializing Cornell Course Navigator Gateway...")
    
    # Check for production safety - no accidental mocks in prod
    use_mock_services = os.getenv("USE_MOCK_SERVICES", "false").lower() == "true"
    environment = os.getenv("ENVIRONMENT", "development")
    
    if environment == "production" and use_mock_services:
        logger.error("CRITICAL: Mock services enabled in production environment!")
        raise RuntimeError("Production deployment cannot use mock services. Check USE_MOCK_SERVICES and ENVIRONMENT variables.")
    
    try:
        # Initialize services
        vector_service = VectorService(
            url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            collection_name=os.getenv("QDRANT_COLLECTION_NAME", "cornell_courses"),
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
        
        graph_service = GraphService(
            uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            username=os.getenv("NEO4J_USERNAME", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD", "password")
        )
        
        rag_service = RAGService(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            vector_service=vector_service,
            graph_service=graph_service
        )
        
        graph_algorithms_service = GraphAlgorithmsService(
            graph_service=graph_service
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
        
        logger.info("All services initialized successfully")
        
    except Exception as e:
        logger.exception(f"Failed to initialize services: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global vector_service, graph_service, rag_service
    
    logger.info("Shutting down Cornell Course Navigator Gateway...")
    
    if graph_service:
        await graph_service.close()
    
    if vector_service:
        await vector_service.close()

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
    service: GraphAlgorithmsService = Depends(get_graph_algorithms_service)
):
    """
    Get course centrality analysis including PageRank, bridge courses, and gateway courses.
    
    This endpoint calculates:
    - PageRank centrality (most important courses in curriculum)
    - Bridge courses (high betweenness centrality)
    - Gateway courses (high prerequisite requirements)
    """
    try:
        logger.info(f"Processing centrality request: top_n={request.top_n}")
        
        result = await service.get_course_centrality(
            top_n=request.top_n,
            damping_factor=request.damping_factor,
            min_betweenness=request.min_betweenness,
            min_in_degree=request.min_in_degree
        )
        
        return CentralityResponse(**result)
        
    except Exception as e:
        logger.exception(f"Centrality analysis failed: {e}")
        return CentralityResponse(
            success=False,
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
    service: GraphAlgorithmsService = Depends(get_graph_algorithms_service)
):
    """
    Get graph subgraph data for visualization.
    
    This endpoint provides:
    - Course nodes with centrality scores and community assignments
    - Prerequisite edges filtered by importance
    - Optimized for frontend visualization performance
    """
    try:
        logger.info(f"Processing graph subgraph request: max_nodes={request.max_nodes}, max_edges={request.max_edges}")
        
        result = await service.get_graph_subgraph(
            max_nodes=request.max_nodes,
            max_edges=request.max_edges,
            include_centrality=request.include_centrality,
            include_communities=request.include_communities,
            filter_by_subject=request.filter_by_subject
        )
        
        return GraphSubgraphResponse(**result)
        
    except Exception as e:
        logger.exception(f"Graph subgraph failed: {e}")
        return GraphSubgraphResponse(
            success=False,
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