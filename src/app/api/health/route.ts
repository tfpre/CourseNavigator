import { NextRequest, NextResponse } from 'next/server';
import { HealthResponse } from '../../../../types/api-types';

const FASTAPI_BASE_URL = process.env.FASTAPI_BASE_URL || 'http://localhost:8000';

export async function GET(request: NextRequest) {
  try {
    const response = await fetch(`${FASTAPI_BASE_URL}/health`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`FastAPI health check failed: ${response.status}`);
    }

    const data: HealthResponse = await response.json();
    
    return NextResponse.json({
      status: 'ok',
      fastapi_gateway: response.ok,
      gateway_health: data,
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error('Health check failed:', error);
    
    return NextResponse.json(
      {
        status: 'error',
        fastapi_gateway: false,
        error: error instanceof Error ? error.message : 'Unknown error',
        timestamp: new Date().toISOString(),
      },
      { status: 503 }
    );
  }
}