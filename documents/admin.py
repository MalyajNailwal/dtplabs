from django.contrib import admin
from .models import Document, LLMResponse


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['filename', 'file_type', 'status', 'model_used', 'created_at']
    list_filter = ['status', 'file_type']
    search_fields = ['filename']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(LLMResponse)
class LLMResponseAdmin(admin.ModelAdmin):
    list_display = ['document', 'title', 'language', 'word_count', 'processing_time']
    search_fields = ['title', 'summary']
