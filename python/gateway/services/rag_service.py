"""
RAG service that combines vector search and graph context with LLM generation
"""

import logging
import time
from typing import List, Dict, Any, Optional

try:
    import openai
except ImportError:
    openai = None

from ..models import RAGRequest, RAGResponse, CourseInfo, ErrorDetail
from .vector_service import VectorService
from .graph_service import GraphService

logger = logging.getLogger(__name__)

class RAGService:
    """Service for RAG with graph enhancement"""
    
    def __init__(
        self, 
        openai_api_key: Optional[str],
        vector_service: VectorService,
        graph_service: GraphService
    ):
        self.openai_api_key = openai_api_key
        self.vector_service = vector_service
        self.graph_service = graph_service
        
        if openai is None or not openai_api_key:
            logger.warning("OpenAI not available, responses will be mocked")
            self._mock_mode = True
        else:
            openai.api_key = openai_api_key
            self._mock_mode = False
    
    async def process_query(self, request: RAGRequest) -> RAGResponse:
        """
        Process RAG query with graph enhancement
        
        Args:
            request: RAG request with query and parameters
            
        Returns:
            RAGResponse with answer and context
        """
        try:
            start_time = time.time()
            query_metadata = {}
            
            # Step 1: Get embedding for the query
            embedding_start = time.time()
            query_embedding = await self.vector_service.get_embedding(request.query)
            query_metadata["embedding_time_ms"] = int((time.time() - embedding_start) * 1000)
            
            # Step 2: Vector search for relevant courses
            vector_start = time.time()
            courses = await self.vector_service.search_courses(
                query_embedding=query_embedding,
                top_k=request.top_k,
                score_threshold=0.7
            )
            query_metadata["vector_search_time_ms"] = int((time.time() - vector_start) * 1000)
            
            # Step 3: Get graph context if requested
            graph_context = None
            if request.include_graph_context and courses:
                graph_start = time.time()
                course_ids = [course.id for course in courses]
                graph_context = await self.graph_service.get_graph_context(
                    course_ids=course_ids,
                    max_depth=request.max_prerequisite_depth
                )
                query_metadata["graph_query_time_ms"] = int((time.time() - graph_start) * 1000)
            
            # Step 4: Generate response using LLM
            llm_start = time.time()
            if request.mode.value == "prerequisite_path":
                answer = await self._generate_prerequisite_answer(request.query, courses, graph_context)
            else:
                answer = await self._generate_rag_answer(request.query, courses, graph_context)
            query_metadata["llm_generation_time_ms"] = int((time.time() - llm_start) * 1000)
            
            return RAGResponse(
                success=True,
                answer=answer,
                courses=courses,
                graph_context=graph_context,
                query_metadata=query_metadata
            )
            
        except Exception as e:
            logger.error(f"RAG processing failed: {e}")
            return RAGResponse(
                success=False,
                error=ErrorDetail(
                    code="RAG_PROCESSING_ERROR",
                    message="Failed to process RAG query",
                    details={"error": str(e)}
                )
            )
    
    async def _generate_rag_answer(
        self, 
        query: str, 
        courses: List[CourseInfo], 
        graph_context: Optional[Any]
    ) -> str:
        """Generate RAG answer using LLM"""
        
        if self._mock_mode:
            return await self._mock_rag_answer(query, courses, graph_context)
        
        try:
            # Build context from courses and graph
            context_parts = []
            
            # Add course information
            if courses:
                context_parts.append("## Relevant Courses:")
                for course in courses[:5]:  # Top 5 courses
                    context_parts.append(
                        f"**{course.subject} {course.catalog_nbr}: {course.title}**"
                    )
                    if course.description:
                        context_parts.append(course.description[:200] + "...")
                    if course.similarity_score:
                        context_parts.append(f"Relevance: {course.similarity_score:.2f}")
                    context_parts.append("")
            
            # Add graph context
            if graph_context and graph_context.edges:
                context_parts.append("## Prerequisite Relationships:")
                for edge in graph_context.edges[:10]:  # Top 10 edges
                    from_course = next((c for c in graph_context.nodes if c.id == edge.from_course_id), None)
                    to_course = next((c for c in graph_context.nodes if c.id == edge.to_course_id), None)
                    
                    if from_course and to_course:
                        context_parts.append(
                            f"- {from_course.subject} {from_course.catalog_nbr} {edge.type.lower()} "
                            f"{to_course.subject} {to_course.catalog_nbr}"
                        )
                context_parts.append("")
            
            context = "\n".join(context_parts)
            
            # Create prompt for LLM
            prompt = f"""You are a Cornell course advisor helping students with course selection and planning.

User Query: {query}

Course Information:
{context}

Please provide a helpful, accurate response based on the course information above. Focus on:
1. Directly answering the user's question
2. Recommending specific courses when appropriate
3. Explaining prerequisite relationships
4. Providing practical advice for course planning

Keep your response concise but informative."""

            # Call OpenAI API
            response = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful Cornell course advisor."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.7
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return await self._mock_rag_answer(query, courses, graph_context)
    
    async def _generate_prerequisite_answer(
        self, 
        query: str, 
        courses: List[CourseInfo], 
        graph_context: Optional[Any]
    ) -> str:
        """Generate prerequisite-focused answer"""
        
        if not courses:
            return "I couldn't find specific courses matching your query. Please try a more specific course name or subject."
        
        primary_course = courses[0]
        
        if not graph_context or not graph_context.edges:
            return f"**{primary_course.subject} {primary_course.catalog_nbr}: {primary_course.title}**\n\nNo specific prerequisites found in the database. This course may be introductory or have general prerequisites not captured in our system."
        
        # Build prerequisite chain
        prereq_info = []
        prereq_info.append(f"**{primary_course.subject} {primary_course.catalog_nbr}: {primary_course.title}**\n")
        
        # Find direct prerequisites
        direct_prereqs = []
        for edge in graph_context.edges:
            if edge.from_course_id == primary_course.id:
                prereq_course = next((c for c in graph_context.nodes if c.id == edge.to_course_id), None)
                if prereq_course:
                    direct_prereqs.append((prereq_course, edge))
        
        if direct_prereqs:
            prereq_info.append("**Prerequisites:**")
            for prereq_course, edge in direct_prereqs:
                relationship_text = self._format_relationship_type(edge.type)
                prereq_info.append(
                    f"- {prereq_course.subject} {prereq_course.catalog_nbr}: {prereq_course.title} "
                    f"({relationship_text})"
                )
        
        return "\n".join(prereq_info)
    
    def _format_relationship_type(self, edge_type: str) -> str:
        """Format edge type for human reading"""
        type_mapping = {
            "PREREQUISITE": "required before",
            "PREREQUISITE_OR": "one of these required",
            "COREQUISITE": "take concurrently",
            "RECOMMENDED": "recommended",
            "UNSURE": "possibly required"
        }
        return type_mapping.get(edge_type, edge_type.lower())
    
    async def _mock_rag_answer(
        self, 
        query: str, 
        courses: List[CourseInfo], 
        graph_context: Optional[Any]
    ) -> str:
        """Generate mock answer for development"""
        
        if not courses:
            return f"Based on your query '{query}', I would recommend exploring Cornell's course catalog for relevant options. Unfortunately, I couldn't find specific matches in our current dataset."
        
        primary_course = courses[0]
        
        return f"""Based on your query about "{query}", I found several relevant courses:

**Top Recommendation: {primary_course.subject} {primary_course.catalog_nbr}**
{primary_course.title}

{primary_course.description or "This course covers relevant topics for your query."}

**Additional Options:**
{chr(10).join([f"- {c.subject} {c.catalog_nbr}: {c.title}" for c in courses[1:3]])}

The courses shown have strong semantic similarity to your query{" and have been enhanced with prerequisite context from our knowledge graph" if graph_context else ""}. 

*Note: This is a mock response for development. Full LLM integration coming soon.*"""