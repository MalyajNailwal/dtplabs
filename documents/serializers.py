import os

from django.conf import settings
from rest_framework import serializers

from .models import Document, LLMResponse


class LLMResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = LLMResponse
        fields = ['id', 'title', 'summary', 'keywords', 'language', 
                  'word_count', 'raw_response', 'processing_time', 'created_at']


class DocumentSerializer(serializers.ModelSerializer):
    llm_response = LLMResponseSerializer(read_only=True)
    
    class Meta:
        model = Document
        fields = ['id', 'filename', 'file_type', 'file_size', 'extracted_text',
                  'model_used', 'status', 'error_message', 'created_at', 
                  'updated_at', 'llm_response']
        read_only_fields = ['id', 'filename', 'file_type', 'file_size', 
                           'extracted_text', 'status', 'error_message', 
                           'created_at', 'updated_at']


class DocumentListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ['id', 'filename', 'file_type', 'file_size', 'model_used',
                  'status', 'created_at', 'updated_at']


class DocumentUploadSerializer(serializers.Serializer):
    ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.txt']

    file = serializers.FileField()
    model = serializers.CharField(max_length=255, required=False,
                                  default=settings.DEFAULT_LLM_MODEL)

    def validate_file(self, value):
        ext = os.path.splitext(value.name)[1].lower()

        if ext not in self.ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                f"File type not allowed. Allowed types: {', '.join(self.ALLOWED_EXTENSIONS)}"
            )

        max_size = settings.MAX_UPLOAD_SIZE
        if value.size > max_size:
            raise serializers.ValidationError(
                f"File size must be less than {max_size // (1024 * 1024)}MB"
            )

        return value
