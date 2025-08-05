"""
Tests for Pydantic models to ensure API contract validation
"""

import pytest
from pydantic import ValidationError

from gateway.models import (
    RAGRequest, CentralityRequest, CommunityRequest, 
    GraphSubgraphRequest, ShortestPathRequest,
    SearchMode, CourseInfo, PrerequisiteEdge
)


class TestPydanticModels:
    """Test suite for Pydantic model validation"""
    
    def test_rag_request_valid(self):
        """Test valid RAG request creation"""
        request = RAGRequest(
            query="What are the prerequisites for CS 4780?",
            mode=SearchMode.GRAPH_AWARE,
            top_k=10,
            include_graph_context=True,
            max_prerequisite_depth=3
        )
        
        assert request.query == "What are the prerequisites for CS 4780?"
        assert request.mode == SearchMode.GRAPH_AWARE
        assert request.top_k == 10
        assert request.include_graph_context is True
        assert request.max_prerequisite_depth == 3
    
    def test_rag_request_defaults(self):
        """Test RAG request with defaults"""
        request = RAGRequest(query="Test query")
        
        assert request.query == "Test query"
        assert request.mode == SearchMode.GRAPH_AWARE  # Default
        assert request.top_k == 10  # Default
        assert request.include_graph_context is True  # Default
        assert request.max_prerequisite_depth == 3  # Default
    
    def test_rag_request_validation_errors(self):
        """Test RAG request validation failures"""
        # Empty query
        with pytest.raises(ValidationError):
            RAGRequest(query="")
        
        # Query too long
        with pytest.raises(ValidationError):
            RAGRequest(query="x" * 501)  # Over 500 char limit
        
        # Invalid top_k
        with pytest.raises(ValidationError):
            RAGRequest(query="test", top_k=0)  # Below minimum
        
        with pytest.raises(ValidationError):
            RAGRequest(query="test", top_k=100)  # Above maximum
        
        # Invalid max_prerequisite_depth
        with pytest.raises(ValidationError):
            RAGRequest(query="test", max_prerequisite_depth=0)  # Below minimum
        
        with pytest.raises(ValidationError):
            RAGRequest(query="test", max_prerequisite_depth=20)  # Above maximum
    
    def test_centrality_request_valid(self):
        """Test valid centrality request creation"""
        request = CentralityRequest(
            top_n=50,
            damping_factor=0.85,
            min_betweenness=0.01,
            min_in_degree=2
        )
        
        assert request.top_n == 50
        assert request.damping_factor == 0.85
        assert request.min_betweenness == 0.01
        assert request.min_in_degree == 2
    
    def test_centrality_request_defaults(self):
        """Test centrality request with defaults"""
        request = CentralityRequest()
        
        assert request.top_n == 20  # Default
        assert request.damping_factor == 0.85  # Default
        assert request.min_betweenness == 0.01  # Default
        assert request.min_in_degree == 2  # Default
    
    def test_centrality_request_validation(self):
        """Test centrality request validation"""
        # Invalid top_n
        with pytest.raises(ValidationError):
            CentralityRequest(top_n=0)
        
        with pytest.raises(ValidationError):
            CentralityRequest(top_n=1001)  # Above maximum
        
        # Invalid damping_factor
        with pytest.raises(ValidationError):
            CentralityRequest(damping_factor=0.0)  # Below minimum
        
        with pytest.raises(ValidationError):
            CentralityRequest(damping_factor=1.0)  # Above maximum
    
    def test_community_request_valid(self):
        """Test valid community request creation"""
        request = CommunityRequest(algorithm="louvain")
        
        assert request.algorithm == "louvain"
    
    def test_community_request_validation(self):
        """Test community request validation"""
        # Invalid algorithm
        with pytest.raises(ValidationError):
            CommunityRequest(algorithm="invalid_algorithm")
    
    def test_graph_subgraph_request_valid(self):
        """Test valid graph subgraph request creation"""
        request = GraphSubgraphRequest(
            max_nodes=100,
            max_edges=200,
            include_centrality=True,
            include_communities=False,
            filter_by_subject=["CS", "MATH"]
        )
        
        assert request.max_nodes == 100
        assert request.max_edges == 200
        assert request.include_centrality is True
        assert request.include_communities is False
        assert request.filter_by_subject == ["CS", "MATH"]
    
    def test_graph_subgraph_request_defaults(self):
        """Test graph subgraph request with defaults"""
        request = GraphSubgraphRequest()
        
        assert request.max_nodes == 50  # Default
        assert request.max_edges == 100  # Default
        assert request.include_centrality is True  # Default
        assert request.include_communities is True  # Default
        assert request.filter_by_subject is None  # Default
    
    def test_graph_subgraph_request_validation(self):
        """Test graph subgraph request validation"""
        # Invalid max_nodes
        with pytest.raises(ValidationError):
            GraphSubgraphRequest(max_nodes=4)  # Below minimum
        
        with pytest.raises(ValidationError):
            GraphSubgraphRequest(max_nodes=300)  # Above maximum
        
        # Invalid max_edges
        with pytest.raises(ValidationError):
            GraphSubgraphRequest(max_edges=5)  # Below minimum
        
        with pytest.raises(ValidationError):
            GraphSubgraphRequest(max_edges=600)  # Above maximum
    
    def test_shortest_path_request_valid(self):
        """Test valid shortest path request creation"""
        request = ShortestPathRequest(
            target_course="CS 4780",
            completed_courses=["CS 2110", "MATH 2940"]
        )
        
        assert request.target_course == "CS 4780"
        assert request.completed_courses == ["CS 2110", "MATH 2940"]
    
    def test_shortest_path_request_defaults(self):
        """Test shortest path request with defaults"""
        request = ShortestPathRequest(target_course="CS 4780")
        
        assert request.target_course == "CS 4780"
        assert request.completed_courses == []  # Default empty list
    
    def test_shortest_path_request_validation(self):
        """Test shortest path request validation"""
        # Empty target_course
        with pytest.raises(ValidationError):
            ShortestPathRequest(target_course="")
    
    def test_course_info_model(self):
        """Test CourseInfo model creation and validation"""
        course = CourseInfo(
            id="CS-2110",
            subject="CS",
            catalog_nbr="2110",
            title="Object-Oriented Programming and Data Structures",
            description="Introduction to object-oriented concepts...",
            credits="4",
            similarity_score=0.95,
            graph_relevance=0.87
        )
        
        assert course.id == "CS-2110"
        assert course.subject == "CS"
        assert course.catalog_nbr == "2110"
        assert course.title == "Object-Oriented Programming and Data Structures"
        assert course.similarity_score == 0.95
        assert course.graph_relevance == 0.87
    
    def test_course_info_optional_fields(self):
        """Test CourseInfo with only required fields"""
        course = CourseInfo(
            id="MATH-2940",
            subject="MATH",
            catalog_nbr="2940", 
            title="Linear Algebra for Engineers"
        )
        
        assert course.id == "MATH-2940"
        assert course.description is None
        assert course.credits is None
        assert course.similarity_score is None
        assert course.graph_relevance is None
    
    def test_prerequisite_edge_model(self):
        """Test PrerequisiteEdge model creation and validation"""
        edge = PrerequisiteEdge(
            from_course_id="CS-2110",
            to_course_id="CS-3110",
            type="PREREQUISITE",
            confidence=0.87
        )
        
        assert edge.from_course_id == "CS-2110"
        assert edge.to_course_id == "CS-3110"
        assert edge.type == "PREREQUISITE"
        assert edge.confidence == 0.87
    
    def test_prerequisite_edge_confidence_validation(self):
        """Test PrerequisiteEdge confidence field validation"""
        # Valid confidence
        edge = PrerequisiteEdge(
            from_course_id="CS-2110",
            to_course_id="CS-3110", 
            type="PREREQUISITE",
            confidence=0.5
        )
        assert edge.confidence == 0.5
        
        # Invalid confidence - too low
        with pytest.raises(ValidationError):
            PrerequisiteEdge(
                from_course_id="CS-2110",
                to_course_id="CS-3110",
                type="PREREQUISITE", 
                confidence=-0.1
            )
        
        # Invalid confidence - too high
        with pytest.raises(ValidationError):
            PrerequisiteEdge(
                from_course_id="CS-2110",
                to_course_id="CS-3110",
                type="PREREQUISITE",
                confidence=1.5
            )
    
    def test_search_mode_enum(self):
        """Test SearchMode enum values"""
        assert SearchMode.SEMANTIC == "semantic"
        assert SearchMode.GRAPH_AWARE == "graph_aware"
        assert SearchMode.PREREQUISITE_PATH == "prereq_path"
        
        # Test in request
        request = RAGRequest(query="test", mode=SearchMode.SEMANTIC)
        assert request.mode == "semantic"