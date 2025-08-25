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

from .demo_mode import DemoMode

logger = logging.getLogger(__name__)

class _ToolArgsAssembler:
    """Accumulates streamed tool_call arguments OR plain content for robust JSON completion"""
    def __init__(self):
        self._args_by_idx = {}
        self._content_parts = []

    def feed(self, obj: dict):
        choice = (obj.get("choices") or [{}])[0]
        delta = choice.get("delta") or {}
        
        # OpenAI-style streamed tool_calls in delta
        for tc in delta.get("tool_calls", []) or []:
            idx = tc.get("index", 0)
            fn = tc.get("function", {}) or {}
            frag = fn.get("arguments") or ""
            if frag:
                self._args_by_idx[idx] = self._args_by_idx.get(idx, "") + frag
        
        # Fallback to content
        content = delta.get("content")
        if content:
            self._content_parts.append(content)

    def result(self) -> str:
        if self._args_by_idx:
            # Prefer the first tool call deterministically
            return self._args_by_idx.get(0) or next(iter(self._args_by_idx.values()))
        return "".join(self._content_parts)

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

    async def _demo_stream(self, prompt: str) -> AsyncIterator[Dict[str, Any]]:
        """Deterministic demo mode response for predictable presentations"""
        logger.info("🎬 Demo mode LLM: Using deterministic response")
        
        # Deterministic response chunks for demo stability
        response_chunks = [
            "Based on your profile and interests, here are my recommendations:\n\n",
            "**CS 4780: Machine Learning** - Excellent fit for your ML interest. ",
            "Prerequisites satisfied (CS 2110, CS 2800). Professor quality: 4.2/5.\n\n",
            "**CS 3110: Data Structures & Functional Programming** - Core requirement. ",
            "Strong foundation for advanced courses. Manageable workload.\n\n",
            "**CS 4820: Introduction to Algorithms** - Builds on CS 2800. ",
            "High demand course, register early. Prerequisites: CS 2800, MATH 2940.\n\n"
        ]
        
        try:
            # Emit tokens with realistic timing
            for i, chunk in enumerate(response_chunks):
                await asyncio.sleep(0.05)  # 50ms between chunks for realistic feel
                yield {
                    "provider": "demo-mode",
                    "event": "token", 
                    "text": chunk
                }
            
            # Final structured JSON chunk for completeness
            await asyncio.sleep(0.1)
            yield {
                "provider": "demo-mode",
                "event": "done"
            }
        except Exception as e:
            logger.error(f"Demo stream error: {e}")
            yield {
                "provider": "demo-mode",
                "event": "error",
                "error": str(e)
            }

    async def stream_with_deadline(self, prompt: str) -> AsyncIterator[Dict[str, Any]]:
        """
        Race the first token from local vLLM vs 200ms deadline.
        If local doesn't produce token in time, cancel and stream from fallback.
        
        This prevents demo hangs while preserving local-first architecture.
        Enhanced with proper resource cleanup and cancellation.
        
        DEMO MODE: When demo mode is enabled or local LLM unavailable, 
        use deterministic response for presentation stability.
        """
        # Demo mode short-circuit for presentation stability
        if DemoMode.is_enabled():
            async for evt in self._demo_stream(prompt):
                yield evt
            return
            
        # Also check if local LLM URL is missing/unavailable for graceful degradation
        vllm_unavailable = not os.getenv("VLLM_BASE_URL") and "localhost:8000" in self.vllm_base
        if vllm_unavailable and not self.openai_key:
            logger.warning("No local LLM or OpenAI key available, using demo mode")
            async for evt in self._demo_stream(prompt):
                yield evt
            return
        
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
                with contextlib.suppress(asyncio.CancelledError):
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
                with contextlib.suppress(asyncio.CancelledError):
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
    
    async def complete_json_with_deadline(self, prompt: str, max_tokens: int = 900) -> str:
        """
        Try local (vLLM) first; if first token misses deadline, fallback to OpenAI with JSON mode.
        Returns raw text (expected to be pure JSON).
        """
        # Demo mode short-circuit for presentation stability
        if DemoMode.is_enabled():
            logger.info("🎬 Demo mode JSON completion: Using mock response")
            await asyncio.sleep(0.1)  # Realistic delay
            return '{"success": true, "data": "demo_response"}'
        
        try:
            # Attempt local completion quickly
            text = await self._try_local_complete(prompt, max_tokens=max_tokens, json_hint=True)
            if text and text.strip():
                return text
        except Exception:
            pass
        # Fallback: OpenAI with response_format=json_object when available
        return await self._fallback_complete_json(prompt, max_tokens=max_tokens)

    async def complete_json_structured(self, prompt: str, model_schema: dict, max_tokens: int = 900) -> str:
        """
        Enhanced structured JSON completion with tool calls support and hedged fallback.
        Implements redisTicket.md recommendations for robust JSON generation.
        """
        import contextlib
        
        # Demo mode short-circuit for presentation stability
        if DemoMode.is_enabled():
            logger.info("🎬 Demo mode JSON completion: Using mock structured response")
            await asyncio.sleep(0.1)  # Realistic delay
            return '{"recommendations": [{"course": "CS 4780", "title": "Machine Learning", "rating": 4.2, "confidence": "high"}], "reasoning": "Perfect match for ML interests"}'
        
        hedge_delay_ms = getattr(self, "hedge_delay_ms", 250)
        
        async def _local_stream_with_tools():
            """Try local vLLM with tool calls if supported"""
            url = f"{self.vllm_base}/chat/completions"
            headers = {"Content-Type": "application/json"}
            payload = {
                "model": self.model_local,
                "stream": True,
                "temperature": 0.1,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            }
            
            # Try tools first, fallback to content if not supported
            try:
                payload.update({
                    "tools": [{"type": "function", "function": {"name": "advisor_reply", "parameters": model_schema}}],
                    "tool_choice": {"type": "function", "function": {"name": "advisor_reply"}},
                })
            except Exception:
                # If tools not supported, just stream content
                pass
                
            assembler = _ToolArgsAssembler()
            async with self.client_local.stream("POST", url, headers=headers, json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        assembler.feed(json.loads(data))
                    except Exception:
                        pass  # Ignore malformed chunks
            return assembler.result()

        async def _openai_json_mode():
            """OpenAI with JSON mode fallback"""
            url = f"{self.openai_base}/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_key}",
            }
            payload = {
                "model": self.model_fallback,
                "stream": False,
                "temperature": 0.1,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant designed to output JSON only."},
                    {"role": "user", "content": prompt},
                ],
            }
            
            resp = await self.client_openai.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        # Hedged approach: start local, then OpenAI after short delay
        local_task = asyncio.create_task(_local_stream_with_tools())
        
        # Give local a head start
        await asyncio.sleep(hedge_delay_ms / 1000.0)
        
        if self.openai_key:
            openai_task = asyncio.create_task(_openai_json_mode())
            done, pending = await asyncio.wait({local_task, openai_task}, return_when=asyncio.FIRST_COMPLETED)
            
            # Clean up the losing task
            winner = done.pop()
            result = await winner
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            return result
        else:
            # No OpenAI key, just wait for local
            return await local_task

    async def _try_local_complete(self, prompt: str, max_tokens: int = 900, json_hint: bool = False) -> str:
        """
        Stream from local (vLLM) and enforce a *first-token* deadline.
        If json_hint=True, prepend a 'JSON ONLY' instruction.
        """
        deadline = getattr(self, "first_token_deadline_ms", 200) / 1000
        jhint = "\nReturn ONLY a JSON object. No prose, no markdown fences.\n" if json_hint else ""

        url = f"{self.vllm_base}/chat/completions"
        payload = {
            "model": self.model_local,
            "stream": True,
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt + jhint}],
        }
        headers = {"Content-Type": "application/json"}

        # We stream; if no first chunk by deadline, we bail.
        first_chunk = asyncio.Event()
        buffer = []

        async def _recv():
            async with self.client_local.stream("POST", url, headers=headers, json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                        delta = obj["choices"][0]["delta"].get("content")
                        if delta:
                            buffer.append(delta)
                            first_chunk.set()
                    except Exception:
                        # ignore malformed chunks; continue
                        pass
        task = asyncio.create_task(_recv())
        try:
            await asyncio.wait_for(first_chunk.wait(), timeout=deadline)
        except asyncio.TimeoutError:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            return ""  # signal caller to fallback
        else:
            await task  # finish stream
            return "".join(buffer)

    async def _fallback_complete_json(self, prompt: str, max_tokens: int = 900) -> str:
        """
        Use OpenAI/compatible with response_format={'type': 'json_object'} when supported; else add strict system msg.
        """
        if not self.openai_key:
            # Last resort: ask model for JSON only
            strict = prompt + "\nReturn ONLY a JSON object. Do not include backticks or any explanation."
            return await self._try_local_complete(strict, max_tokens=max_tokens)
        
        url = f"{self.openai_base}/chat/completions"
        payload = {
            "model": self.model_fallback,
            "stream": False,
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
                {"role": "user", "content": prompt}
            ],
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.openai_key}",
        }
        
        response = await self.client_openai.post(url, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        return result.get("choices", [{}])[0].get("message", {}).get("content", "")