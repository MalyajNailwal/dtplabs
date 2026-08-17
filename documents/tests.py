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
