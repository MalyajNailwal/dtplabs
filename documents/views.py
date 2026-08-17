import os
import logging
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.conf import settings
from django.shortcuts import render

from .models import Document
from .serializers import (DocumentSerializer, DocumentListSerializer, 
                         DocumentUploadSerializer)
from .tasks import process_document
from .llm_utils import get_free_models

logger = logging.getLogger(__name__)


class DocumentUploadView(generics.CreateAPIView):
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = DocumentUploadSerializer
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        file = serializer.validated_data['file']
        model = serializer.validated_data.get('model') or settings.DEFAULT_LLM_MODEL
        
        file_ext = os.path.splitext(file.name)[1].lower().strip('.')
        
        document = Document.objects.create(
            file=file,
            filename=file.name,
            file_type=file_ext,
            file_size=file.size,
            model_used=model,
            status='pending'
        )
        
        use_celery = False
        try:
            import redis
            r = redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=2)
            r.ping()
            use_celery = True
        except Exception:
            pass
        
        if use_celery:
            process_document.delay(str(document.id))
        else:
            logger.warning("Redis unavailable, processing synchronously")
            try:
                process_document(str(document.id))
            except Exception as exc:
                # Synchronous fallback must never fail the upload itself.
                # The task already records the failure on the document, so we
                # just log it and let the client poll the status endpoint.
                logger.error(
                    f"Synchronous processing failed for {document.id}: {exc}"
                )
            document.refresh_from_db()

        logger.info(f"Document uploaded: {document.filename} (ID: {document.id})")

        return Response({
            "message": "Document uploaded successfully. Processing started.",
            "document_id": str(document.id),
            "status": document.status,
            "error_message": document.error_message or None,
        }, status=status.HTTP_201_CREATED)


class DocumentListView(generics.ListAPIView):
    queryset = Document.objects.all()
    serializer_class = DocumentListSerializer


class DocumentDetailView(generics.RetrieveAPIView):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    lookup_field = 'id'


@api_view(['GET'])
def document_status_view(request, id):
    try:
        document = Document.objects.get(id=id)
        return Response({
            "id": str(document.id),
            "filename": document.filename,
            "status": document.status,
            "error_message": document.error_message
        })
    except Document.DoesNotExist:
        return Response({
            "error": "Document not found"
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
def free_models_view(request):
    try:
        models = get_free_models()
        return Response({
            "free_models": models,
            "count": len(models)
        })
    except ValueError as e:
        return Response({
            "error": str(e),
            "free_models": [],
            "count": 0
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)


def index_view(request):
    """Minimal demo page that drives the public API from the browser.

    Not part of the REST API - it is a thin client so the upload/poll/summary
    flow can be demonstrated without Postman or curl.
    """
    return render(request, 'documents/index.html', {
        'default_model': settings.DEFAULT_LLM_MODEL,
        'max_upload_mb': settings.MAX_UPLOAD_SIZE // (1024 * 1024),
    })
