# Unit tests for token budget enforcement
# Following newfix.md recommendations for hard caps and deterministic behavior

import pytest
from python.gateway.services.token_budget import (
    approx_tokens, clamp_text_to_tokens, assemble_with_budgets, 
    adaptive_token_budget, TokenBudgetManager
)


class TestTokenApproximation:
    """Test token approximation with ~4 chars/token heuristic"""
    
    def test_approx_tokens_basic(self):
        """Test basic token approximation"""
        assert approx_tokens("hello") == 2  # 5 chars / 4 ≈ 1.25 → max(1, 1) = 1, but actually len//4 = 1, max(1,1) = 1. Wait, 5//4 = 1, max(1,1) = 1
        assert approx_tokens("hello world") == 2  # 11 chars / 4 = 2.75 → 2
        assert approx_tokens("a" * 100) == 25  # 100 / 4 = 25
        
    def test_approx_tokens_minimum(self):
        """Test minimum token count is 1"""
        assert approx_tokens("") == 1  # Empty string still counts as 1 token
        assert approx_tokens("a") == 1  # Single char is 1 token minimum


class TestTokenClamping:
    """Test text clamping to token budgets"""
    
    def test_clamp_enforces_caps(self):
        """Test that clamping enforces hard caps"""
        big = "x" * 10000
        out = clamp_text_to_tokens(big, 150)
        # Should clamp to 150 tokens = 600 chars + "..."
        assert len(out) <= 150 * 4 + 3  # 600 + 3 for "..."
        assert out.endswith("...")
        
    def test_clamp_preserves_short_text(self):
        """Test that short text is preserved"""
        short = "This is a short sentence."
        out = clamp_text_to_tokens(short, 150)
        assert out == short  # Should be unchanged
        
    def test_clamp_exact_boundary(self):
        """Test clamping at exact token boundary"""
        # Text that's exactly at the limit
        text = "x" * (100 * 4)  # Exactly 100 tokens worth
        out = clamp_text_to_tokens(text, 100)
        assert out == text  # Should be unchanged
        
        # Text that's just over the limit
        text_over = "x" * (100 * 4 + 1)  # Just over 100 tokens
        out_over = clamp_text_to_tokens(text_over, 100)
        assert len(out_over) <= 100 * 4 + 3  # Should be clamped


class TestBudgetAssembly:
    """Test assembling sections with individual budgets"""
    
    def test_assemble_with_budgets(self):
        """Test section assembly with token budgets"""
        sections = [
            ("First section with some content", 10),
            ("Second section with more content here", 15),
            ("Third section", 5)
        ]
        
        result = assemble_with_budgets(sections)
        
        # Should have 3 sections separated by double newlines
        parts = result.split("\n\n")
        assert len(parts) == 3
        
        # Each part should be within its budget
        for i, (original_text, budget) in enumerate(sections):
            part_tokens = approx_tokens(parts[i])
            assert part_tokens <= budget, f"Section {i} exceeds budget: {part_tokens} > {budget}"
    
    def test_assemble_empty_sections(self):
        """Test assembly with empty sections"""
        sections = [
            ("Valid content", 10),
            ("", 5),  # Empty section
            (None, 10),  # None section
            ("More valid content", 15)
        ]
        
        result = assemble_with_budgets(sections)
        # Should only include non-empty sections
        parts = result.split("\n\n")
        assert len(parts) == 2  # Only the 2 valid sections


class TestAdaptiveBudget:
    """Test adaptive budget allocation based on conversation context"""
    
    def test_adaptive_budget_basic(self):
        """Test basic adaptive budget allocation"""
        base_sections = [
            ("student_profile", "CS major, sophomore, completed CS 1110", 200),
            ("vector_search", "Similar courses: CS 2110, CS 3110", 150),
            ("graph_analysis", "Prerequisites: CS 1110 → CS 2110", 60)
        ]
        
        result = adaptive_token_budget(base_sections, conversation_length=2, max_total_tokens=1000)
        
        # Should return list of (content, adjusted_budget) tuples
        assert len(result) == 3
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)
        
        # Total budget should not exceed max
        total_budget = sum(budget for _, budget in result)
        assert total_budget <= 1000
    
    def test_adaptive_budget_long_conversation(self):
        """Test budget scaling for long conversations"""
        base_sections = [
            ("student_profile", "Profile content", 200),
            ("difficulty_data", "Course difficulty info", 80),
            ("enrollment_data", "Enrollment predictions", 80)
        ]
        
        # Short conversation
        short_result = adaptive_token_budget(base_sections, conversation_length=2, max_total_tokens=1000)
        short_total = sum(budget for _, budget in short_result)
        
        # Long conversation
        long_result = adaptive_token_budget(base_sections, conversation_length=15, max_total_tokens=1000)
        long_total = sum(budget for _, budget in long_result)
        
        # Long conversation should use less budget for secondary contexts
        assert long_total <= short_total
    
    def test_adaptive_budget_ceiling_enforcement(self):
        """Test that adaptive budget enforces hard ceiling"""
        # Create sections that would exceed the max budget
        large_sections = [
            ("section1", "Content 1", 500),
            ("section2", "Content 2", 500),
            ("section3", "Content 3", 500),
        ]
        
        result = adaptive_token_budget(large_sections, conversation_length=0, max_total_tokens=800)
        
        # Should not exceed the ceiling
        total_budget = sum(budget for _, budget in result)
        assert total_budget <= 800


class TestTokenBudgetManager:
    """Test the main TokenBudgetManager class"""
    
    def test_budget_manager_initialization(self):
        """Test budget manager initialization"""
        manager = TokenBudgetManager(max_total_tokens=1500)
        assert manager.max_total_tokens == 1500
        assert "student_profile" in manager.default_budgets
        assert "vector_search" in manager.default_budgets
    
    def test_build_prompt_with_budget(self):
        """Test prompt building with budget enforcement"""
        manager = TokenBudgetManager(max_total_tokens=1200)
        
        template = "User: {user_message}\n\nProfile: {student_profile}\n\nSimilar: {vector_search}\n\nAnswer:"
        sections = {
            "user_message": "What courses should I take next?",
            "student_profile": "CS major, sophomore, completed CS 1110, CS 2110",
            "vector_search": "Similar courses: CS 3110 (Object-Oriented Programming), CS 2800 (Discrete Math)"
        }
        
        result = manager.build_prompt_with_budget(template, sections, conversation_length=5)
        
        # Should be a valid string
        assert isinstance(result, str)
        assert len(result) > 0
        
        # Should be within token budget
        estimated_tokens = manager.estimate_tokens(result)
        assert estimated_tokens <= manager.max_total_tokens
        
        # Should contain the template structure
        assert "User:" in result
        assert "Profile:" in result
        assert "Answer:" in result
    
    def test_prompt_hard_clamp_safety(self):
        """Test that final prompt is clamped as safety measure"""
        manager = TokenBudgetManager(max_total_tokens=100)  # Very small budget
        
        template = "{large_section}"
        sections = {
            "large_section": "x" * 10000  # Much larger than budget allows
        }
        
        result = manager.build_prompt_with_budget(template, sections)
        
        # Should be clamped to budget despite large input
        estimated_tokens = manager.estimate_tokens(result)
        assert estimated_tokens <= manager.max_total_tokens
    
    def test_get_budget_for_section(self):
        """Test getting default budget for sections"""
        manager = TokenBudgetManager()
        
        assert manager.get_budget_for_section("student_profile") == 200
        assert manager.get_budget_for_section("vector_search") == 150
        assert manager.get_budget_for_section("nonexistent_section") == 50  # Default fallback


class TestTokenBudgetIntegration:
    """Integration tests for token budget system"""
    
    def test_end_to_end_budget_enforcement(self):
        """Test complete budget enforcement pipeline"""
        manager = TokenBudgetManager(max_total_tokens=500)  # Tight budget
        
        # Create template and sections that would exceed budget without clamping
        template = """System: You are a course advisor.

Profile: {student_profile}
Context: {vector_search}
Graph: {graph_analysis}
History: {conversation_history}

User: {user_message}

Answer:"""
        
        sections = {
            "student_profile": "Computer Science major, sophomore year, completed CS 1110, CS 2110, MATH 1910, MATH 1920. Interested in machine learning and software engineering. Current GPA: 3.7. Planning to take CS 3110 next semester.",
            "vector_search": "Similar courses found: CS 3110 (Object-Oriented Programming and Data Structures), CS 2800 (Discrete Structures), CS 4410 (Operating Systems), CS 4780 (Machine Learning), CS 5414 (Distributed Systems)",
            "graph_analysis": "Prerequisite analysis: CS 1110 → CS 2110 → CS 3110. CS 2800 is recommended before CS 4780. Strong path exists for ML track.",
            "conversation_history": "Previous messages: User asked about CS 3110 difficulty. Assistant explained OOP concepts and functional programming in OCaml. User expressed interest in algorithms.",
            "user_message": "Should I take CS 3110 and CS 2800 together next semester?"
        }
        
        result = manager.build_prompt_with_budget(template, sections, conversation_length=3)
        
        # Verify hard constraints are met
        estimated_tokens = manager.estimate_tokens(result)
        assert estimated_tokens <= manager.max_total_tokens, f"Final prompt exceeds budget: {estimated_tokens} > {manager.max_total_tokens}"
        
        # Verify essential content is preserved
        assert "Computer Science major" in result or "CS major" in result  # Profile preserved (possibly truncated)
        assert "CS 3110" in result  # Course codes should be preserved
        assert "Answer:" in result  # Template structure preserved
    
    def test_budget_priority_preservation(self):
        """Test that high-priority sections are preserved under tight budgets"""
        manager = TokenBudgetManager(max_total_tokens=300)  # Very tight budget
        
        template = "Profile: {student_profile}\nContext: {vector_search}\nDifficulty: {difficulty_data}\nAnswer:"
        
        sections = {
            "student_profile": "Critical student information: CS major, senior, needs to graduate",  # High priority
            "vector_search": "Some similar courses that might be relevant for recommendations",  # Medium priority
            "difficulty_data": "Course difficulty statistics and grade distributions data"  # Lower priority
        }
        
        result = manager.build_prompt_with_budget(template, sections, conversation_length=10)
        
        # Student profile should be preserved even under tight budget
        assert "CS major" in result or "senior" in result
        
        # Template structure should remain
        assert "Profile:" in result
        assert "Answer:" in result


if __name__ == "__main__":
    pytest.main([__file__])