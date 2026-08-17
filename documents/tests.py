import logging
import os
import json
import tempfile
from unittest.mock import patch, MagicMock
from django.conf import settings
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status

from .models import Document, LLMResponse
from .utils import extract_text_from_txt, extract_text_from_pdf, extract_text_from_docx
from .llm_utils import get_free_models, call_llm
from .prompts import build_summary_messages, truncate


def setUpModule():
    """Keep the request log out of the test report.

    assertLogs() raises the level it needs on its own, so the middleware tests
    below still see their records.
    """
    logging.getLogger('documents').setLevel(logging.CRITICAL)
    logging.getLogger('documents.requests').setLevel(logging.CRITICAL)


class DocumentModelTest(TestCase):
    def test_create_document(self):
        document = Document.objects.create(
            filename='test.txt',
            file_type='txt',
            file_size=1024,
            status='pending'
        )
        self.assertEqual(document.filename, 'test.txt')
        self.assertEqual(document.status, 'pending')
        self.assertIsNotNone(document.id)

    def test_document_str(self):
        document = Document.objects.create(
            filename='test.txt',
            file_type='txt',
            file_size=1024,
            status='completed'
        )
        self.assertEqual(str(document), 'test.txt (completed)')


class LLMResponseModelTest(TestCase):
    def setUp(self):
        self.document = Document.objects.create(
            filename='test.txt',
            file_type='txt',
            file_size=1024,
            status='completed'
        )

    def test_create_llm_response(self):
        response = LLMResponse.objects.create(
            document=self.document,
            title='Test Title',
            summary='Test Summary',
            keywords=['test', 'keyword'],
            language='English',
            word_count=100
        )
        self.assertEqual(response.title, 'Test Title')
        self.assertEqual(response.word_count, 100)


class TextExtractionTest(TestCase):
    def test_extract_text_from_txt(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write('Hello World\nThis is a test document.')
            temp_path = f.name
        
        try:
            text = extract_text_from_txt(temp_path)
            self.assertEqual(text, 'Hello World\nThis is a test document.')
        finally:
            os.unlink(temp_path)

    def test_extract_text_empty_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write('')
            temp_path = f.name
        
        try:
            text = extract_text_from_txt(temp_path)
            self.assertEqual(text, '')
        finally:
            os.unlink(temp_path)


class DocumentAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.document = Document.objects.create(
            filename='test.txt',
            file_type='txt',
            file_size=1024,
            status='completed',
            extracted_text='Test content'
        )

    def test_list_documents(self):
        response = self.client.get('/api/documents/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_document_detail(self):
        response = self.client.get(f'/api/documents/{self.document.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['filename'], 'test.txt')

    def test_get_document_not_found(self):
        response = self.client.get('/api/documents/00000000-0000-0000-0000-000000000000/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class LLMUtilsTest(TestCase):
    @patch('documents.llm_utils.requests.get')
    def test_get_free_models(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'data': [
                {'id': 'model/free-1', 'name': 'Free Model 1', 'pricing': {'prompt': '0'}},
                {'id': 'model/paid-1', 'name': 'Paid Model 1', 'pricing': {'prompt': '0.001'}},
                {'id': 'model/free-2:free', 'name': 'Free Model 2', 'pricing': {'prompt': '0.001'}},
            ]
        }
        mock_get.return_value = mock_response
        
        models = get_free_models()
        self.assertEqual(len(models), 2)

    @patch('documents.llm_utils.requests.post')
    def test_call_llm(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': json.dumps({
                        'title': 'Test Title',
                        'summary': 'Test Summary',
                        'keywords': ['test'],
                        'language': 'English',
                        'word_count': 10
                    })
                }
            }]
        }
        mock_post.return_value = mock_response
        
        with patch('documents.llm_utils.OPENROUTER_API_KEY', 'test-key'):
            result = call_llm('Test content')
            self.assertEqual(result['title'], 'Test Title')

    @patch('documents.llm_utils.requests.post')
    def test_call_llm_truncated_response(self, mock_post):
        """Reasoning models can spend the whole budget on reasoning and return
        no content - that must surface as a clear ValueError, not AttributeError."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'choices': [{'message': {'content': None}, 'finish_reason': 'length'}]
        }
        mock_post.return_value = mock_response

        with patch('documents.llm_utils.OPENROUTER_API_KEY', 'test-key'):
            with self.assertRaises(ValueError) as ctx:
                call_llm('Test content')
        self.assertIn('truncated', str(ctx.exception))

    @patch('documents.llm_utils.requests.post')
    def test_call_llm_markdown_fenced_json(self, mock_post):
        """Models often wrap JSON in ```json fences."""
        payload = {'title': 'Fenced', 'summary': 's', 'keywords': [],
                   'language': 'English', 'word_count': 1}
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'choices': [{
                'message': {'content': f"```json\n{json.dumps(payload)}\n```"},
                'finish_reason': 'stop'
            }]
        }
        mock_post.return_value = mock_response

        with patch('documents.llm_utils.OPENROUTER_API_KEY', 'test-key'):
            self.assertEqual(call_llm('Test content')['title'], 'Fenced')

    @patch('documents.llm_utils.requests.post')
    def test_call_llm_api_error_payload(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {'error': {'message': 'Rate limited', 'code': 429}}
        mock_post.return_value = mock_response

        with patch('documents.llm_utils.OPENROUTER_API_KEY', 'test-key'):
            with self.assertRaises(ValueError) as ctx:
                call_llm('Test content')
        self.assertIn('Rate limited', str(ctx.exception))


class DemoPageTest(TestCase):
    def test_index_page_renders(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'Document Summarizer')
        self.assertContains(response, settings.DEFAULT_LLM_MODEL)


class PromptTemplateTest(TestCase):
    def test_build_summary_messages_structure(self):
        messages = build_summary_messages('one two three')
        self.assertEqual([m['role'] for m in messages], ['system', 'user'])
        for field in ('title', 'summary', 'keywords', 'language', 'word_count'):
            self.assertIn(field, messages[1]['content'])

    def test_word_count_is_injected(self):
        messages = build_summary_messages('one two three four')
        self.assertIn('contains 4 words', messages[1]['content'])

    def test_long_document_is_truncated_to_budget(self):
        self.assertEqual(len(truncate('x' * 50, max_chars=10)), 10)

    @override_settings(PROMPT_MAX_CHARS=25)
    def test_truncate_uses_configured_budget(self):
        self.assertEqual(len(truncate('y' * 100)), 25)


class RequestLoggingMiddlewareTest(TestCase):
    def test_request_id_header_is_returned(self):
        response = self.client.get('/api/documents/')
        self.assertEqual(len(response['X-Request-ID']), 8)

    def test_successful_request_is_logged_at_info(self):
        with self.assertLogs('documents.requests', level='INFO') as logs:
            self.client.get('/api/documents/')
        self.assertIn('method=GET path=/api/documents/ status=200', logs.output[0])

    def test_client_error_is_logged_as_warning(self):
        with self.assertLogs('documents.requests', level='WARNING') as logs:
            self.client.get('/api/documents/00000000-0000-0000-0000-000000000000/')
        self.assertIn('status=404', logs.output[0])

    def test_sensitive_query_params_are_masked(self):
        with self.assertLogs('documents.requests', level='INFO') as logs:
            self.client.get('/api/documents/?api_key=super-secret')
        self.assertNotIn('super-secret', logs.output[0])
        self.assertIn('***', logs.output[0])
