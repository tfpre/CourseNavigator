import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_BASE_URL = process.env.FASTAPI_BASE_URL || 'http://localhost:8000';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    
    // Validate algorithm parameter with default
    const requestData = {
      algorithm: body.algorithm || 'louvain'
    };

    // Validate algorithm value
    if (!['louvain', 'greedy_modularity'].includes(requestData.algorithm)) {
      throw new Error(`Invalid algorithm: ${requestData.algorithm}. Must be 'louvain' or 'greedy_modularity'`);
    }

    const response = await fetch(`${FASTAPI_BASE_URL}/api/communities`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestData),
    });

    if (!response.ok) {
      throw new Error(`FastAPI communities request failed: ${response.status}`);
    }

    const data = await response.json();
    
    return NextResponse.json(data);

  } catch (error) {
    console.error('Communities API error:', error);
    
    return NextResponse.json(
      {
        success: false,
        error: {
          code: 'COMMUNITIES_API_ERROR',
          message: error instanceof Error ? error.message : 'Unknown error occurred',
          details: { timestamp: new Date().toISOString() }
        }
      },
      { status: 500 }
    );
  }
}