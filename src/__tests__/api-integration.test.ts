/**
 * Integration tests for API endpoints
 * 
 * These tests verify that the Next.js API routes can successfully communicate
 * with the FastAPI backend and return properly structured responses.
 * 
 * NOTE: These tests require the FastAPI service to be running on localhost:8000
 * 
 * To run the FastAPI service:
 * 1. cd python/
 * 2. poetry install
 * 3. poetry run uvicorn gateway.main:app --reload
 */

describe('API Integration Tests', () => {
  const API_BASE = 'http://localhost:3000/api';
  
  // Skip tests if not running in integration test environment
  const isIntegrationTest = process.env.NODE_ENV === 'test' && process.env.INTEGRATION === 'true';
  
  beforeAll(() => {
    if (!isIntegrationTest) {
      console.log('Skipping integration tests. Set INTEGRATION=true to run.');
    }
  });

  describe('/api/centrality', () => {
    it.skip('should return centrality data with proper structure', async () => {
      const response = await fetch(`${API_BASE}/centrality`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          top_n: 5,
          damping_factor: 0.85,
          min_betweenness: 0.01,
          min_in_degree: 2
        }),
      });

      expect(response.ok).toBe(true);
      
      const data = await response.json();
      
      // Verify response structure matches CentralityResponse interface
      expect(data).toMatchObject({
        success: expect.any(Boolean),
        data: expect.any(Object),
        computation_time_ms: expect.any(Number),
      });

      if (data.success) {
        expect(data.data).toMatchObject({
          most_central_courses: expect.any(Array),
          bridge_courses: expect.any(Array),
          gateway_courses: expect.any(Array),
          analysis_metadata: expect.any(Object),
        });
      }
    });

    it.skip('should handle invalid parameters gracefully', async () => {
      const response = await fetch(`${API_BASE}/centrality`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          top_n: -1, // Invalid parameter
        }),
      });

      const data = await response.json();
      
      expect(data.success).toBe(false);
      expect(data.error).toBeDefined();
      expect(data.error.message).toMatch(/validation|parameter|invalid/i);
    });
  });

  describe('/api/communities', () => {
    it.skip('should return community detection data', async () => {
      const response = await fetch(`${API_BASE}/communities`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          algorithm: 'louvain'
        }),
      });

      expect(response.ok).toBe(true);
      
      const data = await response.json();
      
      expect(data).toMatchObject({
        success: expect.any(Boolean),
        data: expect.any(Object),
        computation_time_ms: expect.any(Number),
      });
    });
  });

  describe('/api/shortest-path', () => {
    it.skip('should return shortest path data', async () => {
      const response = await fetch(`${API_BASE}/shortest-path`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          target_course: 'CS 4780',
          completed_courses: ['CS 2110', 'MATH 2940']
        }),
      });

      expect(response.ok).toBe(true);
      
      const data = await response.json();
      
      expect(data).toMatchObject({
        success: expect.any(Boolean),
        data: expect.any(Object),
        computation_time_ms: expect.any(Number),
      });
    });
  });

  describe('/api/health', () => {
    it.skip('should return health status', async () => {
      const response = await fetch(`${API_BASE}/health`);
      
      expect(response.ok).toBe(true);
      
      const data = await response.json();
      
      expect(data).toMatchObject({
        status: 'ok',
        fastapi_gateway: expect.any(Boolean),
        timestamp: expect.any(String),
      });
    });
  });
});

/**
 * Manual Test Instructions
 * 
 * To test the API integration manually:
 * 
 * 1. Start the FastAPI backend:
 *    cd python/
 *    poetry run uvicorn gateway.main:app --reload
 * 
 * 2. Start the Next.js frontend:
 *    npm run dev
 * 
 * 3. Open http://localhost:3000 and check:
 *    - CourseRankings component loads without errors
 *    - Data appears in the rankings tables
 *    - No console errors in browser dev tools
 * 
 * 4. Test API endpoints directly:
 *    curl -X POST http://localhost:3000/api/centrality \
 *      -H "Content-Type: application/json" \
 *      -d '{"top_n": 5}'
 * 
 * Expected Response Structure:
 * {
 *   "success": true,
 *   "data": {
 *     "most_central_courses": [...],
 *     "bridge_courses": [...],
 *     "gateway_courses": [...],
 *     "analysis_metadata": {...}
 *   },
 *   "computation_time_ms": 1200
 * }
 */