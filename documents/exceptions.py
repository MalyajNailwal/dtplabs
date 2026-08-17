import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """Custom exception handler for consistent error responses."""
    response = exception_handler(exc, context)
    
    if response is not None:
        error_data = {
            "error": True,
            "status_code": response.status_code,
            "message": _get_error_message(response),
            "details": response.data
        }
        response.data = error_data
    else:
        logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
        response = Response({
            "error": True,
            "status_code": 500,
            "message": "Internal server error",
            "details": str(exc) if context.get('request', {}).user and context['request'].user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return response


def _get_error_message(response):
    """Extract human-readable error message from response."""
    if isinstance(response.data, dict):
        if 'detail' in response.data:
            return str(response.data['detail'])
        if 'message' in response.data:
            return response.data['message']
    
    if isinstance(response.data, list):
        return "Validation error"
    
    return f"Request failed with status {response.status_code}"
