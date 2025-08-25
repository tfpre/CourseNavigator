#!/usr/bin/env python3
"""
Performance Validation Script - Python replacement for k6 test
Validates SLOs: P95 first-chunk < 500ms, P95 full-response < 3s
"""

import asyncio
import aiohttp
import json
import time
import statistics
from typing import List, Tuple, Dict, Any
import os
import sys

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

async def chat_request_with_timing(session: aiohttp.ClientSession, base_url: str) -> Tuple[float, float, int, bool]:
    """
    Make a chat request and measure timing
    
    Returns:
        (first_chunk_ms, full_response_ms, chunk_count, has_error)
    """
    
    payload = {
        "message": "What CS courses should I take next semester?",
        "student_profile": {
            "student_id": "demo_cs_2027",
            "major": "Computer Science", 
            "year": "sophomore",
            "completed_courses": ["CS 1110", "CS 2110", "MATH 1910", "MATH 1920"],
            "interests": ["Machine Learning", "Software Engineering"]
        },
        "context_preferences": {
            "include_prerequisites": True,
            "include_professor_ratings": True,
            "include_difficulty_info": True,
            "include_enrollment_data": True
        },
        "stream": True,
        "max_recommendations": 5
    }
    
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
        'Cache-Control': 'no-cache'
    }
    
    start_time = time.perf_counter()
    first_chunk_time = None
    chunk_count = 0
    has_error = False
    
    try:
        async with session.post(f"{base_url}/api/chat", json=payload, headers=headers, timeout=15) as response:
            if response.status != 200:
                return 0, 0, 0, True
            
            async for line in response.content:
                line_str = line.decode('utf-8').strip()
                if not line_str or not line_str.startswith('data: '):
                    continue
                    
                try:
                    data_content = line_str[6:]  # Remove 'data: '
                    if data_content == '{}' or data_content == '[DONE]':
                        continue
                        
                    chunk = json.loads(data_content)
                    
                    # Record first meaningful chunk
                    if (first_chunk_time is None and 
                        chunk.get('chunk_type') in ['token', 'context_info', 'course_highlight']):
                        first_chunk_time = time.perf_counter()
                    
                    chunk_count += 1
                    
                    # Check for errors
                    if chunk.get('chunk_type') == 'error':
                        has_error = True
                        print(f"⚠️ Error in stream: {chunk.get('content', 'Unknown error')}")
                    
                    # Stream completed
                    if chunk.get('chunk_type') == 'done':
                        break
                        
                except json.JSONDecodeError as e:
                    print(f"⚠️ Failed to parse SSE chunk: {e}")
                    has_error = True
                    
    except asyncio.TimeoutError:
        print("⚠️ Request timed out")
        return 0, 0, 0, True
    except Exception as e:
        print(f"⚠️ Request failed: {e}")
        return 0, 0, 0, True
    
    end_time = time.perf_counter()
    
    first_chunk_ms = ((first_chunk_time - start_time) * 1000) if first_chunk_time else 0
    full_response_ms = (end_time - start_time) * 1000
    
    return first_chunk_ms, full_response_ms, chunk_count, has_error

async def run_performance_validation(base_url: str = "http://localhost:8000", num_requests: int = 20):
    """Run performance validation with multiple requests"""
    
    print(f"🚀 Running performance validation with {num_requests} requests")
    print(f"   Target SLOs: P95 first-chunk < 500ms, P95 full-response < 3000ms")
    print(f"   API URL: {base_url}")
    print()
    
    # Set demo mode
    os.environ['DEMO_MODE'] = 'true'
    
    first_chunk_times = []
    full_response_times = []
    total_errors = 0
    
    async with aiohttp.ClientSession() as session:
        # Test API health first
        try:
            async with session.get(f"{base_url}/health", timeout=5) as response:
                if response.status != 200:
                    print(f"❌ API health check failed: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Cannot reach API at {base_url}: {e}")
            return False
        
        print("✅ API health check passed")
        
        # Run concurrent requests (simulate load)
        tasks = []
        for i in range(num_requests):
            task = asyncio.create_task(chat_request_with_timing(session, base_url))
            tasks.append(task)
            
            # Add small delay between request starts
            if i < num_requests - 1:
                await asyncio.sleep(0.1)
        
        # Collect results
        print(f"📊 Collecting results from {num_requests} concurrent requests...")
        
        for i, task in enumerate(tasks):
            try:
                first_chunk_ms, full_response_ms, chunk_count, has_error = await task
                
                if has_error:
                    total_errors += 1
                    print(f"   Request {i+1}: ❌ ERROR")
                else:
                    first_chunk_times.append(first_chunk_ms)
                    full_response_times.append(full_response_ms)
                    print(f"   Request {i+1}: ✓ {first_chunk_ms:.0f}ms / {full_response_ms:.0f}ms ({chunk_count} chunks)")
                    
            except Exception as e:
                total_errors += 1
                print(f"   Request {i+1}: ❌ Exception: {e}")
    
    # Calculate statistics
    if not first_chunk_times or not full_response_times:
        print("❌ No successful requests - cannot validate SLOs")
        return False
    
    first_chunk_p95 = statistics.quantiles(first_chunk_times, n=100)[94]  # P95
    full_response_p95 = statistics.quantiles(full_response_times, n=100)[94]  # P95
    error_rate = total_errors / num_requests
    
    print("\n📈 Performance Results:")
    print(f"   First chunk P95: {first_chunk_p95:.1f}ms (target: <500ms)")
    print(f"   Full response P95: {full_response_p95:.1f}ms (target: <3000ms)")
    print(f"   Error rate: {error_rate*100:.1f}% (target: <1%)")
    print(f"   Successful requests: {len(first_chunk_times)}/{num_requests}")
    
    # SLO validation  
    slos_met = [
        first_chunk_p95 < 500,
        full_response_p95 < 3000,
        error_rate < 0.01
    ]
    
    overall_pass = all(slos_met)
    
    print(f"\n🎯 SLO Compliance: {'✅ PASS' if overall_pass else '❌ FAIL'}")
    
    if not slos_met[0]:
        print("   ⚠️  First chunk P95 exceeds 500ms - investigate context service latency")
    if not slos_met[1]:  
        print("   ⚠️  Full response P95 exceeds 3s - investigate LLM response time")
    if not slos_met[2]:
        print("   ⚠️  Error rate exceeds 1% - investigate service reliability")
    
    if overall_pass:
        print("   🚀 Demo is performance-ready!")
    else:
        print("   🔧 Performance tuning required before demo")
    
    return overall_pass

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate CourseNavigator performance SLOs")
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--requests", type=int, default=20, help="Number of test requests")
    
    args = parser.parse_args()
    
    success = asyncio.run(run_performance_validation(args.url, args.requests))
    sys.exit(0 if success else 1)