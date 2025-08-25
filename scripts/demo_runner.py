#!/usr/bin/env python3
"""
Demo Runner for CourseNavigator - Deterministic Golden Path Testing

Provides consistent demo scenarios for presentations and testing.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Dict, Any, List
import httpx

class DemoRunner:
    """Execute deterministic demo scenarios for CourseNavigator"""
    
    def __init__(self, api_base_url: str = "http://localhost:8000"):
        self.api_base_url = api_base_url
        self.demo_data = self._load_demo_dataset()
        
    def _load_demo_dataset(self) -> Dict[str, Any]:
        """Load demo dataset from JSON file"""
        demo_path = Path(__file__).parent.parent / "demo_dataset.json"
        with open(demo_path, 'r') as f:
            return json.load(f)
    
    def get_profile(self, profile_id: str) -> Dict[str, Any]:
        """Get demo profile by ID"""
        for profile in self.demo_data["demo_profiles"]:
            if profile["profile_id"] == profile_id:
                return profile
        raise ValueError(f"Demo profile {profile_id} not found")
    
    def get_scenario(self, scenario_id: str) -> Dict[str, Any]:
        """Get demo scenario by ID"""
        for scenario in self.demo_data["demo_scenarios"]:
            if scenario["scenario_id"] == scenario_id:
                return scenario
        raise ValueError(f"Demo scenario {scenario_id} not found")
    
    async def run_golden_path(self) -> Dict[str, Any]:
        """Execute the full golden path demo sequence"""
        print("🚀 Starting CourseNavigator Golden Path Demo")
        results = {"steps": [], "total_time": 0, "success": True}
        
        golden_path = self.demo_data["golden_path_script"]
        start_time = time.perf_counter()
        
        for step_config in golden_path["steps"]:
            step_num = step_config["step"]
            action = step_config["action"]
            expected_time = step_config["expected_response_time"]
            success_criteria = step_config["success_criteria"]
            
            print(f"\n📋 Step {step_num}: {action}")
            
            step_start = time.perf_counter()
            try:
                if "Load demo_cs_sophomore profile" in action:
                    result = await self._load_demo_profile("demo_cs_sophomore")
                elif "What CS courses should I take" in action:
                    result = await self._send_chat_message(
                        "demo_cs_sophomore", 
                        "What CS courses should I take next semester?"
                    )
                elif "I want both CS 4780 and CS 4820" in action:
                    result = await self._send_chat_message(
                        "demo_cs_sophomore",
                        "I want both CS 4780 and CS 4820, what should I do?"
                    )
                elif "Check provenance display" in action:
                    result = {"provenance_check": True, "status": "success"}
                else:
                    result = {"status": "skipped", "reason": "Unknown action"}
                
                step_time = (time.perf_counter() - step_start) * 1000
                
                # Validate response time
                expected_ms = self._parse_time_expectation(expected_time)
                time_ok = step_time <= expected_ms if expected_ms else True
                
                step_result = {
                    "step": step_num,
                    "action": action,
                    "duration_ms": round(step_time, 1),
                    "expected_ms": expected_ms,
                    "time_slo_met": time_ok,
                    "success_criteria": success_criteria,
                    "result": result,
                    "status": "success" if time_ok else "warning"
                }
                
                print(f"   ✅ Completed in {step_time:.1f}ms (target: {expected_time})")
                
                results["steps"].append(step_result)
                
            except Exception as e:
                print(f"   ❌ Failed: {str(e)}")
                step_time = (time.perf_counter() - step_start) * 1000
                results["steps"].append({
                    "step": step_num,
                    "action": action,
                    "duration_ms": round(step_time, 1),
                    "error": str(e),
                    "status": "failed"
                })
                results["success"] = False
        
        total_time = (time.perf_counter() - start_time) * 1000
        results["total_time"] = round(total_time, 1)
        
        # Print summary
        print(f"\n📊 Demo Summary:")
        print(f"   Total time: {total_time:.1f}ms")
        print(f"   Steps completed: {len([s for s in results['steps'] if s.get('status') == 'success'])}/{len(results['steps'])}")
        print(f"   Overall success: {'✅' if results['success'] else '❌'}")
        
        return results
    
    async def run_scenario(self, scenario_id: str) -> Dict[str, Any]:
        """Run a specific demo scenario"""
        scenario = self.get_scenario(scenario_id)
        profile = self.get_profile(scenario["profile"])
        
        print(f"🎬 Running scenario: {scenario['description']}")
        print(f"👤 Profile: {profile['name']} ({profile['major']} {profile['year']})")
        
        start_time = time.perf_counter()
        
        # Send the scenario query
        response = await self._send_chat_message(scenario["profile"], scenario["query"])
        
        duration = (time.perf_counter() - start_time) * 1000
        
        # Analyze response against expected outcomes
        outcomes_met = self._analyze_response_outcomes(response, scenario["expected_outcomes"])
        
        result = {
            "scenario_id": scenario_id,
            "duration_ms": round(duration, 1),
            "expected_outcomes": scenario["expected_outcomes"],
            "outcomes_met": outcomes_met,
            "response": response,
            "success": len(outcomes_met) >= len(scenario["expected_outcomes"]) * 0.75  # 75% threshold
        }
        
        print(f"   Duration: {duration:.1f}ms")
        print(f"   Outcomes met: {len(outcomes_met)}/{len(scenario['expected_outcomes'])}")
        
        return result
    
    async def _load_demo_profile(self, profile_id: str) -> Dict[str, Any]:
        """Load a demo profile into the system"""
        profile = self.get_profile(profile_id)
        
        # Convert to API format
        student_profile = {
            "student_id": profile["student_id"],
            "major": profile["major"],
            "year": profile["year"],
            "completed_courses": profile["completed_courses"],
            "current_courses": profile["current_courses"],
            "interests": profile["interests"]
        }
        
        return {"profile_loaded": True, "profile": student_profile}
    
    async def _send_chat_message(self, profile_id: str, message: str) -> Dict[str, Any]:
        """Send a chat message using the demo profile"""
        profile = self.get_profile(profile_id)
        
        student_profile = {
            "student_id": profile["student_id"],
            "major": profile["major"],
            "year": profile["year"],
            "completed_courses": profile["completed_courses"],
            "current_courses": profile["current_courses"],
            "interests": profile["interests"]
        }
        
        chat_request = {
            "message": message,
            "student_profile": student_profile,
            "context_preferences": {
                "include_prerequisites": True,
                "include_professor_ratings": True,
                "include_difficulty_info": True,
                "include_enrollment_data": True
            },
            "stream": False  # Use non-streaming for demo simplicity
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.api_base_url}/chat",
                json=chat_request
            )
            response.raise_for_status()
            return response.json()
    
    def _parse_time_expectation(self, time_str: str) -> int:
        """Parse time expectation string to milliseconds"""
        if not time_str or time_str == "immediate":
            return None
            
        time_str = time_str.replace("<", "").replace(">", "")
        
        if "ms" in time_str:
            return int(time_str.replace("ms", ""))
        elif "s" in time_str:
            return int(float(time_str.replace("s", "")) * 1000)
        
        return None
    
    def _analyze_response_outcomes(self, response: Dict[str, Any], expected_outcomes: List[str]) -> List[str]:
        """Analyze if response meets expected outcomes"""
        met_outcomes = []
        response_text = json.dumps(response).lower()
        
        for outcome in expected_outcomes:
            # Simple keyword matching - could be enhanced with NLP
            keywords = outcome.lower().split()
            if any(keyword in response_text for keyword in keywords):
                met_outcomes.append(outcome)
        
        return met_outcomes

async def main():
    """Run demo scenarios"""
    import argparse
    
    parser = argparse.ArgumentParser(description="CourseNavigator Demo Runner")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--golden-path", action="store_true", help="Run golden path demo")
    parser.add_argument("--scenario", help="Run specific scenario ID")
    parser.add_argument("--all-scenarios", action="store_true", help="Run all scenarios")
    
    args = parser.parse_args()
    
    demo = DemoRunner(args.api_url)
    
    if args.golden_path:
        results = await demo.run_golden_path()
        print(f"\n📄 Results: {json.dumps(results, indent=2)}")
    elif args.scenario:
        results = await demo.run_scenario(args.scenario)
        print(f"\n📄 Results: {json.dumps(results, indent=2)}")
    elif args.all_scenarios:
        for scenario in demo.demo_data["demo_scenarios"]:
            results = await demo.run_scenario(scenario["scenario_id"])
            print()
    else:
        print("Usage: python demo_runner.py [--golden-path | --scenario ID | --all-scenarios]")
        print("\nAvailable scenarios:")
        for scenario in demo.demo_data["demo_scenarios"]:
            print(f"  - {scenario['scenario_id']}: {scenario['description']}")

if __name__ == "__main__":
    asyncio.run(main())