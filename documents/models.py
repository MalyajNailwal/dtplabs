import uuid
from django.db import models


class Document(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    FILE_TYPE_CHOICES = [
        ('pdf', 'PDF'),
        ('docx', 'DOCX'),
        ('txt', 'TXT'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField(upload_to='documents/%Y/%m/%d/')
    filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES)
    file_size = models.PositiveIntegerField(help_text='File size in bytes')
    extracted_text = models.TextField(blank=True, null=True)
    model_used = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.filename} ({self.status})"


class LLMResponse(models.Model):
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name='llm_response')
    title = models.CharField(max_length=500, blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    keywords = models.JSONField(default=list, blank=True)
    language = models.CharField(max_length=50, blank=True, null=True)
    word_count = models.PositiveIntegerField(default=0)
    raw_response = models.JSONField(blank=True, null=True)
    processing_time = models.FloatField(default=0, help_text='Processing time in seconds')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"LLM Response for {self.document.filename}"
