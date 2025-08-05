import { useState, useCallback, useEffect } from 'react';

export interface APIState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

export interface APIHookReturn<T> extends APIState<T> {
  execute: () => Promise<void>;
  reset: () => void;
}

interface APIResponse {
  success: boolean;
  data?: any;
  error?: {
    message: string;
    code?: string;
    details?: any;
  };
}

/**
 * Reusable hook for API calls with consistent error handling and loading states
 * 
 * @param apiCall - Function that makes the API call and returns the response
 * @param options - Configuration options
 */
export function useAPI<T>(
  apiCall: () => Promise<Response>,
  options: {
    executeOnMount?: boolean;
    transform?: (data: any) => T;
  } = {}
): APIHookReturn<T> {
  const { executeOnMount = false, transform } = options;
  
  const [state, setState] = useState<APIState<T>>({
    data: null,
    loading: false,
    error: null,
  });

  const execute = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));
    
    try {
      const response = await apiCall();
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const result: APIResponse = await response.json();
      
      if (result.success) {
        const transformedData = transform ? transform(result.data) : result.data;
        setState({
          data: transformedData,
          loading: false,
          error: null,
        });
      } else {
        setState({
          data: null,
          loading: false,
          error: result.error?.message || 'API call failed',
        });
      }
    } catch (err) {
      setState({
        data: null,
        loading: false,
        error: err instanceof Error ? err.message : 'An unknown error occurred',
      });
      console.error('API call failed:', err);
    }
  }, [apiCall, transform]);

  const reset = useCallback(() => {
    setState({
      data: null,
      loading: false,
      error: null,
    });
  }, []);

  // Execute on mount if requested
  useEffect(() => {
    if (executeOnMount) {
      execute();
    }
  }, [executeOnMount]); // ✅ Remove 'execute' dependency to prevent infinite loop

  return {
    ...state,
    execute,
    reset,
  };
}

/**
 * Specialized hook for centrality data API calls
 */
export function useCentralityAPI(params: {
  top_n?: number;
  damping_factor?: number;
  min_betweenness?: number;
  min_in_degree?: number;
} = {}) {
  const defaultParams = {
    top_n: 15,
    damping_factor: 0.85,
    min_betweenness: 0.01,
    min_in_degree: 2,
    ...params,
  };

  return useAPI(
    () => fetch('/api/centrality', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(defaultParams),
    }),
    { executeOnMount: true }
  );
}