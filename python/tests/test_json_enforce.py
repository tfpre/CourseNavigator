# Tests for JSON Schema Enforcement with auto-repair and observability
# Covers happy path, retry, failure cases, and integration

import asyncio
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from python.gateway.utils.schema_enforcer import (
    extract_and_validate, 
    build_repair_prompt,
    sanitize_validated,
    enforce_with_retry,
    validate_reask_result,
    JSONEnforceError,
    _extract_fenced_json,
    _extract_json_anywhere,
    _simple_repairs
)
from python.gateway.models import ChatAdvisorResponse, Recommendation, NextAction
from python.gateway.services.chat_orchestrator import ChatOrchestratorService


class TestSchemaEnforcerUtility:
    """Test the core schema enforcer utility functions"""
    
    def test_extract_fenced_json_success(self):
        """Test extraction from code fences"""
        text = 'Here is the response:\n```json\n{"recommendations": []}\n```\nDone!'
        result = _extract_fenced_json(text)
        assert result == '{"recommendations": []}'
        
    def test_extract_fenced_json_generic_fence(self):
        """Test extraction from generic code fences"""
        text = 'Response:\n```\n{"recommendations": [{"course_code": "CS 3110"}]}\n```'
        result = _extract_fenced_json(text)
        assert result == '{"recommendations": [{"course_code": "CS 3110"}]}'
        
    def test_extract_json_anywhere_balanced(self):
        """Test balanced brace extraction"""
        text = 'Some text {"a": 1, "b": {"c": 2}} trailing words'
        result = _extract_json_anywhere(text)
        assert result == '{"a": 1, "b": {"c": 2}}'
        
    def test_extract_json_anywhere_with_quotes(self):
        """Test balanced extraction handles quoted braces"""
        text = 'Text {"message": "This has {braces} in quotes", "value": 42} more text'
        result = _extract_json_anywhere(text)
        assert result == '{"message": "This has {braces} in quotes", "value": 42}'
        
    def test_simple_repairs(self):
        """Test common JSON repairs"""
        # Test trailing comma fix
        assert _simple_repairs('{"a": 1,}') == '{"a": 1}'
        assert _simple_repairs('{"a": [1, 2,]}') == '{"a": [1, 2]}'
        
        # Test smart quotes
        assert _simple_repairs('{"title": "Course"}') == '{"title": "Course"}'
        
        # Test single to double quotes
        assert _simple_repairs("{'key': 'value'}") == '{"key": "value"}'

    def test_extract_and_validate_success(self):
        """Test successful extraction and validation"""
        valid_json = {
            "recommendations": [
                {
                    "course_code": "CS 3110",
                    "title": "Data Structures", 
                    "rationale": "Great course",
                    "priority": 1,
                    "next_action": "add_to_plan"
                }
            ],
            "constraints": [],
            "next_actions": [],
            "notes": "Test",
            "provenance": []
        }
        text = f"```json\n{json.dumps(valid_json)}\n```"
        
        model = extract_and_validate(ChatAdvisorResponse, text)
        assert isinstance(model, ChatAdvisorResponse)
        assert len(model.recommendations) == 1
        assert model.recommendations[0].course_code == "CS 3110"
        
    def test_extract_and_validate_json_error(self):
        """Test JSONEnforceError on malformed JSON"""
        text = '{"recommendations": ['  # Incomplete JSON
        with pytest.raises(JSONEnforceError) as exc_info:
            extract_and_validate(ChatAdvisorResponse, text)
        assert exc_info.value.stage == "json_decode"
        
    def test_extract_and_validate_schema_error(self):
        """Test JSONEnforceError on schema validation failure"""
        invalid_json = '{"wrong_field": "value"}'
        with pytest.raises(JSONEnforceError) as exc_info:
            extract_and_validate(ChatAdvisorResponse, invalid_json)
        assert exc_info.value.stage == "schema_validate"

    def test_build_repair_prompt(self):
        """Test repair prompt generation"""
        prompt = build_repair_prompt(ChatAdvisorResponse, "What courses should I take?")
        assert "What courses should I take?" in prompt
        assert "SCHEMA:" in prompt
        assert "recommendations" in prompt
        assert "No prose, no code fences" in prompt

    def test_sanitize_validated(self):
        """Test sanitization and normalization"""
        # Create a model with duplicate course codes
        rec1 = Recommendation(
            course_code="cs3110",  # Needs normalization
            title="Test", 
            rationale="Test",
            priority=1,
            next_action="add_to_plan"
        )
        rec2 = Recommendation(
            course_code="CS 3110",  # Same course, different format
            title="Test 2",
            rationale="Test 2", 
            priority=2,
            next_action="add_to_plan"
        )
        
        model = ChatAdvisorResponse(
            recommendations=[rec1, rec2],
            notes="Very long notes " * 100  # Long notes to test truncation
        )
        
        sanitized = sanitize_validated(model)
        
        # Should dedupe and normalize course codes
        assert len(sanitized.recommendations) == 1
        assert sanitized.recommendations[0].course_code == "CS 3110"
        assert sanitized.recommendations[0].priority == 1
        
        # Should truncate notes
        assert len(sanitized.notes) <= 1000

    def test_enforce_with_retry_first_pass(self):
        """Test successful first pass validation"""
        valid_json = {
            "recommendations": [
                {
                    "course_code": "CS 3110",
                    "title": "Data Structures",
                    "rationale": "Good course",
                    "priority": 1,
                    "next_action": "add_to_plan"
                }
            ]
        }
        text = json.dumps(valid_json)
        
        model, telemetry = enforce_with_retry(ChatAdvisorResponse, text, "test prompt")
        
        assert model is not None
        assert isinstance(model, ChatAdvisorResponse)
        assert telemetry["stage"] == "first_pass"
        assert "ms" in telemetry

    def test_enforce_with_retry_needs_reask(self):
        """Test when re-ask is needed"""
        invalid_text = '{"malformed": json}'
        
        model, telemetry = enforce_with_retry(ChatAdvisorResponse, invalid_text, "test prompt")
        
        assert model is None
        assert telemetry["stage"] == "needs_reask"
        assert "repair_prompt" in telemetry
        assert "error" in telemetry

    def test_validate_reask_result_success(self):
        """Test successful re-ask validation"""
        valid_json = {
            "recommendations": [
                {
                    "course_code": "MATH 2210",
                    "title": "Linear Algebra",
                    "rationale": "Foundation course",
                    "priority": 1,
                    "next_action": "add_to_plan"
                }
            ]
        }
        raw_json = json.dumps(valid_json)
        
        model = validate_reask_result(ChatAdvisorResponse, raw_json)
        assert model is not None
        assert model.recommendations[0].course_code == "MATH 2210"

    def test_validate_reask_result_failure(self):
        """Test re-ask validation failure"""
        invalid_json = '{"still": "wrong"}'
        
        model = validate_reask_result(ChatAdvisorResponse, invalid_json)
        assert model is None


class TestOrchestratorIntegration:
    """Test integration with ChatOrchestratorService"""
    
    @pytest.fixture
    def mock_orchestrator(self):
        """Create a mock orchestrator with necessary dependencies"""
        orchestrator = AsyncMock(spec=ChatOrchestratorService)
        orchestrator.llm_router = AsyncMock()
        
        # Add the real _to_legacy_recs method
        def _to_legacy_recs(model):
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
        
        orchestrator._to_legacy_recs = _to_legacy_recs
        
        # Add the real _fallback_from_text method
        def _fallback_from_text(text):
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
                    "confidence": 0.5,
                    "format": "fallback_regex",
                    "validation_passed": False,
                    "provenance": [],
                })
            return out
        
        orchestrator._fallback_from_text = _fallback_from_text
        
        return orchestrator

    @pytest.mark.asyncio
    async def test_happy_path_valid_json(self, mock_orchestrator):
        """Test successful JSON validation on first try"""
        # Import the real method to test
        from python.gateway.services.chat_orchestrator import ChatOrchestratorService
        
        good_json = {
            "recommendations": [
                {
                    "course_code": "CS 3110",
                    "title": "Data Structures and Functional Programming",
                    "rationale": "Core FP course",
                    "priority": 1,
                    "next_action": "check_prereqs"
                }
            ],
            "constraints": [],
            "next_actions": [],
            "notes": "",
            "provenance": []
        }
        
        response_text = f"Here's my recommendation:\n```json\n{json.dumps(good_json)}\n```"
        
        # Patch the metrics to avoid import issues
        with patch('python.gateway.services.chat_orchestrator.json_pass_total'), \
             patch('python.gateway.services.chat_orchestrator.json_enforce_ms') as mock_timer, \
             patch('python.gateway.services.chat_orchestrator.json_validations_total'):
            
            mock_timer.time.return_value.__enter__ = MagicMock()
            mock_timer.time.return_value.__exit__ = MagicMock()
            
            # Use the real method
            method = ChatOrchestratorService._enforce_json_schema
            model, legacy = await method(mock_orchestrator, response_text, "advise me")
            
            assert model is not None
            assert isinstance(model, ChatAdvisorResponse)
            assert len(legacy) == 1
            assert legacy[0]["course_code"] == "CS 3110"
            assert legacy[0]["validation_passed"] is True

    @pytest.mark.asyncio
    async def test_retry_repairs_invalid_json(self, mock_orchestrator):
        """Test that invalid JSON triggers re-ask and succeeds"""
        bad_json = "{recommendations: ["  # Malformed JSON
        
        # Mock the structured completion to return valid JSON
        good_json = {
            "recommendations": [
                {
                    "course_code": "MATH 2210",
                    "title": "Linear Algebra",
                    "rationale": "Foundation course",
                    "priority": 1,
                    "next_action": "add_to_plan"
                }
            ],
            "constraints": [],
            "next_actions": [],
            "notes": "",
            "provenance": []
        }
        
        mock_orchestrator.llm_router.complete_json_structured.return_value = json.dumps(good_json)
        
        # Patch the metrics
        with patch('python.gateway.services.chat_orchestrator.json_retry_pass_total'), \
             patch('python.gateway.services.chat_orchestrator.json_enforce_ms') as mock_timer, \
             patch('python.gateway.services.chat_orchestrator.json_reask_total'), \
             patch('python.gateway.services.chat_orchestrator.json_validations_total'):
            
            mock_timer.time.return_value.__enter__ = MagicMock()
            mock_timer.time.return_value.__exit__ = MagicMock()
            
            from python.gateway.services.chat_orchestrator import ChatOrchestratorService
            method = ChatOrchestratorService._enforce_json_schema
            model, legacy = await method(mock_orchestrator, bad_json, "advise me on math")
            
            assert model is not None
            assert model.recommendations[0].course_code == "MATH 2210"
            assert legacy[0]["validation_passed"] is True
            
            # Verify re-ask was called
            mock_orchestrator.llm_router.complete_json_structured.assert_called_once()

    @pytest.mark.asyncio 
    async def test_double_failure_returns_fallback(self, mock_orchestrator):
        """Test fallback when both first pass and re-ask fail"""
        bad_json = "{foo:}"  # Invalid JSON
        
        # Mock structured completion to also return invalid JSON
        mock_orchestrator.llm_router.complete_json_structured.return_value = "{still: invalid}"
        
        with patch('python.gateway.services.chat_orchestrator.json_fail_total'), \
             patch('python.gateway.services.chat_orchestrator.json_enforce_ms') as mock_timer, \
             patch('python.gateway.services.chat_orchestrator.json_reask_total'), \
             patch('python.gateway.services.chat_orchestrator.json_fallback_total'), \
             patch('python.gateway.services.chat_orchestrator.json_validations_total'):
            
            mock_timer.time.return_value.__enter__ = MagicMock()
            mock_timer.time.return_value.__exit__ = MagicMock()
            
            from python.gateway.services.chat_orchestrator import ChatOrchestratorService
            method = ChatOrchestratorService._enforce_json_schema
            model, legacy = await method(mock_orchestrator, bad_json, "advise")
            
            assert model is None
            assert len(legacy) > 0
            assert legacy[0]["format"] == "fallback_regex"
            assert legacy[0]["validation_passed"] is False

    @pytest.mark.asyncio
    async def test_reask_exception_handling(self, mock_orchestrator):
        """Test that re-ask exceptions are handled gracefully"""
        bad_json = "{invalid}"
        
        # Mock structured completion to raise an exception
        mock_orchestrator.llm_router.complete_json_structured.side_effect = Exception("Network error")
        
        with patch('python.gateway.services.chat_orchestrator.json_fail_total'), \
             patch('python.gateway.services.chat_orchestrator.json_enforce_ms') as mock_timer, \
             patch('python.gateway.services.chat_orchestrator.json_reask_total'), \
             patch('python.gateway.services.chat_orchestrator.json_fallback_total'), \
             patch('python.gateway.services.chat_orchestrator.json_validations_total'):
            
            mock_timer.time.return_value.__enter__ = MagicMock()
            mock_timer.time.return_value.__exit__ = MagicMock()
            
            from python.gateway.services.chat_orchestrator import ChatOrchestratorService
            method = ChatOrchestratorService._enforce_json_schema
            model, legacy = await method(mock_orchestrator, bad_json, "advise")
            
            assert model is None
            assert len(legacy) > 0
            assert legacy[0]["format"] == "fallback_regex"


if __name__ == "__main__":
    # Run tests manually if needed
    pytest.main([__file__, "-v"])