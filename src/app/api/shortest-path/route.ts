import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_BASE_URL = process.env.FASTAPI_BASE_URL || 'http://localhost:8000';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    
    // Validate required parameters
    if (!body.target_course) {
      throw new Error('target_course is required');
    }

    const requestData = {
      target_course: body.target_course,
      completed_courses: body.completed_courses || []
    };

    const response = await fetch(`${FASTAPI_BASE_URL}/api/shortest_path`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestData),
    });

    if (!response.ok) {
      throw new Error(`FastAPI shortest path request failed: ${response.status}`);
    }

    const data = await response.json();
    
    return NextResponse.json(data);

  } catch (error) {
    console.error('Shortest path API error:', error);
    
    return NextResponse.json(
      {
        success: false,
        error: {
          code: 'SHORTEST_PATH_API_ERROR',
          message: error instanceof Error ? error.message : 'Unknown error occurred',
          details: { timestamp: new Date().toISOString() }
        }
      },
      { status: 500 }
    );
  }
}