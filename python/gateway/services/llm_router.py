# LLM Router - First-Token Deadline with Graceful Fallback
# Implements expert friend's recommendation: 200ms deadline → OpenAI fallback
# Updated with Llama 3.1-8B-Instruct for better quality per ground truth principles

import asyncio
from typing import AsyncIterator, Optional, Dict, Any
import httpx
import json
import time
import logging
from contextlib import suppress
import os

logger = logging.getLogger(__name__)

class LLMRouter:
    """
    LLM Router with race condition handling between local vLLM and OpenAI fallback.
    
    Key Features:
    - 200ms first-token deadline for local LLM
    - Clean task cancellation if local times out  
    - Graceful fallback to OpenAI API
    - Proper provider attribution for monitoring
    - Persistent HTTP clients for performance
    - Llama 3.1-8B-Instruct for better quality
    """
    
    def __init__(
        self,
        vllm_base: str = None,
        openai_base: str = "https://api.openai.com/v1",
        openai_key: Optional[str] = None,
        model_local: str = "meta-llama/Llama-3.1-8B-Instruct",  # UPDATED: Better quality per ground truth
        model_fallback: str = "gpt-4o-mini",
        first_token_deadline_ms: int = 200,
        request_timeout_s: float = 8.0,
    ):
        # Use environment variable for vLLM base to support Docker routing
        self.vllm_base = (vllm_base or os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")).rstrip("/")
        self.openai_base = openai_base.rstrip("/")
        self.openai_key = openai_key
        self.model_local = model_local
        self.model_fallback = model_fallback
        self.first_token_deadline_ms = first_token_deadline_ms
        self.request_timeout_s = request_timeout_s
        
        # Persistent HTTP clients for performance (newfix.md recommendation)
        self.client_local = httpx.AsyncClient(timeout=request_timeout_s)
        self.client_openai = httpx.AsyncClient(
            timeout=request_timeout_s,
            headers={"Authorization": f"Bearer {openai_key}"} if openai_key else {}
        )

    async def _stream_openai_compatible(
        self, client: httpx.AsyncClient, base: str, model: str, headers: Dict[str, str], prompt: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream tokens from OpenAI-compatible API (vLLM or OpenAI)"""
        url = f"{base}/chat/completions"
        payload = {
            "model": model,
            "stream": True,
            "temperature": 0.3,
            "max_tokens": 512,  # Increased for better responses with Llama 3.1
            "messages": [
                {"role": "user", "content": prompt}
            ],
        }
        
        async with client.stream("POST", url, headers=headers, json=payload) as r:
            async for line in r.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                if line.strip() == "data: [DONE]":
                    yield {"event": "done"}
                    return
                try:
                    obj = json.loads(line[5:])  # Remove "data: " prefix
                except Exception:
                    continue
                
                # Extract token from OpenAI-compatible response
                delta = obj.get("choices", [{}])[0].get("delta", {}).get("content")
                if delta:
                    yield {"event": "token", "text": delta}

    async def _local_stream(self, prompt: str) -> AsyncIterator[Dict[str, Any]]:
        """Stream from local vLLM instance"""
        headers = {"Content-Type": "application/json"}
        try:
            async for evt in self._stream_openai_compatible(
                self.client_local, self.vllm_base, self.model_local, headers, prompt
            ):
                yield {"provider": "local-vllm", **evt}
        except Exception as e:
            logger.exception(f"Local vLLM stream failed: {e}")
            yield {"provider": "local-vllm", "event": "error", "error": str(e)}

    async def _fallback_stream(self, prompt: str) -> AsyncIterator[Dict[str, Any]]:
        """Stream from OpenAI API fallback"""
        if not self.openai_key:
            yield {"provider": "fallback-none", "event": "error", "error": "no_openai_key"}
            return
            
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.openai_key}",
        }
        
        try:
            async for evt in self._stream_openai_compatible(
                self.client_openai, self.openai_base, self.model_fallback, headers, prompt
            ):
                yield {"provider": "openai-fallback", **evt}
        except Exception as e:
            logger.exception(f"OpenAI fallback stream failed: {e}")
            yield {"provider": "openai-fallback", "event": "error", "error": str(e)}

    async def stream_with_deadline(self, prompt: str) -> AsyncIterator[Dict[str, Any]]:
        """
        Race the first token from local vLLM vs 200ms deadline.
        If local doesn't produce token in time, cancel and stream from fallback.
        
        This prevents demo hangs while preserving local-first architecture.
        Enhanced with proper resource cleanup and cancellation.
        """
        local_gen = None
        local_task = None
        fallback_started = False
        t0 = time.perf_counter()
        provider_used = "unknown"

        try:
            # Start local stream and create task for first token
            local_gen = self._local_stream(prompt)
            local_task = asyncio.create_task(local_gen.__anext__())
            
            try:
                # Race first token against deadline
                first_evt = await asyncio.wait_for(
                    local_task, timeout=self.first_token_deadline_ms / 1000
                )
                
                first_token_ms = (time.perf_counter() - t0) * 1000
                logger.info(f"Local LLM first token in {first_token_ms:.1f}ms")
                provider_used = "local-vllm"
                
                if first_evt.get("event") == "token":
                    # Local LLM succeeded - continue with local stream
                    yield {**first_evt, "provider": provider_used}
                    async for evt in local_gen:
                        yield {**evt, "provider": provider_used}
                    return
                else:
                    # Local returned done/error before token → fallback
                    logger.warning("Local LLM returned non-token first event, falling back")
                    fallback_started = True
                    
            except asyncio.TimeoutError:
                # Local missed first-token SLA → cancel and fallback
                local_task.cancel()
                with suppress(Exception):
                    await local_task
                fallback_deadline_ms = (time.perf_counter() - t0) * 1000
                logger.warning(f"Local LLM missed {self.first_token_deadline_ms}ms deadline ({fallback_deadline_ms:.1f}ms actual), falling back")
                fallback_started = True

            if fallback_started:
                # Properly close local generator if it was started
                if local_gen:
                    with suppress(Exception):
                        await local_gen.aclose()
                
                # Stream from OpenAI fallback
                provider_used = "openai-fallback"
                async for evt in self._fallback_stream(prompt):
                    yield {**evt, "provider": provider_used}
                    
        except Exception as e:
            logger.exception(f"LLM router failed completely: {e}")
            # Clean up resources
            if local_task and not local_task.done():
                local_task.cancel()
                with suppress(Exception):
                    await local_task
            if local_gen:
                with suppress(Exception):
                    await local_gen.aclose()
            yield {"provider": provider_used, "event": "error", "error": str(e)}

    async def health_check(self) -> Dict[str, Any]:
        """Check health of local vLLM and fallback connectivity"""
        health = {
            "local_vllm": {"status": "unknown", "latency_ms": None, "model": self.model_local},
            "openai_fallback": {"status": "unknown", "available": bool(self.openai_key), "model": self.model_fallback}
        }
        
        # Check local vLLM with persistent client
        try:
            t0 = time.perf_counter()
            response = await self.client_local.get(f"{self.vllm_base}/v1/models")
            latency = (time.perf_counter() - t0) * 1000
            if response.status_code == 200:
                models = response.json().get("data", [])
                available_models = [m.get("id") for m in models]
                health["local_vllm"] = {
                    "status": "healthy", 
                    "latency_ms": round(latency, 1),
                    "model": self.model_local,
                    "available_models": available_models
                }
            else:
                health["local_vllm"] = {"status": "error", "latency_ms": round(latency, 1), "model": self.model_local}
        except Exception as e:
            health["local_vllm"] = {"status": "error", "error": str(e), "model": self.model_local}
        
        # Check OpenAI connectivity with persistent client
        if self.openai_key:
            try:
                t0 = time.perf_counter()
                response = await self.client_openai.get(f"{self.openai_base}/models")
                latency = (time.perf_counter() - t0) * 1000
                if response.status_code == 200:
                    health["openai_fallback"]["status"] = "healthy"
                    health["openai_fallback"]["latency_ms"] = round(latency, 1)
                else:
                    health["openai_fallback"]["status"] = "error"
                    health["openai_fallback"]["latency_ms"] = round(latency, 1)
            except Exception as e:
                health["openai_fallback"]["status"] = "error"
                health["openai_fallback"]["error"] = str(e)
        
        return health
    
    async def close(self):
        """Clean up persistent HTTP clients"""
        with suppress(Exception):
            await self.client_local.aclose()
        with suppress(Exception):
            await self.client_openai.aclose()
    
    async def warm_engine(self):
        """Warm the local engine with a small test generation"""
        try:
            logger.info("Warming vLLM engine...")
            test_prompt = "Say hello in one word."
            count = 0
            async for event in self.stream_with_deadline(test_prompt):
                count += 1
                if count >= 3:  # Just get a few tokens
                    break
            logger.info("Engine warming completed")
        except Exception as e:
            logger.warning(f"Engine warming failed: {e}")