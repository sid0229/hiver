import os
import sys
import time
import random
from google.api_core import exceptions

# Configure rate limiting delay (15 RPM -> 4 seconds minimum delay)
MIN_DELAY_SECONDS = 4.0

# Store the timestamps of the last call for each category
_LAST_CALL_TIMES = {
    "generation": 0.0,
    "embedding": 0.0
}

def throttle(call_type: str):
    """Enforces a minimum delay of MIN_DELAY_SECONDS between calls of the same type."""
    global _LAST_CALL_TIMES
    now = time.time()
    last_time = _LAST_CALL_TIMES.get(call_type, 0.0)
    elapsed = now - last_time
    delay = MIN_DELAY_SECONDS - elapsed
    if delay > 0:
        time.sleep(delay)
    _LAST_CALL_TIMES[call_type] = time.time()

def execute_with_retry(api_func, call_type: str, *args, **kwargs):
    """
    Executes a Gemini API function with rate limiting (throttling) and
    exponential backoff with jitter on 429 errors.
    """
    max_retries = 5
    for attempt in range(max_retries + 1):
        throttle(call_type)
        try:
            return api_func(*args, **kwargs)
        except Exception as e:
            err_msg = str(e)
            is_429 = (
                isinstance(e, exceptions.ResourceExhausted)
                or "429" in err_msg
                or "Quota exceeded" in err_msg
                or "ResourceExhausted" in err_msg
            )
            
            if is_429 and attempt < max_retries:
                # Exponential backoff: starts at ~2s, doubling with jitter
                base_wait = 2.0 * (2 ** attempt)
                jitter = random.uniform(0.0, 1.5)
                wait_time = base_wait + jitter
                print(
                    f"[{call_type.upper()} API] 429 Quota Exceeded. Retrying attempt {attempt+1}/{max_retries} "
                    f"in {wait_time:.2f}s... Error: {err_msg}",
                    file=sys.stderr
                )
                time.sleep(wait_time)
            else:
                # Re-raise the exception if it's not a 429, or all retries failed
                raise e
