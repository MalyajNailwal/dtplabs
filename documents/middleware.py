"""Request/response logging middleware.

Emits one structured line per request (and one per unhandled exception) so API
traffic, slow calls and failures are traceable without adding logging calls to
every view. Each request carries a short id that is also returned in the
``X-Request-ID`` response header, which makes a client-reported problem easy to
find in the logs.
"""

import logging
import time
import uuid

logger = logging.getLogger('documents.requests')

# Never log these, even though they arrive as ordinary query/POST params.
SENSITIVE_KEYS = {'password', 'token', 'secret', 'api_key', 'authorization'}


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = uuid.uuid4().hex[:8]
        started = time.monotonic()

        response = self.get_response(request)

        duration_ms = (time.monotonic() - started) * 1000
        # 5xx is our fault, 4xx is the caller's - log them at different levels
        # so alerting can key off ERROR only.
        if response.status_code >= 500:
            log = logger.error
        elif response.status_code >= 400:
            log = logger.warning
        else:
            log = logger.info

        log(
            'request_id=%s method=%s path=%s status=%s duration_ms=%.1f query=%s',
            request.request_id,
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            self._safe_query(request),
        )

        response['X-Request-ID'] = request.request_id
        return response

    def process_exception(self, request, exception):
        """Log unhandled exceptions with a traceback, then let Django continue.

        Returning None keeps the normal error handling (and DRF's exception
        handler) in charge of the response.
        """
        logger.error(
            'request_id=%s method=%s path=%s unhandled_exception=%s: %s',
            getattr(request, 'request_id', '-'),
            request.method,
            request.path,
            type(exception).__name__,
            exception,
            exc_info=True,
        )
        return None

    @staticmethod
    def _safe_query(request):
        return {
            key: ('***' if key.lower() in SENSITIVE_KEYS else value)
            for key, value in request.GET.items()
        }
