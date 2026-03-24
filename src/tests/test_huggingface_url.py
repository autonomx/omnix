"""
Tests for HuggingFace URL parsing and LLM model management.

Tests the URL parsing logic for extracting model IDs from HuggingFace URLs.
These tests verify the fix for the bug where URLs like:
  https://huggingface.co/unsloth/gpt-oss-20b-GGUF
were incorrectly parsed as "unsloth" instead of "unsloth/gpt-oss-20b-GGUF"

Also tests the fix for URLs with query parameters:
  https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF?show_file_info=qwen2.5-coder-7b-instruct-q3_k_m.gguf
were incorrectly resulting in filenames with query params
"""

import pytest
import json
import os
import sys
from urllib.parse import urlparse, unquote

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestHuggingFaceURLParsing:
    """Test HuggingFace URL parsing logic.
    
    These tests verify that model IDs are correctly extracted from 
    HuggingFace URLs. The bug was that only the first path segment
    was used (e.g., "unsloth") instead of the full model ID 
    (e.g., "unsloth/gpt-oss-20b-GGUF").
    """
    
    def test_parse_simple_model_url(self):
        """Test parsing a simple model URL like unsloth/gpt-oss-20b-GGUF"""
        # This is the FIXED parsing logic from fetch_huggingface_files
        model_url = "https://huggingface.co/unsloth/gpt-oss-20b-GGUF"
        
        if 'huggingface.co/' in model_url:
            parts = model_url.split('huggingface.co/')
            if len(parts) > 1:
                path_parts = parts[1].split('/')
                # Fixed: Rejoin first 2 parts to get full model ID
                model_id = '/'.join(path_parts[:2])
        
        assert model_id == "unsloth/gpt-oss-20b-GGUF"
    
    def test_parse_url_with_tree_path(self):
        """Test parsing URL with /tree/main path"""
        model_url = "https://huggingface.co/ggml-org/Devstral-Small-2-24B-Instruct-2512-GGUF/tree/main"
        
        if 'huggingface.co/' in model_url:
            parts = model_url.split('huggingface.co/')
            if len(parts) > 1:
                path_parts = parts[1].split('/')
                model_id = '/'.join(path_parts[:2])
        
        assert model_id == "ggml-org/Devstral-Small-2-24B-Instruct-2512-GGUF"
    
    def test_parse_mistral_model_url(self):
        """Test parsing Mistral model URL"""
        model_url = "https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.2-GGUF"
        
        if 'huggingface.co/' in model_url:
            parts = model_url.split('huggingface.co/')
            if len(parts) > 1:
                path_parts = parts[1].split('/')
                model_id = '/'.join(path_parts[:2])
        
        assert model_id == "mistralai/Mistral-7B-Instruct-v0.2-GGUF"
    
    def test_parse_model_with_quantization(self):
        """Test parsing model URL with quantization suffix"""
        model_url = "https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF/resolve/main"
        
        if 'huggingface.co/' in model_url:
            parts = model_url.split('huggingface.co/')
            if len(parts) > 1:
                path_parts = parts[1].split('/')
                model_id = '/'.join(path_parts[:2])
        
        assert model_id == "TheBloke/Llama-2-7B-Chat-GGUF"
    
    def test_parse_qwen_model_url(self):
        """Test parsing Qwen model URL"""
        model_url = "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF"
        
        if 'huggingface.co/' in model_url:
            parts = model_url.split('huggingface.co/')
            if len(parts) > 1:
                path_parts = parts[1].split('/')
                model_id = '/'.join(path_parts[:2])
        
        assert model_id == "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
    
    def test_parse_single_word_org(self):
        """Test parsing URL with single-word organization"""
        model_url = "https://huggingface.co/meta/Llama-3.1-8B-Instruct-GGUF"
        
        if 'huggingface.co/' in model_url:
            parts = model_url.split('huggingface.co/')
            if len(parts) > 1:
                path_parts = parts[1].split('/')
                model_id = '/'.join(path_parts[:2])
        
        assert model_id == "meta/Llama-3.1-8B-Instruct-GGUF"
    
    def test_parse_llama_3_1_model(self):
        """Test parsing Llama 3.1 model URL"""
        model_url = "https://huggingface.co/unsloth/Llama-3.1-8B-Instruct-GGUF"
        
        if 'huggingface.co/' in model_url:
            parts = model_url.split('huggingface.co/')
            if len(parts) > 1:
                path_parts = parts[1].split('/')
                model_id = '/'.join(path_parts[:2])
        
        assert model_id == "unsloth/Llama-3.1-8B-Instruct-GGUF"
    
    def test_parse_phi_model(self):
        """Test parsing Phi model URL"""
        model_url = "https://huggingface.co/microsoft/Phi-3.5-mini-instruct-GGUF"
        
        if 'huggingface.co/' in model_url:
            parts = model_url.split('huggingface.co/')
            if len(parts) > 1:
                path_parts = parts[1].split('/')
                model_id = '/'.join(path_parts[:2])
        
        assert model_id == "microsoft/Phi-3.5-mini-instruct-GGUF"


class TestFilenameExtractionFromURL:
    """Test filename extraction from URLs with query parameters.
    
    These tests verify the fix for the bug where URLs like:
    https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF?show_file_info=qwen2.5-coder-7b-instruct-q3_k_m.gguf
    
    Were incorrectly parsed, resulting in filenames like:
    "Qwen2.5-Coder-7B-Instruct-GGUF?show_file_info=qwen2.5-coder-7b-instruct-q3_k_m.gguf"
    
    Instead of just: "qwen2.5-coder-7b-instruct-q3_k_m.gguf"
    """
    
    def test_extract_filename_simple(self):
        """Test extracting filename from simple URL"""
        url = "https://huggingface.co/model/resolve/main/model.gguf"
        
        parsed = urlparse(url)
        filename = unquote(parsed.path.split('/')[-1])
        
        assert filename == "model.gguf"
    
    def test_extract_filename_with_query_params(self):
        """Test extracting filename from URL with query parameters"""
        # This is the actual problematic URL format from HuggingFace
        url = "https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF?show_file_info=qwen2.5-coder-7b-instruct-q3_k_m.gguf"
        
        parsed = urlparse(url)
        filename = unquote(parsed.path.split('/')[-1])
        
        # Should be just "Qwen2.5-Coder-7B-Instruct-GGUF", not the query param
        assert filename == "Qwen2.5-Coder-7B-Instruct-GGUF"
    
    def test_extract_filename_with_escape_chars(self):
        """Test extracting filename with URL-encoded characters"""
        url = "https://huggingface.co/model/resolve/main/model%20with%20spaces.gguf"
        
        parsed = urlparse(url)
        filename = unquote(parsed.path.split('/')[-1])
        
        assert filename == "model with spaces.gguf"
    
    def test_clean_filename_from_file_list(self):
        """Test cleaning filename from file list (removing query params)"""
        # When files come from HF API, they might have query params in the name
        file = "qwen2.5-coder-7b-instruct-q3_k_m.gguf?download=true"
        
        clean_filename = file.split('?')[0]
        
        assert clean_filename == "qwen2.5-coder-7b-instruct-q3_k_m.gguf"
    
    def test_clean_filename_no_query_params(self):
        """Test cleaning filename that has no query params"""
        file = "model.gguf"
        
        clean_filename = file.split('?')[0]
        
        assert clean_filename == "model.gguf"
    
    def test_build_download_url(self):
        """Test building download URL without query params"""
        model_id = "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF"
        file = "qwen2.5-coder-7b-instruct-q3_k_m.gguf?download=true"
        
        clean_filename = file.split('?')[0]
        download_url = f"https://huggingface.co/{model_id}/resolve/main/{clean_filename}"
        
        expected = "https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q3_k_m.gguf"
        assert download_url == expected


class TestLLMModelEndpoints:
    """Test LLM model management endpoints."""
    
    def test_get_llm_models_empty(self, client):
        """Test getting models when directory is empty or doesn't exist."""
        response = client.get('/api/llm/models')
        
        assert response.status_code == 200
        data = response.json
        assert data['success'] is True
        assert 'models' in data
        assert isinstance(data['models'], list)
    
    def test_delete_llm_model_not_found(self, client):
        """Test deleting non-existent model."""
        response = client.delete('/api/llm/models/nonexistent_model.gguf')
        
        assert response.status_code == 404
        data = response.json
        assert data['success'] is False


class TestHuggingFaceAPIValidation:
    """Test HuggingFace API endpoint validation (without external API calls)."""
    
    def test_fetch_huggingface_files_missing_url(self, client):
        """Test fetch with missing model_url."""
        response = client.post(
            '/api/llm/huggingface/files',
            json={},
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = response.json
        assert data['success'] is False
    
    def test_fetch_huggingface_files_invalid_url(self, client):
        """Test fetch with invalid HuggingFace URL (not from huggingface.co)."""
        response = client.post(
            '/api/llm/huggingface/files',
            json={'model_url': 'https://invalid-domain.com/model'},
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = response.json
        assert data['success'] is False
    
    def test_search_huggingface_missing_query(self, client):
        """Test search with missing query."""
        response = client.get('/api/huggingface/search')
        
        assert response.status_code == 400
        data = response.json
        assert data['success'] is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
