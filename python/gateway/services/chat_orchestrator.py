# Chat Orchestrator Service - Multi-Context Fusion for Course Advisor AI
# Implements friend's recommendations: single monolithic prompt, deterministic token budgets, fail-fast timeouts

import asyncio
import logging
import os
import time
import uuid
from typing import Dict, List, Optional, Any, AsyncGenerator
from datetime import datetime, timedelta

from ..models import (
    ChatRequest, ChatResponse, ChatContext, ChatStreamChunk, 
    StudentProfile, ConversationState, ConversationMessage,
    ContextSource, TokenBudget, ErrorDetail, PrerequisitePathRequest,
    ChatResponseJSON, Recommendation, CourseCode, ChatAdvisorResponse
)
from .vector_service import VectorService
from .graph_service import GraphService
from .rag_service import RAGService
from .professor_intelligence_service import ProfessorIntelligenceService
from .course_difficulty_service import CourseDifficultyService
from .enrollment_prediction_service import EnrollmentPredictionService
from .grades_service import GradesService
from .student_profile_service import StudentProfileService
from .schedule_fit_service import ScheduleFitService, ProfilePrefs
from .major_requirements_service import MajorRequirementsService
from .conflict_detection_service import ConflictDetectionService
from .llm_router import LLMRouter
from .token_budget import TokenBudgetManager
from .tag_cache import ContextCache
from ..utils.schema_enforcer import enforce_with_retry, validate_reask_result, JSONEnforceError
from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

try:
    redis_hit = Counter("conversation_state_redis_hit_total", "Redis hits for conversation state")
    redis_miss = Counter("conversation_state_redis_miss_total", "Redis misses for conversation state")
    
    # Enhanced JSON Schema Enforcement Metrics
    json_pass_total = Counter("json_pass_total", "Valid JSON on first try")
    json_retry_pass_total = Counter("json_retry_pass_total", "Valid JSON after one retry")
    json_fail_total = Counter("json_fail_total", "Still invalid after retry")
    json_enforce_ms = Histogram("json_enforce_ms", "End-to-end JSON enforcement time (ms)",
                               buckets=(50, 100, 200, 400, 800, 1600, 3200))
    
    # Legacy metrics for compatibility
    json_validations_total = Counter("json_validations_total", "JSON validation attempts", ["result"])
    json_reask_total = Counter("json_reask_total", "JSON re-ask attempts")
    json_fallback_total = Counter("json_fallback_total", "JSON fallback invocations")
    
    # Performance and reliability metrics
    chat_request_duration_seconds = Histogram("chat_request_duration_seconds", "Chat request latency", 
                                            buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0))
    sse_stream_errors_total = Counter("sse_stream_errors_total", "SSE streaming failures", ["error_type"])
    sse_chunk_gap_exceeded_total = Counter("sse_chunk_gap_exceeded_total", "SSE chunk gaps > 1.5s")
    context_timeout_total = Counter("context_timeout_total", "Context service timeouts", ["service"])
    context_requests_total = Counter("context_requests_total", "Context service requests", ["service", "status"])
    cache_hits_total = Counter("cache_hits_total", "Cache hits", ["service"])
    cache_misses_total = Counter("cache_misses_total", "Cache misses", ["service"])
except ValueError:
    # metrics already registered
    pass

class ChatOrchestratorService:
    """
    Chat Orchestrator - Core conversational AI service with multi-context fusion.
    
    Architecture following friend's guidance:
    - Single monolithic prompt (~1.1k tokens) 
    - Deterministic token budget allocation
    - Parallel context fetching with fail-fast timeouts (150ms per service)
    - Local LLM primary, OpenAI fallback strategy
    - Redis conversation state persistence
    
    Performance target: <500ms P95 perceived latency with SSE streaming
    """
    
    def __init__(
        self,
        vector_service: VectorService,
        graph_service: GraphService,
        rag_service: RAGService,
        redis_client=None,  # Optional Redis for conversation state
        local_llm_client=None,  # Optional local LLM (Phi-3-mini)
        openai_api_key: str = None
    ):
        self.vector_service = vector_service
        self.graph_service = graph_service
        self.rag_service = rag_service
        self.redis_client = redis_client
        self.local_llm_client = local_llm_client
        self.openai_api_key = openai_api_key
        
        # Initialize context services (friend's multi-modal architecture)
        self.professor_service = ProfessorIntelligenceService(redis_client=redis_client)
        self.difficulty_service = CourseDifficultyService(redis_client=redis_client)
        self.enrollment_service = EnrollmentPredictionService(redis_client=redis_client)
        self.grades_service = GradesService(redis_client=redis_client)
        self.schedule_fit_service = ScheduleFitService(redis_client=redis_client)
        self.profile_service = StudentProfileService(redis_client=redis_client)
        self.conflict_detection_service = ConflictDetectionService()
        
        # Initialize major requirements service (feature flagged)
        self.major_req_enabled = os.getenv("ENABLE_DEGREE_PROGRESS", "true").lower() == "true"
        if self.major_req_enabled:
            self.major_req_service = MajorRequirementsService(
                neo4j_client=self.graph_service.driver, 
                redis_client=redis_client
            )
        
        # Initialize LLM router with first-token deadline pattern
        self.llm_router = LLMRouter(
            vllm_base=os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1"),
            openai_key=openai_api_key,
            model_local=os.getenv("LOCAL_MODEL", "meta-llama/Llama-3.1-8B-Instruct"),
            model_fallback=os.getenv("FALLBACK_MODEL", "gpt-4o-mini"),
            first_token_deadline_ms=200
        )
        
        # Initialize token budget manager with hard caps
        self.token_budget_manager = TokenBudgetManager(max_total_tokens=1200)
        
        # Initialize versioned tag cache for context optimization
        self.context_cache = ContextCache(redis_client) if redis_client else None
        
        # Performance configuration (friend's guidance)
        self.CONTEXT_TIMEOUT_MS = 150  # Fail-fast per micro-service
        self.LLM_FALLBACK_TIMEOUT_MS = 200  # Switch to OpenAI fallback
        self.MAX_CONVERSATION_HISTORY = 20  # Bounded conversation memory
        # Redis TTL (seconds) – env override allowed
        self.REDIS_TTL_SECONDS = int(os.getenv("REDIS_TTL_DAYS", "7")) * 24 * 3600
        # Timeouts so Redis can't tank P95
        self.REDIS_OP_TIMEOUT_MS = int(os.getenv("REDIS_OP_TIMEOUT_MS", "50"))

        # Build async Redis client if not injected
        if self.redis_client is None:
            try:
                import redis.asyncio as aioredis
                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                # decode_responses=True → JSON strings in/out, no bytes juggling
                self.redis_client = aioredis.from_url(redis_url, decode_responses=True)
                # Light liveness check, timeboxed
                async def _ping():
                    try:
                        return await asyncio.wait_for(self.redis_client.ping(), timeout=self.REDIS_OP_TIMEOUT_MS/1000)
                    except Exception:
                        return False
                # fire-and-forget ping (don’t block init)
                try:
                    asyncio.get_running_loop().create_task(_ping())
                except RuntimeError:
                    pass
            except Exception as e:
                logger.warning(f"Redis initialization skipped (continuing without persistence): {e}")
        
        # Template for prompt construction with structured output requirement (Friend's JSON enforcement)
        self.PROMPT_TEMPLATE = """System: You are an intelligent Cornell University academic advisor. You have access to course prerequisites, professor ratings, grade distributions, and enrollment data. Provide helpful, actionable advice for course planning and academic decisions.

User Profile: {profile_json}

=== CONTEXT ===
{context_sections}

=== CONVERSATION HISTORY ===
{conversation_history}

=== USER QUESTION ===
{user_message}

{provenance_section}

=== INSTRUCTIONS ===
Provide a helpful conversational response that ends with structured recommendations in this EXACT JSON format:

```json
{{
  "recommendations": [
    {{
      "course_code": "CS 3110",
      "title": "Data Structures and Functional Programming",
      "rationale": "Builds directly on CS 2110 and is required for ML track",
      "priority": 1,
      "next_action": "add_to_plan",
      "difficulty_warning": "High workload but manageable after 2110",
      "source": {{}}
    }}
  ],
  "constraints": ["Prerequisites: CS 2110 required", "Time conflict warning"],
  "next_actions": [
    {{"type": "check_prerequisites", "course_code": "CS 3110"}},
    {{"type": "monitor_enrollment", "course_code": "CS 3110"}}
  ],
  "notes": "Consider semester balance with other challenging courses",
  "provenance": ["graphctx:v42", "grades:v12", "rmp:v7"]
}}
```

STRICT REQUIREMENTS (Ground Truth: Actionable Prioritization):
- Write conversational advice first, then add the JSON block with triple backticks
- Include 3-5 course recommendations ranked by priority (1=highest)
- course_code MUST be format "SUBJ ####" (e.g., "CS 3110", "MATH 1920")
- title MUST be the actual course title
- next_action MUST be one of: "add_to_plan", "check_prereqs", "consider_alternative", "waitlist_monitor"
- constraints array should list specific limitations or conflicts
- next_actions array should contain actionable follow-up steps
- MUST include provenance array with source tags from SOURCES section
- Use **course_code** format in conversational text for frontend parsing
- If uncertain about information, acknowledge limitations

Answer:"""

    async def process_chat_request(
        self,
        request: ChatRequest
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        """
        Process chat request with streaming response.
        
        Main orchestration flow:
        1. Load/create conversation state
        2. Gather context in parallel (with timeouts)
        3. Build prompt with token budget management
        4. Generate streaming LLM response (local → fallback)
        5. Update conversation state
        """
        request_id = str(uuid.uuid4())
        start_time = time.time()
        
        logger.info(f"Processing chat request {request_id}: {request.message[:50]}...")
        
        # Start latency measurement for SLO tracking
        with chat_request_duration_seconds.time():
            try:
                # Step 1: Load conversation state
                conversation_state = await self._load_conversation_state(
                    request.conversation_id,
                    request.student_profile
                )
                
                yield ChatStreamChunk(
                    chunk_id=0,
                    content="",
                    chunk_type="context_info",
                    metadata={"status": "loading_context", "request_id": request_id}
                )
            
                # Step 2: Gather context in parallel with fail-fast timeouts
                context = await self._gather_context_parallel(
                    request, 
                    conversation_state.student_profile,
                    request_id
                )
                
                yield ChatStreamChunk(
                    chunk_id=1, 
                    content="",
                    chunk_type="context_info",
                    metadata={"status": "building_prompt", "context_sources": len(context.context_sources)}
                )
                
                # Step 3: Build prompt with deterministic token budget
                prompt = await self._build_prompt(
                    request.message,
                    context,
                    conversation_state
                )
                
                if not prompt:
                    yield ChatStreamChunk(
                        chunk_id=2,
                        content="I'm having trouble processing your request right now. Please try again.",
                        chunk_type="error", 
                        metadata={"error": "prompt_generation_failed"}
                    )
                    return
                
                yield ChatStreamChunk(
                    chunk_id=2,
                    content="",
                    chunk_type="context_info", 
                    metadata={"status": "generating_response", "prompt_tokens": len(prompt.split())}
                )
                
                # Step 4: Generate streaming LLM response
                chunk_counter = 3
                response_text = ""
                provider_used = None
                first_token_time = None
                llm_generation_start = time.perf_counter()
                last_chunk_time = llm_generation_start  # For gap detection
                
                try:
                    async for chunk in self._generate_llm_response(prompt):
                        current_time = time.perf_counter()
                        
                        # SSE Watchdog: Monitor inter-chunk gaps
                        if chunk_counter > 3:  # Skip gap check for first chunk
                            gap_ms = (current_time - last_chunk_time) * 1000
                            if gap_ms > 1500:  # Gap threshold: 1.5s
                                logger.warning(f"SSE chunk gap detected: {gap_ms:.1f}ms between chunks {chunk_counter-1} and {chunk_counter}")
                                sse_chunk_gap_exceeded_total.inc()
                        
                        last_chunk_time = current_time
                        
                        if chunk.metadata and "llm_provider" in chunk.metadata:
                            provider_used = chunk.metadata["llm_provider"]
                        
                        # Track first token timing for SLO observability  
                        if chunk.chunk_type == "token" and first_token_time is None:
                            first_token_time = (current_time - llm_generation_start) * 1000
                        
                        chunk.chunk_id = chunk_counter
                        chunk_counter += 1
                        if chunk.chunk_type == "token":
                            response_text += chunk.content
                        yield chunk
                        
                except Exception as stream_error:
                    # Track streaming failures for monitoring
                    error_type = type(stream_error).__name__
                    sse_stream_errors_total.labels(error_type=error_type).inc()
                    logger.error(f"SSE streaming error: {stream_error}")
                    raise
                
                # Step 5: Update conversation state and yield final response
                processing_time_ms = int((time.time() - start_time) * 1000)
                
                # Update conversation with new message and response
                conversation_state.messages.append(
                    ConversationMessage(role="user", content=request.message)
                )
                conversation_state.messages.append(
                    ConversationMessage(role="assistant", content=response_text)
                )
                conversation_state.updated_at = datetime.utcnow()
                
                # Enforce schema: parse/repair/re-ask to ensure a valid ChatAdvisorResponse
                validated_response, recommended_courses = await self._enforce_json_schema(response_text, prompt)
                
                # Store active recommendations for /explain command
                conversation_state.active_recommendations = recommended_courses
                
                # Save conversation state
                await self._save_conversation_state(conversation_state)
                
                # Yield completion chunk
                yield ChatStreamChunk(
                    chunk_id=chunk_counter,
                    content="",
                    chunk_type="done",
                    metadata={
                        "conversation_id": conversation_state.conversation_id,
                        "processing_time_ms": processing_time_ms,
                        "llm_provider": provider_used or "unknown",
                        "fallback_triggered": (provider_used == "openai-fallback"),
                        "recommended_courses": recommended_courses,
                        "context_sources_used": [source.source_type for source in context.context_sources],
                        "context_fetch_time_ms": context.processing_metadata.get("context_fetch_time_ms"),
                        "provenance_info": {
                            "sources": [],  # TODO: fix provenance_tags scope issue
                            "data_freshness": self._get_data_freshness_summary(context.context_sources),
                            "professor_selections": self._get_professor_selection_summary(context.context_sources),
                            "updated_at": datetime.utcnow().isoformat()
                        },
                        # SSE observability metrics for performance SLO monitoring
                        "first_token_ms": first_token_time,
                        "provider_first": provider_used or "unknown",
                        "slo_compliance": {
                            "first_token_slo_met": first_token_time is not None and first_token_time < 500,
                            "total_response_slo_met": processing_time_ms < 500
                        }
                    }
                )
                
                logger.info(f"Chat request {request_id} completed in {processing_time_ms}ms")
                
            except Exception as e:
                logger.exception(f"Chat request {request_id} failed: {e}")
                yield ChatStreamChunk(
                    chunk_id=999,
                    content=f"I encountered an error processing your request: {str(e)}",
                    chunk_type="error",
                    metadata={"error": str(e), "request_id": request_id}
                )

    async def _gather_context_parallel(
        self,
        request: ChatRequest,
        student_profile: StudentProfile,
        request_id: str
    ) -> ChatContext:
        """
        Gather context from multiple services in parallel with fail-fast timeouts.
        
        Expert pattern: measure actual wall-clock duration, not timeout values.
        """
        context = ChatContext(
            request_id=request_id,
            student_profile=student_profile
        )
        
        context.processing_metadata["context_fetch_start"] = t0 = time.perf_counter()
        
        # Prepare async tasks for parallel execution
        tasks = []
        prefs = request.context_preferences or {}
        
        if prefs.get("include_similar_courses", True):
            tasks.append(("vector_search", self._fetch_vector_context(request.message)))
        
        if prefs.get("include_prerequisites", True):
            tasks.append(("graph_analysis", self._fetch_graph_context(request.message, student_profile)))
            
        if prefs.get("include_professor_ratings", True):
            tasks.append(("professor_intel", self._fetch_professor_context(request.message, student_profile)))
        
        if prefs.get("include_difficulty_info", True):
            tasks.append(("difficulty_data", self._fetch_difficulty_context(request.message, student_profile)))

        if prefs.get("include_grades_data", True):
            tasks.append(("grades_data", self._fetch_grades_context(request.message, student_profile)))

        if prefs.get("include_enrollment_data", True):
            tasks.append(("enrollment_data", self._fetch_enrollment_context(request.message, student_profile)))
        
        # Schedule fit context (behind feature flag)
        if os.getenv("ENABLE_SCHEDULE_FIT", "false").lower() == "true":
            tasks.append(("schedule_fit", self._fetch_schedule_fit_context(request.message, student_profile)))
        
        # Degree progress context (behind feature flag)
        if self.major_req_enabled and prefs.get("include_degree_progress", True) and getattr(student_profile, "major", None):
            tasks.append(("degree_progress", self._fetch_degree_progress_context(student_profile)))
        
        # Conflict detection for registration intelligence
        if prefs.get("include_conflict_detection", True):
            tasks.append(("conflict_detection", self._fetch_conflict_detection_context(request.message, student_profile)))
        
        timeout_s = self.CONTEXT_TIMEOUT_MS / 1000.0
        
        async def timed(name, coro):
            """Expert pattern: measure actual duration, not timeout values"""
            start = time.perf_counter()
            try:
                result = await asyncio.wait_for(coro, timeout=timeout_s)
                duration_ms = int((time.perf_counter() - start) * 1000)
                context_requests_total.labels(service=name, status="success").inc()
                return name, result, duration_ms, None
            except asyncio.TimeoutError as e:
                duration_ms = int((time.perf_counter() - start) * 1000)
                logger.warning(f"Context {name} timeout in {duration_ms}ms: {e}")
                context_requests_total.labels(service=name, status="timeout").inc()
                context_timeout_total.labels(service=name).inc()
                return name, None, duration_ms, e
            except Exception as e:
                duration_ms = int((time.perf_counter() - start) * 1000)
                logger.warning(f"Context {name} failed in {duration_ms}ms: {e}")
                context_requests_total.labels(service=name, status="error").inc()
                return name, None, duration_ms, e
        
        # Execute all tasks in parallel with real timing
        if tasks:
            results = await asyncio.gather(*[timed(name, coro) for name, coro in tasks], return_exceptions=False)
            
            # Process results with accurate timing and cache hit tracking
            for name, data, duration_ms, error in results:
                if data:
                    # Extract cache hit information if available
                    cache_hit = False
                    if isinstance(data, dict) and "cache_hit" in data:
                        cache_hit = data["cache_hit"]
                    elif hasattr(data, "cache_hit"):
                        cache_hit = data.cache_hit
                    
                    # Estimate token count (rough approximation)
                    token_count = len(str(data)) // 4  # ~4 chars per token
                    
                    # Generate versioned source tag for provenance tracking
                    version = data.get("version", 1) if isinstance(data, dict) else 1
                    source_tag = f"{name}:v{version}"
                    
                    context_source = ContextSource(
                        source_type=name,
                        data=data,
                        confidence=0.8,
                        token_count=token_count,
                        processing_time_ms=duration_ms,  # CORRECT: actual measured duration
                        cache_hit=cache_hit,  # CORRECT: track actual cache hits
                        metadata={
                            "source_tag": source_tag,
                            "version": version,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    )
                    context.context_sources.append(context_source)
                else:
                    # Log failed context fetch for debugging
                    logger.debug(f"Context {name} returned no data after {duration_ms}ms")
        
        t1 = time.perf_counter()
        context.processing_metadata["context_fetch_end"] = time.time()
        context.processing_metadata["context_fetch_time_ms"] = int((t1 - t0) * 1000)
        
        logger.info(f"Gathered {len(context.context_sources)} context sources for request {request_id} in {int((t1 - t0) * 1000)}ms")
        return context
    
    async def _fetch_vector_context(self, message: str) -> Optional[Dict[str, Any]]:
        """Fetch semantically similar courses via vector search"""
        try:
            # CRITICAL FIX: Get embedding first, then search with vector
            # VectorService.search_courses expects embedding list, not text
            embedding = await self.vector_service.get_embedding(message)
            similar_courses = await self.vector_service.search_courses(
                query_embedding=embedding,
                top_k=5,
                score_threshold=0.7  # Fixed parameter name
            )
            
            if similar_courses:
                return {
                    "similar_courses": [
                        {
                            "title": course.title,
                            "subject": course.subject,
                            "catalog_nbr": course.catalog_nbr,
                            "description": course.description,
                            "similarity_score": course.similarity_score
                        } for course in similar_courses[:5]
                    ],
                    "search_query": message
                }
        except Exception as e:
            logger.exception(f"Vector context fetch failed: {e}")
        return None
    
    async def _fetch_graph_context(self, message: str, student_profile: StudentProfile) -> Optional[Dict[str, Any]]:
        """Fetch prerequisite and graph relationship context with versioned tag cache"""
        try:
            import re
            course_matches = re.findall(r'([A-Z]{2,4})\s*(\d{4})', message.upper())
            if not course_matches:
                return None
                
            course_code = f"{course_matches[0][0]} {course_matches[0][1]}"
            
            # Use context cache for graph data (24h TTL)
            if self.context_cache:
                return await self.context_cache.get_graph_context(
                    course_code=course_code,
                    student_profile={
                        "student_id": student_profile.student_id if student_profile else "unknown",
                        "completed_courses": student_profile.completed_courses if student_profile else []
                    },
                    loader=lambda: self._load_graph_data(course_code, student_profile)
                )
            else:
                # Fallback without cache
                return await self._load_graph_data(course_code, student_profile)
                
        except Exception as e:
            logger.exception(f"Graph context fetch failed: {e}")
        return None
    
    async def _load_graph_data(self, course_code: str, student_profile: StudentProfile) -> Optional[Dict[str, Any]]:
        """Load graph data from service (cache loader)"""
        # CRITICAL FIX: Use correct API - PrerequisitePathRequest object required
        try:
            request = PrerequisitePathRequest(
                course_id=course_code,
                max_depth=3,  # Reasonable depth for chat context
                include_recommendations=True
            )
            response = await self.graph_service.get_prerequisite_path(request)
            
            if response and response.paths:
                return {
                    "prerequisite_path": {
                        "course_id": response.course_id,
                        "paths": [
                            {
                                "path": path.path,
                                "total_depth": path.total_depth,
                                "missing_prerequisites": path.missing_prerequisites
                            } for path in response.paths[:3]  # Limit for token budget
                        ]
                    },
                    "course_code": course_code,
                    "student_completed": student_profile.completed_courses if student_profile else []
                }
        except Exception as e:
            logger.warning(f"Graph service call failed for {course_code}: {e}")
        return None

    async def _fetch_professor_context(self, message: str, student_profile: StudentProfile) -> Optional[Dict[str, Any]]:
        """
        Fetch professor ratings and intelligence context with versioned tag cache.
        
        Expert pattern: cache professor data with 7d TTL since ratings change infrequently.
        """
        try:
            import re
            course_matches = re.findall(r'([A-Z]{2,4})\s*(\d{4})', message.upper())
            
            # Collect course codes to analyze
            course_codes = []
            if course_matches:
                # Get professor intel for mentioned courses (limit to 3 for token budget)
                for subject, number in course_matches[:3]:
                    course_codes.append(f"{subject} {number}")
            elif student_profile and student_profile.current_courses:
                # Fallback to current courses (limit to 2 for performance)
                course_codes = student_profile.current_courses[:2]
            
            if not course_codes:
                return None
            
            professor_data = {}
            for course_code in course_codes:
                # Use context cache for professor data (7d TTL)
                if self.context_cache:
                    prof_intel = await self.context_cache.get_professor_context(
                        course_code=course_code,
                        loader=lambda cc=course_code: self.professor_service.get_professor_intel(cc)
                    )
                else:
                    # Fallback without cache
                    prof_intel = await self.professor_service.get_professor_intel(course_code)
                
                if prof_intel:
                    professor_data[course_code] = prof_intel
            
            if professor_data:
                return {
                    "professor_intelligence": professor_data,
                    "query": message,
                    "courses_analyzed": list(professor_data.keys())
                }
                
        except Exception as e:
            logger.exception(f"Professor context fetch failed: {e}")
        return None

    async def _fetch_difficulty_context(self, message: str, student_profile: StudentProfile) -> Optional[Dict[str, Any]]:
        """
        Fetch course difficulty and grade distribution context.
        
        Following friend's guidance: mean_gpa, stdev, relative_rank from pre-computed data
        """
        try:
            # Extract course codes from message (same pattern as other contexts)
            import re
            course_pattern = r'([A-Z]{2,4})\s*(\d{4})'
            course_matches = re.findall(course_pattern, message.upper())
            
            difficulty_data = {}
            
            if course_matches:
                # Get difficulty data for mentioned courses
                for subject, number in course_matches[:3]:  # Limit to 3 courses for token budget
                    course_code = f"{subject} {number}"
                    diff_data = await self.difficulty_service.get_course_difficulty(course_code)
                    if diff_data:
                        difficulty_data[course_code] = diff_data
            else:
                # If no specific courses mentioned, try to infer from student profile
                if student_profile and student_profile.current_courses:
                    for course_code in student_profile.current_courses[:2]:  # Limit to 2 for performance
                        diff_data = await self.difficulty_service.get_course_difficulty(course_code)
                        if diff_data:
                            difficulty_data[course_code] = diff_data
            
            if difficulty_data:
                return {
                    "difficulty_analysis": difficulty_data,
                    "query": message,
                    "courses_analyzed": list(difficulty_data.keys())
                }
                
        except Exception as e:
            logger.exception(f"Difficulty context fetch failed: {e}")
        return None

    async def _fetch_grades_context(self, message: str, student_profile: StudentProfile) -> Optional[Dict[str, Any]]:
        """
        Fetch real Cornell grade distribution context using GradesService.
        
        Following friend's guidance: Real data integration for Information Consolidation ground truth.
        """
        try:
            # Extract course codes from message
            import re
            course_pattern = r'([A-Z]{2,4})\s*(\d{4})'
            course_matches = re.findall(course_pattern, message.upper())
            
            grades_data = {}
            
            if course_matches:
                # Get grades data for mentioned courses
                for subject, number in course_matches[:3]:  # Limit to 3 courses for token budget
                    course_code = f"{subject} {number}"
                    course_stats = await self.grades_service.get_course_stats(course_code)
                    if course_stats:
                        grades_data[course_code] = {
                            "mean_gpa": course_stats.mean_gpa,
                            "grade_distribution": course_stats.grade_histogram,
                            "pass_rate": course_stats.pass_rate,
                            "difficulty_percentile": course_stats.difficulty_percentile,
                            "provenance": course_stats.provenance
                        }
            else:
                # If no specific courses mentioned, check student's current/planned courses
                if student_profile:
                    courses_to_check = student_profile.current_courses[:2]
                    
                    for course_code in courses_to_check:
                        course_stats = await self.grades_service.get_course_stats(course_code)
                        if course_stats:
                            grades_data[course_code] = {
                                "mean_gpa": course_stats.mean_gpa,
                                "grade_distribution": course_stats.grade_histogram,
                                "pass_rate": course_stats.pass_rate,
                                "difficulty_percentile": course_stats.difficulty_percentile,
                                "provenance": course_stats.provenance
                            }
            
            if grades_data:
                return {
                    "grade_distributions": grades_data,
                    "query": message,
                    "courses_analyzed": list(grades_data.keys()),
                    "data_source": "cornell_grade_distributions"
                }
                
        except Exception as e:
            logger.exception(f"Grades context fetch failed: {e}")
        return None

    async def _fetch_enrollment_context(self, message: str, student_profile: StudentProfile) -> Optional[Dict[str, Any]]:
        """
        Fetch enrollment prediction and registration advice context.
        
        Following friend's guidance: waitlist_prob, historical_fill_hours, registration advice
        """
        try:
            # Extract course codes from message
            import re
            course_pattern = r'([A-Z]{2,4})\s*(\d{4})'
            course_matches = re.findall(course_pattern, message.upper())
            
            enrollment_data = {}
            
            # Estimate time until semester (default to 30 days for mock)
            time_until_semester = 30
            
            if course_matches:
                # Get enrollment predictions for mentioned courses
                for subject, number in course_matches[:3]:  # Limit to 3 courses for token budget
                    course_code = f"{subject} {number}"
                    enroll_pred = await self.enrollment_service.get_enrollment_prediction(
                        course_code, 
                        time_until_semester
                    )
                    if enroll_pred:
                        enrollment_data[course_code] = enroll_pred
            else:
                # If no specific courses mentioned, check student's current/planned courses
                if student_profile:
                    # Check current courses first
                    courses_to_check = student_profile.current_courses[:2]
                    
                    # If no current courses, use some common courses based on major
                    if not courses_to_check and student_profile.major:
                        if "computer science" in student_profile.major.lower():
                            courses_to_check = ["CS 2110", "CS 3110"]
                        elif "math" in student_profile.major.lower():
                            courses_to_check = ["MATH 1920", "MATH 2940"]
                    
                    for course_code in courses_to_check:
                        enroll_pred = await self.enrollment_service.get_enrollment_prediction(
                            course_code,
                            time_until_semester
                        )
                        if enroll_pred:
                            enrollment_data[course_code] = enroll_pred
            
            if enrollment_data:
                return {
                    "enrollment_predictions": enrollment_data,
                    "query": message,
                    "courses_analyzed": list(enrollment_data.keys()),
                    "time_until_semester": time_until_semester
                }
                
        except Exception as e:
            logger.exception(f"Enrollment context fetch failed: {e}")
        return None

    async def _fetch_schedule_fit_context(self, message: str, student_profile: StudentProfile) -> Optional[Dict[str, Any]]:
        """
        Fetch schedule fit context with conflict detection and preference scoring.
        
        Extract course codes from message or use student's planned courses.
        """
        try:
            # Extract course codes from message
            candidates = self._extract_course_codes(message)
            if not candidates and student_profile and student_profile.planned_courses:
                candidates = student_profile.planned_courses[:6]  # Limit for performance
            
            if not candidates:
                return None

            # Build preferences from student profile
            prefs = ProfilePrefs(
                dislikes_morning=bool(getattr(student_profile, "dislikes_morning", False)),
                no_fri=bool(getattr(student_profile, "no_friday", False)),
            )
            
            # Get ranked schedules
            ranked = await self.schedule_fit_service.rank_schedules(candidates, prefs, limit=3)
            if not ranked:
                return None

            # Generate summary for prompt (≤120 tokens)
            best = ranked[0]
            summary = f"Best schedule score {best.fit_score}/100 with {len(best.section_bundle_ids)} sections"
            if best.conflict_reason:
                summary += f" ({best.conflict_reason})"

            return {
                "schedule_fit": {
                    "best": best.model_dump(),
                    "alternatives": [r.model_dump() for r in ranked[1:]] if len(ranked) > 1 else [],
                    "summary": summary,
                    "course_codes": candidates,
                    "preferences_applied": prefs.model_dump()
                }
            }
        except Exception as e:
            logger.exception(f"Schedule fit context fetch failed: {e}")
        return None

    def _extract_course_codes(self, message: str) -> List[str]:
        """Extract course codes from message text."""
        import re
        course_pattern = r'([A-Z]{2,4})\s*(\d{4})'
        course_matches = re.findall(course_pattern, message.upper())
        return [f"{subject} {number}" for subject, number in course_matches]
    
    def _get_data_freshness_summary(self, context_sources) -> Dict[str, str]:
        """Generate a summary of data freshness for UI display"""
        freshness_summary = {}
        
        for source in context_sources:
            source_type = source.source_type
            metadata = source.data.get("metadata", {}) if source.data else {}
            
            # Extract freshness information from source metadata
            if "version" in metadata:
                version_info = f"v{metadata['version']}"
            else:
                version_info = "v1"
                
            if "timestamp" in metadata:
                try:
                    timestamp = datetime.fromisoformat(metadata["timestamp"].replace("Z", "+00:00"))
                    hours_ago = int((datetime.utcnow().replace(tzinfo=timezone.utc) - timestamp).total_seconds() / 3600)
                    
                    if hours_ago < 1:
                        time_info = "just updated"
                    elif hours_ago < 24:
                        time_info = f"{hours_ago}h ago"
                    else:
                        days_ago = hours_ago // 24
                        time_info = f"{days_ago}d ago"
                except Exception:
                    time_info = "recently"
            else:
                time_info = "recently"
                
            # Format as "source (version) · time_info"
            freshness_summary[source_type] = f"{source_type.title()} ({version_info}) · {time_info}"
            
        return freshness_summary
    
    def _get_professor_selection_summary(self, context_sources) -> Dict[str, str]:
        """Extract professor selection reasoning for UI explainability"""
        selection_summary = {}
        
        for source in context_sources:
            if source.source_type == "professor_intel" and source.data:
                prof_data = source.data.get("professor_intelligence", {})
                for course_code, intel in prof_data.items():
                    selection_reason = intel.get("selection_reason")
                    if selection_reason:
                        # Convert to human-readable format
                        if selection_reason == "most_reviews_then_rating":
                            selection_summary[course_code] = "Most reviews, then rating"
                        elif selection_reason == "enhanced_mock_deterministic":
                            selection_summary[course_code] = "Enhanced mock data"
                        else:
                            selection_summary[course_code] = selection_reason.replace("_", " ").title()
        
        return selection_summary
    
    async def _fetch_degree_progress_context(self, student_profile: StudentProfile) -> Optional[Dict[str, Any]]:
        """
        Fetch degree progress context showing unmet requirements for graduation planning.
        """
        try:
            dp = await self.major_req_service.unmet_reqs(student_profile)
            if not dp or not dp.unmet:
                return None
                
            # Summarize top 5 unmet deterministically; keep token budget tight (≤150 tokens)
            lines = []
            for u in dp.unmet[:5]:
                if u.credit_gap:
                    lines.append(f"- {u.summary}: need {u.credit_gap} credits (e.g., {', '.join(u.courses_to_satisfy[:3])})")
                elif u.count_gap:
                    lines.append(f"- {u.summary}: take {u.count_gap} more (e.g., {', '.join(u.courses_to_satisfy[:3])})")
                else:
                    lines.append(f"- {u.summary}: remaining")
                    
            section = "### Degree Progress\n" + "\n".join(lines)
            
            # Hard cap ~150 tokens ≈ 600 chars
            if len(section) > 600:
                section = section[:580].rsplit("\n", 1)[0] + "\n- …"
                
            return {
                "section": section,
                "provenance": {"source": "neo4j", "as_of": dp.as_of},
                "major_id": dp.major_id,
                "unmet_count": len(dp.unmet)
            }
        except Exception as e:
            # Don't block chat if degree calc fails
            logger.warning(f"Degree progress fetch failed: {e}")
            return None

    async def _fetch_conflict_detection_context(self, message: str, student_profile: StudentProfile) -> Optional[Dict[str, Any]]:
        """
        Fetch conflict detection context for registration intelligence.
        
        Analyzes requested courses for time conflicts and provides backup plans.
        """
        try:
            # Extract course codes from message using regex
            import re
            course_pattern = r'\b[A-Z]{2,4}\s+\d{4}\b'
            mentioned_courses = re.findall(course_pattern, message.upper())
            
            # Also check current courses from profile
            all_courses = set(mentioned_courses)
            if hasattr(student_profile, 'current_courses'):
                all_courses.update(student_profile.current_courses)
            
            if len(all_courses) < 2:
                return None  # Need at least 2 courses to detect conflicts
            
            # Detect conflicts
            conflicts = self.conflict_detection_service.detect_conflicts(list(all_courses))
            backup_plans = self.conflict_detection_service.suggest_backup_plans(conflicts)
            
            if not conflicts:
                return {
                    "section": "### Schedule Analysis\n✅ No time conflicts detected in your course selection.",
                    "provenance": {"source": "conflict_detection", "as_of": "demo_data"},
                    "conflict_count": 0,
                    "courses_analyzed": list(all_courses)
                }
            
            # Format conflict summary with backup suggestions
            conflict_summary = self.conflict_detection_service.format_conflict_summary(conflicts)
            backup_summary = self.conflict_detection_service.format_backup_suggestions(backup_plans)
            
            section = f"### Schedule Analysis\n{conflict_summary}"
            if backup_summary:
                section += f"\n{backup_summary}"
            
            # Cap at ~200 tokens ≈ 800 chars for registration intelligence context
            if len(section) > 800:
                section = section[:780].rsplit("\n", 1)[0] + "\n..."
            
            return {
                "section": section,
                "provenance": {"source": "conflict_detection", "as_of": "demo_data"},
                "conflict_count": len(conflicts),
                "courses_analyzed": list(all_courses),
                "conflicts": [
                    {
                        "course_a": c.course_a,
                        "course_b": c.course_b,
                        "type": c.conflict_type.value,
                        "severity": c.severity
                    } for c in conflicts
                ],
                "backup_plans": {
                    course: [
                        {
                            "backup_course": plan.backup_course,
                            "rationale": plan.rationale,
                            "difficulty_delta": plan.difficulty_delta
                        } for plan in plans
                    ] for course, plans in backup_plans.items()
                }
            }
        except Exception as e:
            logger.warning(f"Conflict detection fetch failed: {e}")
            return None

    async def _build_prompt(
        self,
        user_message: str,
        context: ChatContext,
        conversation_state: ConversationState
    ) -> Optional[str]:
        """
        Build LLM prompt with token budget manager for hard caps and adaptive allocation.
        
        Expert pattern: 1.2k hard ceiling with deterministic section budgets.
        """
        try:
            # Prepare sections for token budget manager
            sections = {}
            
            # Student profile section (token-budgeted v2)
            if context.student_profile:
                # Use prompt budgeter v2 for efficient token usage
                if self.profile_service:
                    sections["student_profile"] = self.profile_service.to_prompt_budget(
                        context.student_profile, 
                        max_tokens=200  # Stay within budget per redisTicket.md
                    )
                else:
                    # Fallback for when Redis/profile service unavailable
                    sections["student_profile"] = f"Student: {context.student_profile.major or 'Undeclared'}"
                    if context.student_profile.year:
                        sections["student_profile"] += f" {context.student_profile.year}"
                    if context.student_profile.completed_courses:
                        completed_count = len(context.student_profile.completed_courses)
                        if completed_count <= 3:
                            sections["student_profile"] += f". Completed: {', '.join(context.student_profile.completed_courses[:3])}"
                        else:
                            sections["student_profile"] += f". Completed: {completed_count} courses"
            
            # Extract context data by source type
            for source in context.context_sources:
                if source.source_type == "vector_search" and source.data:
                    courses = source.data.get("similar_courses", [])[:5]
                    if courses:
                        course_list = "\n".join([
                            f"- {course.get('title', 'Unknown')}: {course.get('description', '')[:100]}..."
                            for course in courses[:3]
                        ])
                        sections["vector_search"] = f"### Similar Courses\n{course_list}"
                
                elif source.source_type == "graph_analysis" and source.data:
                    prereq_info = source.data.get("prerequisite_path", {})
                    if prereq_info:
                        sections["graph_analysis"] = f"### Prerequisites\n- {source.data.get('course_code')}: {prereq_info}"
                
                elif source.source_type == "professor_intel" and source.data:
                    prof_data = source.data.get("professor_intelligence", {})
                    if prof_data:
                        prof_summaries = []
                        for course_code, intel in list(prof_data.items())[:2]:
                            if intel.get("prompt_summary"):
                                prof_summaries.append(f"- {course_code}: {intel['prompt_summary']}")
                        if prof_summaries:
                            sections["professor_intel"] = f"### Professor Ratings\n" + "\n".join(prof_summaries)
                
                elif source.source_type == "difficulty_data" and source.data:
                    diff_data = source.data.get("difficulty_analysis", {})
                    if diff_data:
                        diff_summaries = []
                        for course_code, analysis in list(diff_data.items())[:2]:
                            if analysis.get("prompt_summary"):
                                diff_summaries.append(f"- {course_code}: {analysis['prompt_summary']}")
                        if diff_summaries:
                            sections["difficulty_data"] = f"### Course Difficulty\n" + "\n".join(diff_summaries)
                
                elif source.source_type == "grades_data" and source.data:
                    grades_data = source.data.get("grade_distributions", {})
                    if grades_data:
                        grades_summaries = []
                        for course_code, data in list(grades_data.items())[:2]:
                            gpa = data.get("mean_gpa", 0.0)
                            pass_rate = data.get("pass_rate", 0.0)
                            difficulty = data.get("difficulty_percentile", 50)
                            grades_summaries.append(f"- {course_code}: GPA {gpa:.2f}, Pass Rate {pass_rate*100:.0f}%, Difficulty {difficulty}th percentile")
                        if grades_summaries:
                            sections["grades_data"] = f"### Grade Distributions\n" + "\n".join(grades_summaries)
                
                elif source.source_type == "enrollment_data" and source.data:
                    enroll_data = source.data.get("enrollment_predictions", {})
                    if enroll_data:
                        enroll_summaries = []
                        for course_code, prediction in list(enroll_data.items())[:2]:
                            if prediction.get("prompt_summary"):
                                enroll_summaries.append(f"- {course_code}: {prediction['prompt_summary']}")
                        if enroll_summaries:
                            sections["enrollment_data"] = f"### Registration Advice\n" + "\n".join(enroll_summaries)
            
                elif source.source_type == "schedule_fit":
                    # Schedule fit context (≤120 tokens)
                    schedule_data = source.data.get("schedule_fit", {})
                    if schedule_data and schedule_data.get("summary"):
                        sections["schedule_fit"] = f"### Schedule Analysis\n{schedule_data['summary']}"
            
            # Conversation history
            history_lines = []
            messages = conversation_state.messages[-6:] if conversation_state.messages else []
            for msg in messages:
                role = "You" if msg.role == "user" else "Assistant" 
                content = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
                history_lines.append(f"{role}: {content}")
            
            sections["conversation_history"] = "\n".join(history_lines) if history_lines else "No previous conversation."
            
            # Use class PROMPT_TEMPLATE for strict JSON output (fixes conflicting templates issue)
            # Prepare context sections for PROMPT_TEMPLATE format
            context_sections = []
            provenance_tags = []
            
            for key in ["vector_search", "graph_analysis", "professor_intel", "difficulty_data", "grades_data", "enrollment_data", "schedule_fit", "degree_progress"]:
                if key in sections and sections[key]:
                    if isinstance(sections[key], dict) and "section" in sections[key]:
                        context_sections.append(sections[key]["section"])
                    else:
                        context_sections.append(sections[key])
            
            # Collect provenance information from context sources
            for source in context.context_sources:
                if source.source_type:
                    # Generate default tag with version (default to v1 for now)
                    source_tag = f"{source.source_type}:v1"
                    provenance_tags.append(source_tag)
            
            # Create provenance section for the prompt (always provide safe default)
            if provenance_tags:
                provenance_section = f"=== SOURCES ===\n" + "\n".join([f"- {tag}" for tag in provenance_tags])
            else:
                provenance_section = "=== SOURCES ===\n- No sources available"
            
            # Format prompt using class template with structured JSON requirement
            # Guard against missing keys with safe defaults (fixes template formatting issue)
            prompt_data = {
                "profile_json": sections.get("student_profile", "{}"),
                "context_sections": "\n\n".join(context_sections) if context_sections else "No additional context available.",
                "conversation_history": sections.get("conversation_history", "No previous conversation."),
                "user_message": user_message or "Please provide course recommendations.",
                "provenance_section": provenance_section
            }
            
            # Build final prompt using PROMPT_TEMPLATE to ensure JSON output
            try:
                prompt = self.PROMPT_TEMPLATE.format(**prompt_data)
                
                # Apply token budget clamping if needed
                estimated_tokens = self.token_budget_manager.estimate_tokens(prompt)
                if estimated_tokens > self.token_budget_manager.max_total_tokens:
                    # Truncate context sections if needed to fit budget
                    max_context_tokens = self.token_budget_manager.max_total_tokens - 500  # Reserve for template
                    truncated_context = self.token_budget_manager.clamp_text_to_tokens(
                        "\n\n".join(context_sections), max_context_tokens
                    )
                    prompt_data["context_sections"] = truncated_context
                    prompt = self.PROMPT_TEMPLATE.format(**prompt_data)
                    
            except KeyError as e:
                logger.error(f"Template formatting failed - missing key: {e}")
                return None
            
            # Log final token estimate
            estimated_tokens = self.token_budget_manager.estimate_tokens(prompt)
            logger.info(f"Generated prompt with ~{estimated_tokens} tokens (clamped to {self.token_budget_manager.max_total_tokens})")
            
            return prompt
            
        except Exception as e:
            logger.exception(f"Prompt building failed: {e}")
            return None

    async def _generate_llm_response(
        self, 
        prompt: str, 
        use_fallback: bool = False
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        """
        Generate streaming LLM response using LLM router with first-token deadline.
        
        Expert pattern: 200ms race condition with OpenAI fallback for demo reliability.
        """
        provider = None
        chunk_id = 0
        
        try:
            if use_fallback:
                # Force fallback mode
                gen = self.llm_router._fallback_stream(prompt)
            else:
                # Use deadline-based routing (local vLLM with 200ms deadline → OpenAI fallback)
                gen = self.llm_router.stream_with_deadline(prompt)

            async for event in gen:
                provider = event.get("provider", provider)
                
                if event.get("event") == "token":
                    yield ChatStreamChunk(
                        chunk_id=chunk_id,
                        content=event["text"],
                        chunk_type="token",
                        metadata={"llm_provider": provider or "unknown"}
                    )
                    chunk_id += 1
                    
                elif event.get("event") == "done":
                    # Stream completed successfully
                    break
                    
                elif event.get("event") == "error":
                    logger.warning(f"LLM error from {provider}: {event.get('error')}")
                    yield ChatStreamChunk(
                        chunk_id=chunk_id,
                        content="I encountered an issue generating a response. Please try again.",
                        chunk_type="error",
                        metadata={
                            "llm_provider": provider or "unknown", 
                            "error": event.get("error", "unknown_llm_error")
                        }
                    )
                    return
                    
        except Exception as e:
            logger.exception("LLM generation failed completely")
            yield ChatStreamChunk(
                chunk_id=0,
                content="I'm currently unable to generate a response. Please try again later.",
                chunk_type="error",
                metadata={
                    "llm_provider": provider or "unknown",
                    "error": f"llm_generation_exception: {str(e)}"
                }
            )

    def _extract_course_recommendations(self, response_text: str) -> List[Dict[str, Any]]:
        """
        Extract structured course recommendations from LLM response with strict validation.
        
        Implements expert guidance: strict JSON validation with repair attempts.
        Serves Actionable Prioritization ground truth by enforcing structured output.
        """
        import re
        import json
        
        recommendations = []
        
        # Step 1: Try to extract and validate structured JSON recommendations
        json_text = self._extract_and_repair_json(response_text)
        
        if json_text:
            try:
                parsed_json = json.loads(json_text)
                
                # Strict validation: must have recommendations array
                if not isinstance(parsed_json, dict) or "recommendations" not in parsed_json:
                    logger.warning("JSON missing required 'recommendations' field")
                    return self._handle_json_validation_failure(response_text)
                
                structured_recommendations = parsed_json["recommendations"]
                
                # Validate array structure
                if not isinstance(structured_recommendations, list) or len(structured_recommendations) == 0:
                    logger.warning("Recommendations field is not a valid non-empty array")
                    return self._handle_json_validation_failure(response_text)
                
                # Validate provenance field (required for Information Reliability ground truth)
                provenance = parsed_json.get("provenance", [])
                if not isinstance(provenance, list):
                    logger.warning("Provenance field is not an array")
                    provenance = []
                
                # Store provenance for metadata
                response_provenance = provenance
                
                for i, rec in enumerate(structured_recommendations[:5]):  # Limit to 5
                    # Strict field validation
                    if not isinstance(rec, dict):
                        logger.warning(f"Recommendation {i} is not an object")
                        continue
                    
                    # Required fields validation
                    required_fields = ["course_code", "reasoning"]
                    missing_fields = [field for field in required_fields if field not in rec or not rec[field]]
                    
                    if missing_fields:
                        logger.warning(f"Recommendation {i} missing required fields: {missing_fields}")
                        continue
                    
                    # Course code format validation (SUBJ 1234 format)
                    course_code = rec["course_code"].strip()
                    if not re.match(r'^[A-Z]{2,4}\s+\d{4}$', course_code):
                        logger.warning(f"Invalid course code format: {course_code}")
                        continue
                    
                    recommendations.append({
                        "course_code": course_code,
                        "recommendation_index": i,
                        "priority": rec.get("priority", i + 1),
                        "reasoning": rec["reasoning"].strip(),
                        "difficulty_warning": rec.get("difficulty_warning", "").strip(),
                        "next_steps": rec.get("next_steps", "").strip(),
                        "confidence": 0.9,  # High confidence for valid structured responses
                        "format": "structured_json",
                        "validation_passed": True,
                        "provenance": response_provenance  # Include provenance for Information Reliability
                    })
                
                if recommendations:
                    logger.info(f"Successfully validated {len(recommendations)} structured recommendations")
                    return recommendations
                else:
                    logger.warning("No valid recommendations after strict validation")
                    return self._handle_json_validation_failure(response_text)
                    
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(f"JSON parsing failed after repair attempt: {e}")
                return self._handle_json_validation_failure(response_text)
        
        else:
            logger.warning("No JSON block found in response")
            return self._handle_json_validation_failure(response_text)
    
    def _extract_and_repair_json(self, response_text: str) -> Optional[str]:
        """
        Extract and repair JSON from response text with multiple strategies.
        
        Implements expert guidance: more robust fenced JSON capture with repair.
        """
        import re
        
        # Strategy 1: Standard fenced JSON block
        json_pattern = r'```json\s*({.*?})\s*```'
        match = re.search(json_pattern, response_text, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # Strategy 2: Try raw brace block as fallback (no backticks)
        brace_pattern = r'({\s*"recommendations"\s*:\s*\[.*?\]\s*})'
        brace_match = re.search(brace_pattern, response_text, re.DOTALL)
        if brace_match:
            return brace_match.group(1).strip()
        
        # Strategy 3: Look for any JSON-like structure with recommendations
        loose_pattern = r'({[^{}]*"recommendations"[^{}]*})'
        loose_match = re.search(loose_pattern, response_text, re.DOTALL)
        if loose_match:
            # Attempt to repair common JSON issues
            json_candidate = loose_match.group(1)
            json_candidate = self._repair_common_json_issues(json_candidate)
            return json_candidate
        
        return None
    
    def _repair_common_json_issues(self, json_text: str) -> str:
        """
        Repair common JSON formatting issues from LLM output.
        """
        import re
        
        # Remove trailing commas before closing brackets
        json_text = re.sub(r',(\s*[}\]])', r'\1', json_text)
        
        # Fix unquoted keys (simple cases)
        json_text = re.sub(r'(\w+):', r'"\1":', json_text)
        
        # Fix single quotes to double quotes
        json_text = json_text.replace("'", '"')
        
        # Remove excessive newlines within JSON
        json_text = re.sub(r'\n\s*\n', '\n', json_text)
        
        return json_text.strip()
    
    def _handle_json_validation_failure(self, response_text: str) -> List[Dict[str, Any]]:
        """
        Handle JSON validation failure with graceful degradation.
        
        Implements expert guidance: log as CI failure mode and provide fallback.
        """
        logger.error("STRICT_JSON_VALIDATION_FAILED - this should trigger CI alerts")
        
        # Could implement repair pass here if needed, but for now provide structured fallback
        fallback_recommendations = []
        
        # Extract course codes from text as last resort
        import re
        course_pattern = r'\*\*([A-Z]{2,4}\s+\d{4})\*\*'
        course_matches = re.findall(course_pattern, response_text)
        
        for i, course_code in enumerate(course_matches[:3]):  # Limit fallback to 3
            fallback_recommendations.append({
                "course_code": course_code,
                "recommendation_index": i,
                "priority": i + 1,
                "reasoning": "Recommendation extracted from unstructured response",
                "difficulty_warning": "Please verify course requirements",
                "next_steps": "Consult with advisor for detailed planning",
                "confidence": 0.3,  # Low confidence for failed validation
                "format": "validation_failure_fallback",
                "validation_passed": False,
                "requires_retry": True
            })
        
        if not fallback_recommendations:
            # Ultimate fallback - generic response
            fallback_recommendations.append({
                "course_code": "UNSPECIFIED",
                "recommendation_index": 0,
                "priority": 1,
                "reasoning": "Unable to parse structured recommendations from response",
                "difficulty_warning": "System error - please retry",
                "next_steps": "Please rephrase your question and try again",
                "confidence": 0.1,
                "format": "system_error_fallback",
                "validation_passed": False,
                "requires_retry": True
            })
        
        return fallback_recommendations
    
    def _extract_reasoning_context(self, response_text: str, course_code: str) -> str:
        """Extract reasoning context around a course code mention"""
        try:
            # Find sentences containing the course code
            import re
            
            # Split into sentences
            sentences = re.split(r'[.!?]+', response_text)
            
            for sentence in sentences:
                if course_code in sentence:
                    # Return the sentence with course code, cleaned up
                    clean_sentence = sentence.strip()
                    if len(clean_sentence) > 20:  # Must be substantial
                        return clean_sentence
            
            # Fallback to generic reasoning
            return f"Recommended based on academic profile and course requirements"
            
        except Exception as e:
            logger.warning(f"Failed to extract reasoning context for {course_code}: {e}")
            return "Recommended based on academic analysis"

    # ---------- Redis helpers (timeboxed; graceful degradation) ----------
    async def _redis_get(self, key: str):
        if not self.redis_client:
            return None
        try:
            return await asyncio.wait_for(self.redis_client.get(key), timeout=self.REDIS_OP_TIMEOUT_MS/1000)
        except Exception as e:
            logger.warning(f"Redis GET failed for {key}: {e}")
            return None

    async def _redis_setex(self, key: str, ttl_seconds: int, value: str):
        if not self.redis_client:
            return False
        try:
            await asyncio.wait_for(self.redis_client.setex(key, ttl_seconds, value), timeout=self.REDIS_OP_TIMEOUT_MS/1000)
            return True
        except Exception as e:
            logger.warning(f"Redis SETEX failed for {key}: {e}")
            return False

    async def _load_conversation_state(
        self,
        conversation_id: Optional[str],
        student_profile: Optional[StudentProfile]
    ) -> ConversationState:
        """
        Load or create conversation state with Redis persistence.
        
        Serves Contextual Relevance ground truth by maintaining personalized student context
        across multiple conversation sessions.
        """
        
        # Reconcile/merge profile first (if provided) so state uses canonical data
        merged_profile = None
        if student_profile and self.profile_service:
            try:
                merged_profile = await self.profile_service.merge(student_profile)
            except Exception as e:
                logger.warning(f"Profile merge failed; continuing with provided profile: {e}")

        if conversation_id:
            try:
                cache_key = f"conversation:{conversation_id}"
                cached_state = await self._redis_get(cache_key)
                
                if cached_state:
                    redis_hit.inc()
                    # Parse cached conversation state
                    import json
                    state_data = json.loads(cached_state)
                    
                    # Reconstruct ConversationState from cached data
                    cached_profile = StudentProfile(**state_data["student_profile"])
                    
                    # Reconstruct messages
                    messages = []
                    for msg_data in state_data.get("messages", []):
                        messages.append(ConversationMessage(**msg_data))
                    
                    # Load active recommendations
                    active_recommendations = state_data.get("active_recommendations", [])
                    context_cache = state_data.get("context_cache", {})
                    
                    # Update timestamps
                    cached_state = ConversationState(
                        conversation_id=conversation_id,
                        student_profile=cached_profile,
                        messages=messages,
                        context_cache=context_cache,
                        active_recommendations=active_recommendations,
                        created_at=datetime.fromisoformat(state_data["created_at"]),
                        updated_at=datetime.utcnow()  # Update timestamp on access
                    )
                    
                    logger.debug(f"Loaded conversation state: {conversation_id} with {len(messages)} messages")
                    return cached_state
                else:
                    redis_miss.inc()
                    
            except Exception as e:
                logger.exception(f"Failed to load conversation state {conversation_id}: {e}")
        
        # Create new conversation state
        new_conversation_id = conversation_id or f"conv_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        
        # Use provided profile or create default
        if merged_profile:
            default_profile = merged_profile
        elif student_profile:
            default_profile = student_profile
        else:
            default_profile = StudentProfile(
                student_id="demo_student",
                major="Computer Science", 
                year="sophomore",
                completed_courses=[],
                current_courses=[],
                interests=["machine learning", "software engineering"]
            )
        
        new_state = ConversationState(
            conversation_id=new_conversation_id,
            student_profile=default_profile,
            messages=[],
            context_cache={},
            active_recommendations=[]
        )
        
        # Save new state to Redis immediately
        await self._save_conversation_state(new_state)
        
        logger.info(f"Created new conversation state: {new_conversation_id}")
        return new_state

    async def _save_conversation_state(self, state: ConversationState):
        """
        Save conversation state to Redis with structured serialization.
        
        Serves Contextual Relevance ground truth by persisting personalized context
        for future conversation sessions.
        """
        try:
            cache_key = f"conversation:{state.conversation_id}"

            # Serialize conversation state to JSON-compatible format
            state_data = {
                "conversation_id": state.conversation_id,
                "student_profile": {
                    "student_id": state.student_profile.student_id,
                    "major": state.student_profile.major,
                    "track": state.student_profile.track,
                    "minor": state.student_profile.minor,
                    "year": state.student_profile.year,
                    "completed_courses": state.student_profile.completed_courses or [],
                    "current_courses": state.student_profile.current_courses or [],
                    "interests": state.student_profile.interests or [],
                    "gpa": state.student_profile.gpa,
                    "gpa_goal": state.student_profile.gpa_goal,
                    "risk_tolerance": state.student_profile.risk_tolerance,
                    "blocked_times": state.student_profile.blocked_times or [],
                    "preferences": state.student_profile.preferences or {}
                },
                "messages": [
                    {
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.timestamp.isoformat()
                    } for msg in state.messages[-self.MAX_CONVERSATION_HISTORY:]  # Limit stored messages
                ],
                "context_cache": state.context_cache or {},
                "active_recommendations": state.active_recommendations or [],
                "created_at": state.created_at.isoformat(),
                "updated_at": state.updated_at.isoformat()
            }

            import json
            ok1 = await self._redis_setex(cache_key, self.REDIS_TTL_SECONDS, json.dumps(state_data, default=str))

            # Also maintain a student profile index for cross-conversation continuity
            profile_key = f"student_profile:{state.student_profile.student_id}"
            profile_data = {
                "student_id": state.student_profile.student_id,
                "major": state.student_profile.major,
                "track": state.student_profile.track,
                "minor": state.student_profile.minor,
                "year": state.student_profile.year,
                "completed_courses": state.student_profile.completed_courses or [],
                "current_courses": state.student_profile.current_courses or [],
                "interests": state.student_profile.interests or [],
                "gpa": state.student_profile.gpa,
                "gpa_goal": state.student_profile.gpa_goal,
                "risk_tolerance": state.student_profile.risk_tolerance,
                "blocked_times": state.student_profile.blocked_times or [],
                "preferences": state.student_profile.preferences or {},
                "last_conversation_id": state.conversation_id,
                "last_active": state.updated_at.isoformat()
            }
            ok2 = await self._redis_setex(profile_key, 30 * 24 * 3600, json.dumps(profile_data))

            if ok1 and ok2:
                logger.debug(f"Conversation state saved: {state.conversation_id} ({len(state.messages)} messages)")
        except Exception as e:
            logger.exception(f"Failed to save conversation state {state.conversation_id}: {e}")

    async def get_conversation_state(self, conversation_id: str) -> Optional[ConversationState]:
        """
        Get conversation state by ID from Redis.
        
        Provides API access to conversation history for UI state restoration.
        """
        if True:  # use helpers internally; they no-op if Redis unavailable
            try:
                cache_key = f"conversation:{conversation_id}"
                cached_state = await self._redis_get(cache_key)
                
                if cached_state:
                    import json
                    state_data = json.loads(cached_state)
                    
                    # Reconstruct ConversationState
                    student_profile = StudentProfile(**state_data["student_profile"])
                    
                    messages = []
                    for msg_data in state_data.get("messages", []):
                        messages.append(ConversationMessage(
                            role=msg_data["role"],
                            content=msg_data["content"],
                            timestamp=datetime.fromisoformat(msg_data["timestamp"])
                        ))
                    
                    conversation_state = ConversationState(
                        conversation_id=conversation_id,
                        student_profile=student_profile,
                        messages=messages,
                        context_cache=state_data.get("context_cache", {}),
                        active_recommendations=state_data.get("active_recommendations", []),
                        created_at=datetime.fromisoformat(state_data["created_at"]),
                        updated_at=datetime.fromisoformat(state_data["updated_at"])
                    )
                    
                    logger.debug(f"Retrieved conversation state: {conversation_id}")
                    return conversation_state
                    
            except Exception as e:
                logger.exception(f"Failed to retrieve conversation state {conversation_id}: {e}")
        
        return None

    async def generate_explanation(
        self,
        conversation_id: str,
        recommendation_index: int,
        explanation_type: str = "context_sources"
    ) -> Dict[str, Any]:
        """
        Generate explanation for /explain slash command.
        
        Friend's suggestion: Slack-style power user feature.
        """
        try:
            conversation_state = await self.get_conversation_state(conversation_id)
            if not conversation_state:
                return {
                    "success": False,
                    "error": "Conversation not found"
                }
            
            active_recommendations = conversation_state.active_recommendations
            if recommendation_index >= len(active_recommendations):
                return {
                    "success": False, 
                    "error": "Recommendation index out of range"
                }
            
            recommendation = active_recommendations[recommendation_index]
            
            # Generate explanation based on type
            if explanation_type == "context_sources":
                explanation_data = {
                    "course_code": recommendation["course_code"],
                    "reasoning": recommendation["reasoning"],
                    "confidence": recommendation["confidence"],
                    "context_sources_used": ["vector_search", "graph_analysis"],  # TODO: Get from actual context
                    "explanation_text": f"**{recommendation['course_code']}** was recommended based on semantic similarity to your query and prerequisite analysis from the course graph."
                }
            else:
                explanation_data = {
                    "explanation_text": f"Explanation type '{explanation_type}' not yet implemented."
                }
            
            return {
                "success": True,
                "explanation_type": explanation_type,
                "visualization_data": explanation_data,
                "explanation_text": explanation_data.get("explanation_text", ""),
                "recommendation_context": recommendation
            }
            
        except Exception as e:
            logger.exception(f"Explanation generation failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _enforce_json_schema(self, response_text: str, original_prompt: str):
        """
        Strengthened JSON Schema Enforcement using SchemaEnforcer utility.
        
        Process:
        1. Extract/repair/validate using SchemaEnforcer 
        2. If needed, re-ask via structured JSON completion
        3. Return (validated_model_or_None, legacy_recommendations_list)
        4. Comprehensive Prometheus metrics for observability
        """
        with json_enforce_ms.time():
            # First pass using SchemaEnforcer utility
            model, telemetry = enforce_with_retry(
                ChatAdvisorResponse,
                response_text,
                original_prompt,
            )

            if model:
                json_pass_total.inc()
                json_validations_total.labels(result="pass").inc()  # Legacy compatibility
                return model, self._to_legacy_recs(model)

            # Need a re-ask - use structured JSON completion
            repair_prompt = telemetry["repair_prompt"]
            
            try:
                json_reask_total.inc()  # Legacy compatibility
                
                # Use enhanced structured JSON completion with tool calls
                raw = await self.llm_router.complete_json_structured(
                    repair_prompt,
                    model_schema=ChatAdvisorResponse.model_json_schema(),
                    max_tokens=900,
                )

                # Validate strict result using utility
                model = validate_reask_result(ChatAdvisorResponse, raw)
                if model:
                    json_retry_pass_total.inc()
                    json_validations_total.labels(result="pass").inc()  # Legacy compatibility
                    return model, self._to_legacy_recs(model)
                else:
                    json_fail_total.inc()
                    json_validations_total.labels(result="fail").inc()  # Legacy compatibility
                    
            except Exception as e:
                logger.warning(f"Structured JSON re-ask failed: {e}")
                json_fail_total.inc()
                json_validations_total.labels(result="fail").inc()  # Legacy compatibility

            # Final deterministic fallback to keep UI responsive
            json_fallback_total.inc()  # Legacy compatibility
            fallback = self._fallback_from_text(response_text)
            return None, fallback

    def _extract_and_validate_first_pass(self, response_text: str) -> ChatAdvisorResponse | None:
        json_text = self._extract_fenced_json(response_text) or self._extract_loose_json(response_text)
        if not json_text:
            return None
        # light repair
        json_text = self._repair_json(json_text)
        try:
            import json
            data = json.loads(json_text)
            return ChatAdvisorResponse.model_validate(data)
        except Exception:
            return None

    def _parse_json_strict(self, raw: str) -> ChatAdvisorResponse | None:
        try:
            import json
            data = json.loads(raw)
            return ChatAdvisorResponse.model_validate(data)
        except Exception as e:
            logger.warning(f"Strict JSON parse failed: {e}")
            return None

    def _to_legacy_recs(self, model: ChatAdvisorResponse):
        # Preserve your existing return contract for state/metadata
        legacy = []
        for i, rec in enumerate(model.recommendations):
            legacy.append({
                "course_code": rec.course_code,
                "recommendation_index": i,
                "priority": rec.priority,
                "reasoning": rec.rationale,
                "difficulty_warning": rec.difficulty_warning or "",
                "next_steps": rec.next_action,
                "confidence": 0.95,
                "format": "validated_json",
                "validation_passed": True,
                "provenance": model.provenance,
            })
        return legacy
    
    def _extract_fenced_json(self, response_text: str) -> Optional[str]:
        """Extract JSON from fenced code blocks with multiple patterns"""
        import re
        
        # Pattern 1: Standard ```json ... ``` blocks
        json_pattern = r'```json\s*({.*?})\s*```'
        match = re.search(json_pattern, response_text, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # Pattern 2: Just ``` without json tag
        generic_pattern = r'```\s*({.*?})\s*```'
        match = re.search(generic_pattern, response_text, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # Pattern 3: Raw JSON object at end of response
        json_object_pattern = r'({[\s\S]*"recommendations"[\s\S]*})(?:\s*$)'
        match = re.search(json_object_pattern, response_text)
        if match:
            return match.group(1).strip()
        
        return None

    def _extract_loose_json(self, text: str) -> str | None:
        import re
        m = re.search(r'({\s*"recommendations"\s*:\s*\[.*?\]\s*[^}]*})', text, re.DOTALL)
        return m.group(1).strip() if m else None
    
    def _repair_json(self, json_text: str) -> Optional[str]:
        """Attempt simple JSON repairs for common LLM mistakes"""
        import re
        
        # Common repairs
        repaired = json_text
        
        # Fix trailing commas
        repaired = re.sub(r',\s*}', '}', repaired)
        repaired = re.sub(r',\s*]', ']', repaired)
        
        # Fix missing quotes around keys
        repaired = re.sub(r'(\w+):', r'"\1":', repaired)
        
        # Fix single quotes to double quotes
        repaired = repaired.replace("'", '"')
        
        # Fix missing commas between objects
        repaired = re.sub(r'}\s*{', '}, {', repaired)
        
        return repaired

    def _fallback_from_text(self, text: str):
        # last-resort structured fallback (keeps UI working)
        import re
        codes = re.findall(r'\b([A-Z]{2,4}\s\d{4})\b', text)[:3] or ["UNSPECIFIED"]
        out = []
        for i, code in enumerate(codes):
            out.append({
                "course_code": code,
                "recommendation_index": i,
                "priority": i + 1,
                "reasoning": "Extracted from unstructured response",
                "difficulty_warning": "",
                "next_steps": "check_prereqs",
                "confidence": 0.4,
                "format": "fallback",
                "validation_passed": False,
                "provenance": []
            })
        return out

    async def close(self):
        if self.redis_client:
            await self.redis_client.close()