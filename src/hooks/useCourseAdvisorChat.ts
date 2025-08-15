// Custom hook for Cornell Course Advisor Chat with SSE streaming
// Implements friend's specifications: <500ms perceived latency, conversation state management
// Enhanced with chunk-safe SSE parsing per newfix.md recommendations

import { useState, useCallback, useRef, useEffect } from 'react';

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  metadata?: Record<string, any>;
}

export interface StudentProfile {
  student_id: string;
  major?: string;
  year?: 'freshman' | 'sophomore' | 'junior' | 'senior' | 'graduate';
  completed_courses: string[];
  current_courses: string[];
  interests: string[];
  gpa?: number;
}

export interface ChatStreamChunk {
  chunk_id: number;
  content: string;
  chunk_type: 'token' | 'course_highlight' | 'context_info' | 'thinking' | 'error' | 'done';
  metadata: Record<string, any>;
  timestamp: string;
}

export interface UseCourseAdvisorChatOptions {
  initialProfile?: StudentProfile;
  gatewayUrl?: string;
  onCourseRecommendation?: (courseCode: string, reasoning: string) => void;
  onConversationUpdate?: (conversationId: string) => void;
}

export interface UseCourseAdvisorChatReturn {
  // State
  messages: ChatMessage[];
  isStreaming: boolean;
  streamingContent: string;
  contextInfo: string;
  error: string | null;
  conversationId: string | null;
  recommendedCourses: string[];
  
  // Actions
  sendMessage: (message: string) => Promise<void>;
  clearChat: () => void;
  updateProfile: (profile: Partial<StudentProfile>) => void;
  
  // Configuration
  studentProfile: StudentProfile;
}

export const useCourseAdvisorChat = (options: UseCourseAdvisorChatOptions = {}): UseCourseAdvisorChatReturn => {
  const {
    initialProfile,
    gatewayUrl = '/api/chat',
    onCourseRecommendation,
    onConversationUpdate
  } = options;

  // Core state management
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [contextInfo, setContextInfo] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [recommendedCourses, setRecommendedCourses] = useState<string[]>([]);
  
  // Student profile with smart defaults
  const [studentProfile, setStudentProfile] = useState<StudentProfile>(
    initialProfile || {
      student_id: `demo_student_${Date.now()}`,
      major: 'Computer Science',
      year: 'sophomore',
      completed_courses: ['CS 1110', 'MATH 1910'],
      current_courses: ['CS 2110'],
      interests: ['Machine Learning', 'Software Engineering']
    }
  );

  // Refs for cleanup and abort control
  const abortControllerRef = useRef<AbortController | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // Update student profile
  const updateProfile = useCallback((profileUpdate: Partial<StudentProfile>) => {
    setStudentProfile(prev => ({
      ...prev,
      ...profileUpdate
    }));
  }, []);

  // Clear chat history
  const clearChat = useCallback(() => {
    setMessages([]);
    setStreamingContent('');
    setContextInfo('');
    setError(null);
    setRecommendedCourses([]);
    setConversationId(null);
    
    // Abort any ongoing requests
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  }, []);

  // Send message with SSE streaming
  const sendMessage = useCallback(async (message: string) => {
    if (!message.trim() || isStreaming) return;

    // Reset state
    setError(null);
    setContextInfo('');
    setStreamingContent('');
    setIsStreaming(true);

    // Create abort controller for this request
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    // Add user message immediately
    const userMessage: ChatMessage = {
      role: 'user',
      content: message.trim(),
      timestamp: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMessage]);

    try {
      // Prepare chat request following FastAPI model structure
      const chatRequest = {
        message: message.trim(),
        conversation_id: conversationId,
        student_profile: studentProfile,
        context_preferences: {
          include_prerequisites: true,
          include_professor_ratings: true,
          include_difficulty_info: true,
          include_enrollment_data: true,
          include_similar_courses: true
        },
        stream: true,
        max_recommendations: 5
      };

      // Make streaming request
      const response = await fetch(gatewayUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          'Cache-Control': 'no-cache'
        },
        body: JSON.stringify(chatRequest),
        signal: abortController.signal
      });

      if (!response.ok) {
        throw new Error(`Chat request failed with status ${response.status}: ${response.statusText}`);
      }

      if (!response.body) {
        throw new Error('No response body received from chat endpoint');
      }

      // Process Server-Sent Events stream with enhanced chunk-safe parser
      await processSSEStream(response.body, {
        onChunk: (chunk: ChatStreamChunk) => {
          handleStreamChunk(chunk);
        },
        onError: (error: Error) => {
          setError(`Stream processing error: ${error.message}`);
          setIsStreaming(false);
        },
        onHeartbeat: () => {
          // Connection still alive - could show subtle indicator
        },
        signal: abortController.signal
      });

    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        // Request was aborted - this is expected during cleanup
        return;
      }
      
      console.error('Chat request failed:', error);
      setError(error instanceof Error ? error.message : 'Failed to send message');
      setIsStreaming(false);
      setStreamingContent('');
      setContextInfo('');
    }
  }, [isStreaming, conversationId, studentProfile, gatewayUrl]);

  // Handle individual stream chunks
  const handleStreamChunk = useCallback((chunk: ChatStreamChunk) => {
    switch (chunk.chunk_type) {
      case 'context_info':
        if (chunk.metadata.status) {
          setContextInfo(`${chunk.metadata.status}...`);
        }
        break;

      case 'token':
        setStreamingContent(prev => prev + chunk.content);
        break;

      case 'course_highlight':
        if (chunk.metadata.course_code) {
          setRecommendedCourses(prev => [...Array.from(new Set([...prev, chunk.metadata.course_code]))]);
          
          // Trigger callback for course recommendation
          if (onCourseRecommendation) {
            onCourseRecommendation(
              chunk.metadata.course_code,
              chunk.metadata.reasoning || 'Recommended based on your academic profile'
            );
          }
        }
        break;

      case 'error':
        setError(chunk.content || 'An error occurred during processing');
        setIsStreaming(false);
        break;

      case 'done':
        // Stream completed successfully
        const finalContent = streamingContent;
        
        const assistantMessage: ChatMessage = {
          role: 'assistant',
          content: finalContent,
          timestamp: new Date().toISOString(),
          metadata: chunk.metadata
        };

        setMessages(prev => [...prev, assistantMessage]);
        
        // Update conversation state
        if (chunk.metadata.conversation_id) {
          const newConversationId = chunk.metadata.conversation_id;
          setConversationId(newConversationId);
          
          if (onConversationUpdate) {
            onConversationUpdate(newConversationId);
          }
        }
        
        // Update recommended courses from metadata
        if (chunk.metadata.recommended_courses) {
          const courses = chunk.metadata.recommended_courses.map((rec: any) => 
            typeof rec === 'string' ? rec : rec.course_code
          );
          setRecommendedCourses(prev => [...Array.from(new Set([...prev, ...courses]))]);
        }
        
        // Reset streaming state
        setContextInfo('');
        setStreamingContent('');
        setIsStreaming(false);
        break;

      default:
        console.warn('Unknown chunk type:', chunk.chunk_type);
    }
  }, [streamingContent, onCourseRecommendation, onConversationUpdate]);

  return {
    // State
    messages,
    isStreaming,
    streamingContent,
    contextInfo,
    error,
    conversationId,
    recommendedCourses,
    studentProfile,
    
    // Actions
    sendMessage,
    clearChat,
    updateProfile
  };
};

// Enhanced SSE stream processor with chunk-safe parsing
// Based on newfix.md recommendations for robust TCP chunk handling
async function processSSEStream(
  body: ReadableStream<Uint8Array>,
  handlers: {
    onChunk: (chunk: ChatStreamChunk) => void;
    onError: (error: Error) => void;
    onHeartbeat?: () => void;
    signal?: AbortSignal;
  }
) {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";
  let warmingUpShown = false;

  try {
    // Show warming up indicator after 600ms if no first token
    const warmUpTimer = setTimeout(() => {
      if (!warmingUpShown) {
        // Could show subtle "warming up" shimmer here
        warmingUpShown = true;
      }
    }, 600);

    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;

      // Check if request was aborted
      if (handlers.signal?.aborted) {
        break;
      }

      buf += decoder.decode(value, { stream: true });

      let idx: number;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const frame = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        
        // Parse SSE fields - supports: event: <name>\n data: <payload>
        let event = "message";
        let data = "";
        
        for (const line of frame.split("\n")) {
          if (line.startsWith("event:")) {
            event = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            data += line.slice(5).trim();
          }
        }
        
        // Handle heartbeat pings (every 10s from server)
        if (event === "ping") {
          if (handlers.onHeartbeat) {
            handlers.onHeartbeat();
          }
          continue; // heartbeat - keep connection alive
        }
        
        // Handle stream termination
        if (data === "[DONE]") {
          clearTimeout(warmUpTimer);
          return;
        }
        
        // Skip empty data
        if (!data || data === "{}") {
          continue;
        }

        try {
          // Parse chat chunk data
          const chunk: ChatStreamChunk = JSON.parse(data);
          
          // Clear warming up timer on first real chunk
          if (!warmingUpShown) {
            clearTimeout(warmUpTimer);
            warmingUpShown = true;
          }
          
          handlers.onChunk(chunk);
          
          // If this is a done chunk, we can break early
          if (chunk.chunk_type === 'done') {
            clearTimeout(warmUpTimer);
            break;
          }
          
        } catch (parseError) {
          console.error('Failed to parse SSE chunk:', parseError, 'Raw data:', data);
          // Don't throw - continue processing other chunks for resilience
        }
      }
    }
    
    // Flush any last partial frame if needed (optional no-op here)
    clearTimeout(warmUpTimer);
    
  } catch (error) {
    if (error instanceof Error && error.name !== 'AbortError') {
      handlers.onError(error);
    }
  } finally {
    reader.releaseLock();
  }
}

export default useCourseAdvisorChat;