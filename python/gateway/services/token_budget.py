# Token Budget Management - Hard Prompt Clamping
# Implements expert friend's recommendation: ~1.2k token ceiling with deterministic allocation

from typing import List, Tuple, Dict, Any

def approx_tokens(text: str) -> int:
    """
    Rough token approximation for budgeting.
    Uses ~4 characters per token heuristic (safe for OpenAI models).
    """
    return max(1, len(text) // 4)

def clamp_text_to_tokens(text: str, max_tokens: int) -> str:
    """
    Clamp text to maximum token count with ellipsis.
    Fast character-based truncation for performance.
    """
    if approx_tokens(text) <= max_tokens:
        return text
    
    # Crude but fast: clamp by characters
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    
    return text[:max_chars] + "..."

def assemble_with_budgets(sections: List[Tuple[str, int]]) -> str:
    """
    Assemble multiple text sections with individual token budgets.
    
    Args:
        sections: List of (text, max_tokens) in priority order
    
    Returns:
        Single string with each section clamped to its budget
    """
    out = []
    for text, token_cap in sections:
        if text and token_cap > 0:
            clamped = clamp_text_to_tokens(text, token_cap)
            out.append(clamped)
    
    return "\n\n".join(out)

def adaptive_token_budget(
    base_sections: List[Tuple[str, str, int]], 
    conversation_length: int,
    max_total_tokens: int = 1200
) -> List[Tuple[str, int]]:
    """
    Adaptive token budget allocation based on conversation context.
    
    Args:
        base_sections: List of (section_name, content, base_budget)
        conversation_length: Number of previous exchanges
        max_total_tokens: Hard ceiling for total prompt
    
    Returns:
        List of (content, adjusted_budget) for assembly
    """
    # Priority scaling: shrink less important contexts first
    priority_weights = {
        "student_profile": 1.0,      # Always keep full profile
        "vector_search": 0.8,        # Can shrink similar courses
        "graph_analysis": 0.9,       # Prerequisites are important
        "professor_intel": 0.85,     # Professor data valuable but flexible
        "difficulty_data": 0.7,      # Nice-to-have context
        "enrollment_data": 0.6,      # Lowest priority for long conversations
    }
    
    # Conversation scaling: reduce secondary contexts in long conversations
    if conversation_length > 10:
        scale_factor = 0.7
    elif conversation_length > 5:
        scale_factor = 0.85
    else:
        scale_factor = 1.0
    
    adjusted_sections = []
    total_budget_used = 0
    
    for section_name, content, base_budget in base_sections:
        if not content:
            continue
        
        # Apply priority and conversation scaling
        weight = priority_weights.get(section_name, 0.5)
        adjusted_budget = int(base_budget * weight * scale_factor)
        
        # Ensure minimum viable budgets
        if adjusted_budget < 20 and base_budget > 0:
            adjusted_budget = 20
        
        # Check total budget ceiling
        if total_budget_used + adjusted_budget > max_total_tokens:
            # Allocate remaining budget
            remaining = max_total_tokens - total_budget_used
            adjusted_budget = max(20, remaining) if remaining > 0 else 0
        
        if adjusted_budget > 0:
            adjusted_sections.append((content, adjusted_budget))
            total_budget_used += adjusted_budget
            
        # Stop if we've hit the ceiling
        if total_budget_used >= max_total_tokens:
            break
    
    return adjusted_sections

class TokenBudgetManager:
    """
    Centralized token budget management for multi-context prompts.
    Prevents prompt bloat while maintaining context quality.
    """
    
    def __init__(self, max_total_tokens: int = 1200):
        self.max_total_tokens = max_total_tokens
        
        # Standard budget allocations (can be overridden)
        self.default_budgets = {
            "student_profile": 200,     # Major, year, completed courses
            "vector_search": 150,       # Top-5 similar courses
            "graph_analysis": 60,       # Prerequisites (≤10 edges)
            "professor_intel": 120,     # Ratings + difficulty summary
            "difficulty_data": 80,      # GPA stats + relative rank
            "enrollment_data": 80,      # Waitlist probability + advice
            "conversation_history": 300, # Last 3-4 exchanges
            "system_template": 150,     # Base instructions
        }
    
    def build_prompt_with_budget(
        self,
        template: str,
        sections: Dict[str, str],
        conversation_length: int = 0
    ) -> str:
        """
        Build final prompt with enforced token budgets.
        
        Args:
            template: Base prompt template with {section_name} placeholders
            sections: Dict of section_name -> content
            conversation_length: Number of previous message exchanges
        
        Returns:
            Final prompt clamped to token budget
        """
        # Prepare sections with base budgets
        base_sections = []
        for section_name, content in sections.items():
            if section_name in self.default_budgets and content:
                budget = self.default_budgets[section_name]
                base_sections.append((section_name, content, budget))
        
        # Get adaptive budgets
        adaptive_sections = adaptive_token_budget(
            base_sections, conversation_length, self.max_total_tokens
        )
        
        # Clamp each section and build final values
        final_sections = {}
        for content, budget in adaptive_sections:
            # Match back to original section name (simplified)
            for section_name, original_content, _ in base_sections:
                if content == original_content:
                    final_sections[section_name] = clamp_text_to_tokens(content, budget)
                    break
        
        # Fill template with clamped sections
        try:
            final_prompt = template.format(**final_sections)
        except KeyError as e:
            # Handle missing sections gracefully
            final_prompt = template
            for section_name, content in final_sections.items():
                placeholder = "{" + section_name + "}"
                if placeholder in final_prompt:
                    final_prompt = final_prompt.replace(placeholder, content)
        
        # Final safety clamp
        final_tokens = approx_tokens(final_prompt)
        if final_tokens > self.max_total_tokens:
            final_prompt = clamp_text_to_tokens(final_prompt, self.max_total_tokens)
        
        return final_prompt
    
    def estimate_tokens(self, text: str) -> int:
        """Get token count estimate for text"""
        return approx_tokens(text)
    
    def get_budget_for_section(self, section_name: str) -> int:
        """Get default token budget for a section"""
        return self.default_budgets.get(section_name, 50)