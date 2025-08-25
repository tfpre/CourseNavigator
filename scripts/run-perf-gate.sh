#!/bin/bash
set -euo pipefail

# CourseNavigator Performance Gate
# Validates P95 latency SLOs for demo readiness

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Configuration
API_URL="${API_URL:-http://localhost:8000}"
K6_SCRIPT="$SCRIPT_DIR/k6-golden-path.js"
RESULTS_DIR="$PROJECT_ROOT/perf-results"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

echo "🚀 CourseNavigator Performance Gate - $TIMESTAMP"
echo "   API URL: $API_URL"
echo "   Results: $RESULTS_DIR"

# Ensure results directory exists
mkdir -p "$RESULTS_DIR"

# Check if k6 is installed
if ! command -v k6 &> /dev/null; then
    echo "❌ k6 not installed. Install with:"
    echo "   # macOS: brew install k6"
    echo "   # Linux: sudo apt install k6"
    echo "   # Windows: choco install k6" 
    exit 1
fi

# Check if API is running
echo "📡 Checking API health..."
if ! curl -f -s "$API_URL/health" > /dev/null; then
    echo "❌ API not responding at $API_URL"
    echo "   Start with: docker-compose up -d"
    exit 1
fi
echo "✅ API health check passed"

# Warm up the system (prevent cold start bias)
echo "🔥 Warming up system..."
curl -s -X POST "$API_URL/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "warmup",
    "student_profile": {
      "student_id": "warmup",
      "major": "Computer Science",
      "year": "sophomore",
      "completed_courses": ["CS 1110"],
      "current_courses": [],
      "interests": ["Machine Learning"]
    },
    "stream": false
  }' > /dev/null || echo "⚠️  Warmup failed (non-fatal)"

echo "⏱️  Starting load test..."

# Run k6 test with results output
export API_URL
k6 run \
  --out json="$RESULTS_DIR/results-$TIMESTAMP.json" \
  --summary-export="$RESULTS_DIR/summary-$TIMESTAMP.json" \
  "$K6_SCRIPT" | tee "$RESULTS_DIR/output-$TIMESTAMP.log"

# Extract key metrics from results
RESULT_JSON="$RESULTS_DIR/results-$TIMESTAMP.json"
if [[ -f "$RESULT_JSON" ]]; then
    echo ""
    echo "📊 Key Metrics Summary:"
    
    # Parse P95 latencies from k6 output
    FIRST_CHUNK_P95=$(grep "first_chunk_duration_ms.*p(95)" "$RESULTS_DIR/output-$TIMESTAMP.log" | grep -o '[0-9.]\+' | head -1 || echo "N/A")
    FULL_RESPONSE_P95=$(grep "full_response_duration_ms.*p(95)" "$RESULTS_DIR/output-$TIMESTAMP.log" | grep -o '[0-9.]\+' | head -1 || echo "N/A")
    ERROR_RATE=$(grep "error_rate" "$RESULTS_DIR/output-$TIMESTAMP.log" | grep -o '[0-9.]\+%' | head -1 || echo "N/A")
    
    echo "   First Token P95: ${FIRST_CHUNK_P95}ms (target: <500ms)"
    echo "   Full Response P95: ${FULL_RESPONSE_P95}ms (target: <3000ms)"
    echo "   Error Rate: ${ERROR_RATE} (target: <1%)"
    
    # Check if thresholds passed
    if grep -q "✓" "$RESULTS_DIR/output-$TIMESTAMP.log" && ! grep -q "✗" "$RESULTS_DIR/output-$TIMESTAMP.log"; then
        echo ""
        echo "🎉 PERFORMANCE GATE: PASSED"
        echo "   Demo is ready from latency perspective"
        exit 0
    else
        echo ""
        echo "❌ PERFORMANCE GATE: FAILED"  
        echo "   Address performance issues before demo"
        exit 1
    fi
else
    echo "⚠️  Could not find results file for analysis"
    exit 1
fi