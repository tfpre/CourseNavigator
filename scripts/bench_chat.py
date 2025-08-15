#!/usr/bin/env python3
# Performance Benchmark Script - P50/P95 First-Token & Full-Completion Latency
# Implements expert friend's recommendation for SLO compliance measurement

import asyncio
import httpx
import time
import statistics
import json
import argparse
import sys
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any

class ChatBenchmark:
    """
    Benchmark chat endpoint performance with focus on:
    - First-token latency (target: <200ms P95)
    - Full completion latency (target: <500ms P95) 
    - Streaming performance and error rates
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout_s: float = 10.0
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.chat_url = f"{self.base_url}/api/chat"
    
    async def single_chat_request(
        self,
        payload: Dict[str, Any],
        request_id: int
    ) -> Optional[Tuple[float, float, int, bool]]:
        """
        Execute single chat request and measure timings.
        
        Returns:
            (first_token_ms, total_ms, token_count, success) or None if failed
        """
        t0 = time.perf_counter()
        first_token_time = None
        token_count = 0
        success = False
        
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_s),
                http2=True
            ) as client:
                async with client.stream(
                    "POST", 
                    self.chat_url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                        "Cache-Control": "no-cache"
                    }
                ) as response:
                    if response.status_code != 200:
                        print(f"Request {request_id}: HTTP {response.status_code}")
                        return None
                    
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        
                        if line.strip() == "data: {}":  # Empty close event
                            continue
                        
                        try:
                            event_data = line[5:]  # Remove "data: " prefix
                            chunk = json.loads(event_data)
                            
                            if chunk.get("chunk_type") == "token":
                                if first_token_time is None:
                                    first_token_time = (time.perf_counter() - t0) * 1000
                                token_count += 1
                            
                            elif chunk.get("chunk_type") == "done":
                                success = True
                                break
                                
                            elif chunk.get("chunk_type") == "error":
                                print(f"Request {request_id}: LLM error - {chunk.get('content', 'unknown')}")
                                return None
                                
                        except json.JSONDecodeError:
                            continue  # Skip malformed chunks
            
            if success and first_token_time is not None:
                total_time = (time.perf_counter() - t0) * 1000
                return (first_token_time, total_time, token_count, True)
            
        except Exception as e:
            print(f"Request {request_id}: Exception - {e}")
        
        return None
    
    async def run_benchmark(
        self,
        n_requests: int = 50,
        concurrency: int = 1,
        query: str = "What CS courses should I take next semester?",
        student_profile: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run benchmark with specified parameters.
        
        Args:
            n_requests: Total number of requests to execute
            concurrency: Number of concurrent requests (1 = sequential)
            query: Chat query to send
            student_profile: Optional student profile for context
        """
        print(f"🚀 Starting benchmark: {n_requests} requests, concurrency={concurrency}")
        print(f"Target: P95 first-token <200ms, P95 total <500ms")
        print(f"Query: {query[:50]}...")
        print()
        
        # Default student profile for consistent testing
        if student_profile is None:
            student_profile = {
                "student_id": "bench_student",
                "major": "Computer Science",
                "year": "sophomore",
                "completed_courses": ["CS 1110", "MATH 1910", "CS 2110"],
                "current_courses": ["CS 2800"],
                "interests": ["Machine Learning", "Software Engineering"]
            }
        
        # Prepare chat payload
        payload = {
            "message": query,
            "student_profile": student_profile,
            "context_preferences": {
                "include_prerequisites": True,
                "include_professor_ratings": True,
                "include_difficulty_info": True,
                "include_enrollment_data": True,
                "include_similar_courses": True
            },
            "stream": True,
            "max_recommendations": 5
        }
        
        # Execute requests
        start_time = time.perf_counter()
        
        if concurrency == 1:
            # Sequential execution
            results = []
            for i in range(n_requests):
                print(f"\rProgress: {i+1}/{n_requests}", end="", flush=True)
                result = await self.single_chat_request(payload, i)
                if result:
                    results.append(result)
                    
                # Brief delay to avoid overwhelming server
                await asyncio.sleep(0.1)
        else:
            # Concurrent execution
            semaphore = asyncio.Semaphore(concurrency)
            
            async def bounded_request(req_id: int):
                async with semaphore:
                    return await self.single_chat_request(payload, req_id)
            
            tasks = [bounded_request(i) for i in range(n_requests)]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)
            results = [r for r in raw_results if r is not None and not isinstance(r, Exception)]
        
        elapsed_s = time.perf_counter() - start_time
        print(f"\n\n✅ Completed in {elapsed_s:.1f}s")
        
        if not results:
            print("❌ No successful requests!")
            return {"error": "no_successful_requests", "elapsed_s": elapsed_s}
        
        # Calculate statistics
        first_tokens = [r[0] for r in results]
        total_times = [r[1] for r in results]
        token_counts = [r[2] for r in results]
        
        def percentile(data: List[float], p: int) -> float:
            return statistics.quantiles(data, n=100)[p-1] if len(data) > 1 else data[0]
        
        stats = {
            "benchmark_config": {
                "n_requests": n_requests,
                "successful_requests": len(results),
                "success_rate": len(results) / n_requests,
                "concurrency": concurrency,
                "query": query,
                "elapsed_s": round(elapsed_s, 1)
            },
            "first_token_latency_ms": {
                "p50": round(statistics.median(first_tokens), 1),
                "p95": round(percentile(first_tokens, 95), 1),
                "p99": round(percentile(first_tokens, 99), 1),
                "min": round(min(first_tokens), 1),
                "max": round(max(first_tokens), 1),
                "mean": round(statistics.mean(first_tokens), 1)
            },
            "total_completion_ms": {
                "p50": round(statistics.median(total_times), 1),
                "p95": round(percentile(total_times, 95), 1),
                "p99": round(percentile(total_times, 99), 1),
                "min": round(min(total_times), 1),
                "max": round(max(total_times), 1),
                "mean": round(statistics.mean(total_times), 1)
            },
            "tokens": {
                "mean_tokens": round(statistics.mean(token_counts), 1),
                "total_tokens": sum(token_counts)
            },
            "slo_compliance": {
                "first_token_p95_target": "200ms",
                "first_token_p95_actual": round(percentile(first_tokens, 95), 1),
                "first_token_slo_met": percentile(first_tokens, 95) < 200,
                "total_p95_target": "500ms", 
                "total_p95_actual": round(percentile(total_times, 95), 1),
                "total_slo_met": percentile(total_times, 95) < 500
            }
        }
        
        return stats
    
    def print_results(self, stats: Dict[str, Any]):
        """Pretty print benchmark results"""
        if "error" in stats:
            print(f"❌ Benchmark failed: {stats['error']}")
            return
        
        config = stats["benchmark_config"]
        first_token = stats["first_token_latency_ms"]
        total = stats["total_completion_ms"]
        slo = stats["slo_compliance"]
        
        print("📊 BENCHMARK RESULTS")
        print("=" * 50)
        print(f"Requests: {config['successful_requests']}/{config['n_requests']} " +
              f"({config['success_rate']:.1%} success)")
        print(f"Concurrency: {config['concurrency']}")
        print(f"Total time: {config['elapsed_s']}s")
        print()
        
        print("🚀 FIRST TOKEN LATENCY")
        print(f"  P50: {first_token['p50']}ms")
        print(f"  P95: {first_token['p95']}ms {'✅' if slo['first_token_slo_met'] else '❌'}")
        print(f"  P99: {first_token['p99']}ms")
        print(f"  Range: {first_token['min']}-{first_token['max']}ms")
        print()
        
        print("⏱️  TOTAL COMPLETION")
        print(f"  P50: {total['p50']}ms")
        print(f"  P95: {total['p95']}ms {'✅' if slo['total_slo_met'] else '❌'}")
        print(f"  P99: {total['p99']}ms") 
        print(f"  Range: {total['min']}-{total['max']}ms")
        print()
        
        print("🎯 SLO COMPLIANCE")
        print(f"  First Token P95: {slo['first_token_p95_actual']}ms / {slo['first_token_p95_target']} " +
              f"{'✅ PASS' if slo['first_token_slo_met'] else '❌ FAIL'}")
        print(f"  Total Response P95: {slo['total_p95_actual']}ms / {slo['total_p95_target']} " +
              f"{'✅ PASS' if slo['total_slo_met'] else '❌ FAIL'}")
        print()
        
        overall_pass = slo['first_token_slo_met'] and slo['total_slo_met']
        print(f"🏆 OVERALL: {'✅ PASS' if overall_pass else '❌ FAIL'}")
        
        return overall_pass


async def main():
    parser = argparse.ArgumentParser(
        description="Benchmark Cornell Course Navigator chat performance"
    )
    parser.add_argument("-n", "--requests", type=int, default=50,
                        help="Number of requests to send (default: 50)")
    parser.add_argument("-c", "--concurrency", type=int, default=1,
                        help="Concurrent requests (default: 1)")
    parser.add_argument("--url", type=str, default="http://localhost:8000",
                        help="Base URL of the service")
    parser.add_argument("--query", type=str, 
                        default="Plan 4 CS courses given I dislike theory, T/Th only.",
                        help="Chat query to benchmark")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="Request timeout in seconds")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    parser.add_argument("--ci", action="store_true",
                        help="CI mode: exit 1 if SLO not met")
    
    args = parser.parse_args()
    
    # Health check first
    try:
        async with httpx.AsyncClient() as client:
            health_response = await client.get(f"{args.url}/health", timeout=5.0)
            if health_response.status_code != 200:
                print(f"❌ Health check failed: HTTP {health_response.status_code}")
                sys.exit(1)
    except Exception as e:
        print(f"❌ Cannot reach service at {args.url}: {e}")
        sys.exit(1)
    
    # Run benchmark
    benchmark = ChatBenchmark(base_url=args.url, timeout_s=args.timeout)
    results = await benchmark.run_benchmark(
        n_requests=args.requests,
        concurrency=args.concurrency,
        query=args.query
    )
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        overall_pass = benchmark.print_results(results)
        
        if args.ci and not overall_pass:
            print("\n❌ Exiting with code 1 for CI (SLO not met)")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())