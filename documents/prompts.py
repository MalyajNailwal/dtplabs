"""Prompt templates for the document summarization LLM calls.

Kept separate from the API client in ``llm_utils.py`` on purpose: prompts are
content that gets tuned and reviewed often, while the transport code around
them rarely changes. Editing a template here needs no changes to the client.

The response schema below is the contract that ``LLMResponse`` is built from,
so any field added here must also exist on that model.
"""

from django.conf import settings


SUMMARY_SYSTEM_PROMPT = (
    "You are a precise document analyst. You always reply with a single valid "
    "JSON object and never add commentary, explanations or markdown fences."
)

RESPONSE_SCHEMA = """{
    "title": "A concise title for the document",
    "summary": "A comprehensive summary of the document (2-3 paragraphs)",
    "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
    "language": "The primary language of the document",
    "word_count": <integer, the number of words in the document>
}"""

SUMMARY_USER_TEMPLATE = """Analyze the following document and provide a structured JSON response.

Document text:
{document_text}

Provide your response in the following JSON format ONLY:
{response_schema}

The document contains {word_count} words - use that value for "word_count".
Important: Return ONLY the JSON object, no additional text or markdown formatting."""


def truncate(text, max_chars=None):
    """Trim document text to the prompt budget (``PROMPT_MAX_CHARS``).

    Long documents are cut rather than rejected: a summary of the opening
    section is more useful than an error, and the limit keeps us inside the
    model's context window.
    """
    limit = settings.PROMPT_MAX_CHARS if max_chars is None else max_chars
    return text[:limit]


def build_summary_messages(text, max_chars=None):
    """Build the OpenRouter ``messages`` list for a summary request."""
    return [
        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": SUMMARY_USER_TEMPLATE.format(
                document_text=truncate(text, max_chars),
                response_schema=RESPONSE_SCHEMA,
                word_count=len(text.split()),
            ),
        },
    ]
