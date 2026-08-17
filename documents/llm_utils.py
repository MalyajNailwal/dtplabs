import json
import requests
from django.conf import settings

from .prompts import build_summary_messages


OPENROUTER_API_KEY = settings.OPENROUTER_API_KEY
OPENROUTER_BASE_URL = settings.OPENROUTER_BASE_URL
DEFAULT_MODEL = settings.DEFAULT_LLM_MODEL


def get_free_models():
    """Fetch available free models from OpenRouter API."""
    try:
        response = requests.get(f"{OPENROUTER_BASE_URL}/models", timeout=10)
        response.raise_for_status()
        models = response.json().get('data', [])
        
        free_models = []
        for model in models:
            model_id = model.get('id', '')
            pricing = model.get('pricing', {})
            
            is_free = (
                model_id.endswith(':free') or
                pricing.get('prompt') == '0' or
                pricing.get('prompt') == 0
            )
            
            if is_free:
                free_models.append({
                    'id': model_id,
                    'name': model.get('name', model_id),
                })
        
        return free_models
    except requests.RequestException as e:
        raise ValueError(f"Failed to fetch models from OpenRouter: {str(e)}")


def call_llm(text, model=None):
    """Call OpenRouter LLM API with the given text."""
    model = model or DEFAULT_MODEL
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not configured")
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Document Summarizer"
    }
    
    data = {
        "model": model,
        "messages": build_summary_messages(text),
        "temperature": settings.LLM_TEMPERATURE,
        "max_tokens": settings.LLM_MAX_TOKENS,
        # Reasoning models (gpt-oss, nemotron, ...) otherwise spend the whole
        # token budget on hidden reasoning and return an empty/truncated answer.
        "reasoning": {"effort": settings.LLM_REASONING_EFFORT},
    }
    
    try:
        response = requests.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=data,
            timeout=settings.LLM_REQUEST_TIMEOUT
        )
        response.raise_for_status()
        
        result = response.json()
        if result.get('error'):
            raise ValueError(f"LLM API returned an error: {result['error'].get('message', result['error'])}")

        choice = result['choices'][0]
        content = choice['message'].get('content')
        finish_reason = choice.get('finish_reason')

        if not content or not content.strip():
            if finish_reason == 'length':
                raise ValueError(
                    "LLM response was truncated before any content was produced "
                    f"(finish_reason='length', max_tokens={settings.LLM_MAX_TOKENS}). "
                    "Increase LLM_MAX_TOKENS or lower LLM_REASONING_EFFORT."
                )
            raise ValueError(f"LLM returned an empty response (finish_reason={finish_reason!r})")

        content = content.strip()
        if content.startswith('```'):
            content = content.split('\n', 1)[1]
            if content.endswith('```'):
                content = content[:-3]
            content = content.strip()
        
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse LLM response as JSON: {str(e)}")
    except requests.RequestException as e:
        raise ValueError(f"LLM API request failed: {str(e)}")
    except (KeyError, IndexError) as e:
        raise ValueError(f"Unexpected LLM response structure: {str(e)}")
