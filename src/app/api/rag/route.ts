import { NextRequest, NextResponse } from 'next/server';
import { RAGRequest, RAGResponse } from '../../../../types/api-types';

const FASTAPI_BASE_URL = process.env.FASTAPI_BASE_URL || 'http://localhost:8000';

export async function POST(request: NextRequest) {
  try {
    const body: RAGRequest = await request.json();

    // Validate required fields
    if (!body.query || body.query.trim().length === 0) {
      return NextResponse.json(
        {
          success: false,
          error: {
            code: 'VALIDATION_ERROR',
            message: 'Query is required and cannot be empty',
          }
        } as RAGResponse,
        { status: 400 }
      );
    }

    // Forward request to FastAPI gateway
    const response = await fetch(`${FASTAPI_BASE_URL}/api/rag_with_graph`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    const data: RAGResponse = await response.json();

    // Return the response with appropriate status code
    const status = data.success ? 200 : (response.status || 500);
    return NextResponse.json(data, { status });

  } catch (error) {
    console.error('RAG request failed:', error);
    
    return NextResponse.json(
      {
        success: false,
        error: {
          code: 'REQUEST_FAILED',
          message: 'Failed to process RAG request',
          details: { error: error instanceof Error ? error.message : 'Unknown error' }
        }
      } as RAGResponse,
      { status: 500 }
    );
  }
}