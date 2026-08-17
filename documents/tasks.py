import time
import logging
from celery import shared_task
from .models import Document, LLMResponse
from .utils import extract_text
from .llm_utils import call_llm

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def process_document(self, document_id):
    """Process document: extract text and call LLM."""
    try:
        document = Document.objects.get(id=document_id)
        document.status = 'processing'
        document.save(update_fields=['status'])
        
        logger.info(f"Processing document: {document.filename}")
        
        text = extract_text(document.file.path, document.file_type)
        
        if not text:
            document.status = 'failed'
            document.error_message = "No text could be extracted from the document"
            document.save(update_fields=['status', 'error_message'])
            return {"status": "failed", "error": "Empty document"}
        
        document.extracted_text = text
        document.save(update_fields=['extracted_text'])
        
        start_time = time.time()
        llm_response = call_llm(text, document.model_used)
        processing_time = time.time() - start_time
        
        LLMResponse.objects.create(
            document=document,
            title=llm_response.get('title', ''),
            summary=llm_response.get('summary', ''),
            keywords=llm_response.get('keywords', []),
            language=llm_response.get('language', ''),
            word_count=llm_response.get('word_count', len(text.split())),
            raw_response=llm_response,
            processing_time=processing_time
        )
        
        document.status = 'completed'
        document.save(update_fields=['status'])
        
        logger.info(f"Document processed successfully: {document.filename}")
        return {"status": "completed", "document_id": str(document_id)}
        
    except Document.DoesNotExist:
        logger.error(f"Document not found: {document_id}")
        return {"status": "error", "error": "Document not found"}
        
    except ValueError as exc:
        if "OPENROUTER_API_KEY" in str(exc):
            document.status = 'failed'
            document.error_message = "OpenRouter API key not configured"
            document.save(update_fields=['status', 'error_message'])
            return {"status": "failed", "error": "API key not configured"}
        
        logger.error(f"Error processing document {document_id}: {str(exc)}")
        try:
            document = Document.objects.get(id=document_id)
            document.status = 'failed'
            document.error_message = str(exc)
            document.save(update_fields=['status', 'error_message'])
        except Document.DoesNotExist:
            pass
        raise self.retry(exc=exc)
        
    except Exception as exc:
        logger.error(f"Error processing document {document_id}: {str(exc)}")
        
        try:
            document = Document.objects.get(id=document_id)
            document.status = 'failed'
            document.error_message = str(exc)
            document.save(update_fields=['status', 'error_message'])
        except Document.DoesNotExist:
            pass
        
        raise self.retry(exc=exc)
