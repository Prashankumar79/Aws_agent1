"""
Centralized LangSmith tracing utility.
Wraps any function with @traced to send execution data to LangSmith.
Falls back gracefully if langsmith is not installed.
"""
import functools
import logging
import time
from typing import Callable, Any

logger = logging.getLogger(__name__)

def traced(name: str = "", run_type: str = "llm"):
    """Decorator that traces a function call to LangSmith.
    
    Usage:
        @traced("bedrock_invoke", run_type="llm")
        def my_llm_call(messages, max_tokens):
            ...
    
    Falls back to no-op if langsmith is not installed or tracing is disabled.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            trace_name = name or func.__name__
            start = time.time()
            
            try:
                from langsmith import traceable
                # Use langsmith's traceable as a context manager
                traced_func = traceable(name=trace_name, run_type=run_type)(func)
                result = traced_func(*args, **kwargs)
                return result
            except ImportError:
                # langsmith not installed — run without tracing
                return func(*args, **kwargs)
            except Exception as e:
                # Tracing failed but don't break the app — run without tracing
                logger.debug(f"[Tracing] Failed for {trace_name}: {e}")
                return func(*args, **kwargs)
        
        return wrapper
    return decorator
