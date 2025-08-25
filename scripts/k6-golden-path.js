/**
 * k6 Load Test - CourseNavigator Golden Path
 * 
 * Tests the deterministic demo flow with latency SLOs:
 * - P95 first-chunk < 500ms  
 * - P95 full-response < 3s
 * - Zero 5xx errors
 */

import http from 'k6/http';
import { check, fail } from 'k6';
import { Trend, Counter, Rate } from 'k6/metrics';

// Custom metrics for SLO tracking
const firstChunkLatency = new Trend('first_chunk_duration_ms');
const fullResponseLatency = new Trend('full_response_duration_ms');
const sseErrors = new Counter('sse_errors');
const chunkGaps = new Trend('sse_chunk_gap_ms');
const errorRate = new Rate('error_rate');

// Load test configuration
export const options = {
  vus: 10, // 10 virtual users
  duration: '2m',
  thresholds: {
    // SLO gates - fail build if not met
    'first_chunk_duration_ms': ['p(95)<500'], // P95 < 500ms
    'full_response_duration_ms': ['p(95)<3000'], // P95 < 3s
    'error_rate': ['rate<0.01'], // <1% error rate
    'sse_chunk_gap_ms': ['p(95)<1500'], // No gaps >1.5s
  },
};

// Demo profiles from dataset
const DEMO_PROFILES = {
  cs_sophomore: {
    student_id: "demo_cs_2027",
    major: "Computer Science",
    year: "sophomore", 
    completed_courses: ["CS 1110", "CS 2110", "MATH 1910", "MATH 1920", "PHYS 1112", "CS 2800"],
    current_courses: ["CS 3110", "CS 2850"],
    interests: ["Machine Learning", "Software Engineering", "Systems Programming"]
  }
};

// Golden path queries from demo script
const GOLDEN_PATH_QUERIES = [
  "What CS courses should I take next semester?",
  "I want both CS 4780 and CS 4820, what should I do?"
];

export default function () {
  const baseUrl = __ENV.API_URL || 'http://localhost:8000';
  
  // Randomly select a query from golden path
  const query = GOLDEN_PATH_QUERIES[Math.floor(Math.random() * GOLDEN_PATH_QUERIES.length)];
  const profile = DEMO_PROFILES.cs_sophomore;
  
  // Prepare chat request
  const payload = {
    message: query,
    student_profile: profile,
    context_preferences: {
      include_prerequisites: true,
      include_professor_ratings: true,
      include_difficulty_info: true,
      include_enrollment_data: true
    },
    stream: true,
    max_recommendations: 5
  };
  
  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
      'Cache-Control': 'no-cache'
    },
    timeout: '10s', // Total timeout
  };
  
  // Time the full request
  const startTime = Date.now();
  let firstChunkTime = null;
  let lastChunkTime = startTime;
  let chunkCount = 0;
  let hasError = false;
  
  // Make SSE request
  const response = http.post(`${baseUrl}/chat`, JSON.stringify(payload), params);
  
  // Basic response validation
  const isSuccess = check(response, {
    'status is 200': (r) => r.status === 200,
    'response has body': (r) => r.body && r.body.length > 0,
    'content-type is SSE': (r) => r.headers['Content-Type'] && 
      r.headers['Content-Type'].includes('text/event-stream'),
  });
  
  if (!isSuccess) {
    hasError = true;
    errorRate.add(1);
    sseErrors.add(1);
    return;
  }
  
  // Parse SSE stream for timing analysis
  if (response.body) {
    const events = response.body.split('\n\n');
    
    for (let i = 0; i < events.length; i++) {
      const event = events[i].trim();
      if (!event || !event.startsWith('data: ')) continue;
      
      try {
        const dataLine = event.split('\n').find(line => line.startsWith('data: '));
        if (!dataLine) continue;
        
        const eventData = dataLine.substring(6); // Remove 'data: '
        if (eventData === '{}') continue; // Skip empty close events
        
        const chunk = JSON.parse(eventData);
        
        // Track first meaningful chunk (first token)
        if (firstChunkTime === null && 
            (chunk.chunk_type === 'token' || chunk.chunk_type === 'context_info')) {
          firstChunkTime = Date.now();
          firstChunkLatency.add(firstChunkTime - startTime);
        }
        
        // Track inter-chunk timing gaps
        if (chunkCount > 0) {
          const now = Date.now();
          const gap = now - lastChunkTime;
          chunkGaps.add(gap);
          
          // Flag excessive gaps (SSE watchdog)
          if (gap > 1500) {
            console.warn(`SSE gap detected: ${gap}ms between chunks`);
          }
        }
        
        lastChunkTime = Date.now();
        chunkCount++;
        
        // Check for errors in stream
        if (chunk.chunk_type === 'error') {
          hasError = true;
          sseErrors.add(1);
          console.error(`SSE error chunk: ${chunk.content}`);
        }
        
        // Stream completed
        if (chunk.chunk_type === 'done') {
          const totalTime = Date.now() - startTime;
          fullResponseLatency.add(totalTime);
          
          // Validate streaming metadata
          check(chunk, {
            'has conversation_id': (c) => c.metadata && c.metadata.conversation_id,
            'has provenance_info': (c) => c.metadata && c.metadata.provenance_info,
            'professor_selections present': (c) => 
              c.metadata && c.metadata.provenance_info && 
              c.metadata.provenance_info.professor_selections,
          });
          
          break;
        }
      } catch (parseError) {
        console.error(`Failed to parse SSE chunk: ${parseError}`);
        hasError = true;
        sseErrors.add(1);
      }
    }
  }
  
  // Record error rate
  errorRate.add(hasError ? 1 : 0);
  
  // Validate we got meaningful chunks
  if (chunkCount === 0) {
    console.error('No SSE chunks received');
    sseErrors.add(1);
  }
  
  // Brief pause between requests
  const jitter = Math.random() * 1000; // 0-1s jitter
  const baseDelay = 1000; // 1s base
  const totalDelay = (baseDelay + jitter) / 1000;
  
  // k6 sleep expects seconds
  if (typeof sleep !== 'undefined') {
    sleep(totalDelay);
  }
}

// Summary function to display SLO results
export function handleSummary(data) {
  const firstChunkP95 = data.metrics.first_chunk_duration_ms.values['p(95)'];
  const fullResponseP95 = data.metrics.full_response_duration_ms.values['p(95)'];
  const errorRateValue = data.metrics.error_rate.values.rate;
  const chunkGapP95 = data.metrics.sse_chunk_gap_ms.values['p(95)'];
  
  console.log('\n📊 Golden Path SLO Results:');
  console.log(`   First chunk P95: ${firstChunkP95?.toFixed(1)}ms (target: <500ms)`);
  console.log(`   Full response P95: ${fullResponseP95?.toFixed(1)}ms (target: <3000ms)`);  
  console.log(`   Error rate: ${(errorRateValue * 100)?.toFixed(2)}% (target: <1%)`);
  console.log(`   Max chunk gap P95: ${chunkGapP95?.toFixed(1)}ms (target: <1500ms)`);
  
  // SLO compliance check
  const slosMet = [
    firstChunkP95 < 500,
    fullResponseP95 < 3000, 
    errorRateValue < 0.01,
    chunkGapP95 < 1500
  ];
  
  const overallPass = slosMet.every(Boolean);
  console.log(`\n🎯 SLO Compliance: ${overallPass ? '✅ PASS' : '❌ FAIL'}`);
  
  if (!overallPass) {
    console.log('⚠️  Demo readiness at risk - investigate performance bottlenecks');
  }
  
  return {
    'stdout': JSON.stringify(data, null, 2),
  };
}