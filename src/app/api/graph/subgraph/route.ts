import { NextRequest, NextResponse } from 'next/server';

interface SubgraphRequest {
  max_nodes?: number;
  max_edges?: number;
  include_centrality?: boolean;
  include_communities?: boolean;
  filter_by_subject?: string[];
}

export async function POST(request: NextRequest) {
  try {
    // Handle empty request bodies gracefully
    let body: SubgraphRequest = {};
    try {
      const rawBody = await request.text();
      if (rawBody.trim()) {
        body = JSON.parse(rawBody);
      }
    } catch (parseError) {
      console.warn('Failed to parse request body, using defaults:', parseError);
      body = {};
    }
    
    // Validate request parameters
    const requestData = {
      max_nodes: Math.min(Math.max(body.max_nodes || 50, 5), 200),
      max_edges: Math.min(Math.max(body.max_edges || 100, 10), 500),
      include_centrality: body.include_centrality !== false,
      include_communities: body.include_communities !== false,
      filter_by_subject: body.filter_by_subject || null
    };

    // Get gateway URL from environment (consistent with other APIs)
    const gatewayUrl = process.env.FASTAPI_BASE_URL || 'http://localhost:8000';
    
    // Forward request to Python gateway
    const response = await fetch(`${gatewayUrl}/api/graph/subgraph`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestData),
    });

    if (!response.ok) {
      console.error(`Gateway responded with status ${response.status}`);
      return NextResponse.json(
        { 
          success: false, 
          error: { 
            code: 'GATEWAY_ERROR',
            message: 'Failed to fetch subgraph data from gateway',
            details: { status: response.status }
          }
        },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);

  } catch (error) {
    console.error('Subgraph API error:', error);
    
    return NextResponse.json(
      {
        success: false,
        error: {
          code: 'API_ERROR',
          message: 'Failed to process subgraph request',
          details: { error: error instanceof Error ? error.message : 'Unknown error' }
        }
      },
      { status: 500 }
    );
  }
}

export async function GET() {
  // Default GET request for basic subgraph data
  return POST(new NextRequest('http://localhost:3000/api/graph/subgraph', {
    method: 'POST',
    body: JSON.stringify({
      max_nodes: 50,
      max_edges: 100,
      include_centrality: true,
      include_communities: true
    }),
    headers: { 'Content-Type': 'application/json' }
  }));
}