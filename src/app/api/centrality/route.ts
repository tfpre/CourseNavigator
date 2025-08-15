import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_BASE_URL = process.env.FASTAPI_BASE_URL || 'http://localhost:8000';

export async function POST(request: NextRequest) {
  try {
    // Handle empty request bodies gracefully
    let body = {};
    try {
      const rawBody = await request.text();
      if (rawBody.trim()) {
        body = JSON.parse(rawBody);
      }
    } catch (parseError) {
      console.warn('Failed to parse request body, using defaults:', parseError);
      body = {};
    }
    
    // Validate required parameters with defaults matching FastAPI model
    const requestData = {
      top_n: (body as any).top_n || 20,
      damping_factor: (body as any).damping_factor || 0.85,
      min_betweenness: (body as any).min_betweenness || 0.01,
      min_in_degree: (body as any).min_in_degree || 2
    };

    const response = await fetch(`${FASTAPI_BASE_URL}/api/centrality`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestData),
    });

    if (!response.ok) {
      throw new Error(`FastAPI centrality request failed: ${response.status}`);
    }

    const data = await response.json();
    
    return NextResponse.json(data);

  } catch (error) {
    console.error('Centrality API error:', error);
    
    return NextResponse.json(
      {
        success: false,
        error: {
          code: 'CENTRALITY_API_ERROR',
          message: error instanceof Error ? error.message : 'Unknown error occurred',
          details: { timestamp: new Date().toISOString() }
        }
      },
      { status: 500 }
    );
  }
}

// GET endpoint following REST best practices for read operations
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    
    // Extract query parameters with defaults
    const requestData = {
      top_n: parseInt(searchParams.get('top_n') || '20'),
      damping_factor: parseFloat(searchParams.get('damping_factor') || '0.85'),
      min_betweenness: parseFloat(searchParams.get('min_betweenness') || '0.01'),
      min_in_degree: parseInt(searchParams.get('min_in_degree') || '2')
    };

    const response = await fetch(`${FASTAPI_BASE_URL}/api/centrality`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestData),
    });

    if (!response.ok) {
      throw new Error(`FastAPI centrality request failed: ${response.status}`);
    }

    const data = await response.json();
    
    return NextResponse.json(data);

  } catch (error) {
    console.error('Centrality API error:', error);
    
    return NextResponse.json(
      {
        success: false,
        error: {
          code: 'CENTRALITY_API_ERROR',
          message: error instanceof Error ? error.message : 'Unknown error occurred',
          details: { timestamp: new Date().toISOString() }
        }
      },
      { status: 500 }
    );
  }
}