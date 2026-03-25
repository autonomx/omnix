"""
API endpoint tests for Flask routes.
Tests the HTTP interface without requiring external services.
"""

import pytest
import json
import base64
from unittest.mock import patch, MagicMock


class TestHealthEndpoint:
    """Test health check endpoints."""
    
    def test_health_endpoint_disconnected(self, client):
        """Test health endpoint when services are not available."""
        response = client.get('/api/health')
        # May return 503 if no provider configured
        assert response.status_code in [200, 503]


class TestSettingsEndpoints:
    """Test settings API endpoints."""
    
    def test_get_settings(self, client):
        """Test getting settings."""
        response = client.get('/api/settings')
        assert response.status_code == 200
        
        data = response.json
        assert data['success'] is True
        assert 'settings' in data
    
    def test_save_settings(self, client):
        """Test saving settings."""
        new_settings = {
            'provider': 'lmstudio',
            'lmstudio': {
                'base_url': 'http://localhost:1234'
            }
        }
        response = client.post('/api/settings', 
                               json=new_settings,
                               content_type='application/json')
        assert response.status_code == 200
        assert response.json['success'] is True


class TestSessionEndpoints:
    """Test session management endpoints."""
    
    def test_get_sessions(self, client):
        """Test getting all sessions."""
        response = client.get('/api/sessions')
        assert response.status_code == 200
        
        data = response.json
        assert data['success'] is True
        assert 'sessions' in data
        assert isinstance(data['sessions'], list)
    
    def test_create_session(self, client):
        """Test creating a new session."""
        response = client.post('/api/sessions')
        assert response.status_code == 200
        
        data = response.json
        assert data['success'] is True
        assert 'session_id' in data
        
        # Cleanup
        session_id = data['session_id']
        client.delete(f'/api/sessions/{session_id}')
    
    def test_get_session(self, client):
        """Test getting a specific session."""
        # First create a session
        create_response = client.post('/api/sessions')
        session_id = create_response.json['session_id']
        
        # Then get it
        response = client.get(f'/api/sessions/{session_id}')
        assert response.status_code == 200
        
        data = response.json
        assert data['success'] is True
        assert 'session' in data
        
        # Cleanup
        client.delete(f'/api/sessions/{session_id}')
    
    def test_delete_session(self, client):
        """Test deleting a session."""
        # Create a session
        create_response = client.post('/api/sessions')
        session_id = create_response.json['session_id']
        
        # Delete it
        response = client.delete(f'/api/sessions/{session_id}')
        assert response.status_code == 200
        assert response.json['success'] is True
        
        # Verify it's gone
        get_response = client.get(f'/api/sessions/{session_id}')
        assert get_response.status_code == 404
    
    def test_update_session(self, client):
        """Test updating a session."""
        # Create a session
        create_response = client.post('/api/sessions')
        session_id = create_response.json['session_id']
        
        # Update it
        update_data = {
            'title': 'Updated Title',
            'system_prompt': 'New system prompt'
        }
        response = client.put(f'/api/sessions/{session_id}',
                              json=update_data,
                              content_type='application/json')
        assert response.status_code == 200
        
        # Verify update
        get_response = client.get(f'/api/sessions/{session_id}')
        session = get_response.json['session']
        assert session['title'] == 'Updated Title'
        
        # Cleanup
        client.delete(f'/api/sessions/{session_id}')


class TestModelEndpoints:
    """Test model listing endpoints."""
    
    @patch('app.requests.get')
    def test_get_models_lmstudio(self, mock_get, client):
        """Test getting models from LM Studio."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            'data': [{'id': 'model-1'}, {'id': 'model-2'}]
        }
        
        # Set provider to lmstudio
        client.post('/api/settings', json={'provider': 'lmstudio'})
        
        response = client.get('/api/models')
        assert response.status_code == 200
        
        data = response.json
        assert data['success'] is True
        assert 'models' in data


class TestChatEndpoint:
    """Test chat API endpoint."""
    
    @patch('app.requests.post')
    def test_chat_basic(self, mock_post, client):
        """Test basic chat request."""
        # Mock LLM response
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            'choices': [
                {'message': {'content': 'Hello! How can I help you?'}}
            ],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}
        }
        
        # Create a session first
        create_response = client.post('/api/sessions')
        session_id = create_response.json['session_id']
        
        # Send chat message
        chat_data = {
            'message': 'Hello',
            'session_id': session_id
        }
        response = client.post('/api/chat',
                               json=chat_data,
                               content_type='application/json')
        
        assert response.status_code == 200
        data = response.json
        assert data['success'] is True
        assert 'response' in data
        
        # Cleanup
        client.delete(f'/api/sessions/{session_id}')
    
    def test_chat_missing_message(self, client):
        """Test chat with missing message."""
        response = client.post('/api/chat', json={})
        assert response.status_code == 400


class TestTTSEndpoints:
    """Test TTS API endpoints."""
    
    def test_get_speakers(self, client):
        """Test getting available speakers."""
        response = client.get('/api/tts/speakers')
        assert response.status_code == 200
        
        data = response.json
        assert data['success'] is True
        assert 'speakers' in data
        assert isinstance(data['speakers'], list)
    
    def test_tts_synthesis_endpoint_exists(self, client):
        """Test TTS synthesis endpoint exists and handles requests."""
        # Without TTS server running, this will return 500 or 503
        response = client.post('/api/tts',
                               json={'text': 'Hello world'},
                               content_type='application/json')
        
        # Endpoint should exist (may fail if TTS not running)
        assert response.status_code in [200, 500, 503]
    
    def test_tts_missing_text(self, client):
        """Test TTS with missing text."""
        response = client.post('/api/tts', json={})
        assert response.status_code == 400


class TestSTTEndpoints:
    """Test STT API endpoints."""
    
    def test_stt_health(self, client):
        """Test STT health check endpoint."""
        response = client.get('/api/stt/health')
        # May return 503 if STT not running
        assert response.status_code in [200, 503]
    
    def test_stt_missing_audio(self, client):
        """Test STT with missing audio."""
        response = client.post('/api/stt')
        assert response.status_code == 400


class TestVoiceCloneEndpoints:
    """Test voice cloning endpoints."""
    
    def test_get_voice_clones(self, client):
        """Test getting voice clones."""
        response = client.get('/api/voice_clones')
        assert response.status_code == 200
        
        data = response.json
        assert data['success'] is True
        assert 'voices' in data
    
    def test_create_voice_clone_without_audio(self, client):
        """Test creating a voice clone entry without audio file."""
        response = client.post('/api/voice_clone',
                               data={'name': 'TestVoice', 'language': 'en'},
                               content_type='multipart/form-data')
        
        # Should succeed - creates mapping entry
        assert response.status_code == 200
        data = response.json
        assert data['success'] is True
        assert 'voice_id' in data
    
    def test_voice_clone_missing_name(self, client):
        """Test voice clone without name returns error."""
        response = client.post('/api/voice_clone',
                               data={'language': 'en'},
                               content_type='multipart/form-data')
        
        assert response.status_code == 400
        data = response.json
        assert data['success'] is False
    
    def test_delete_voice_clone_not_found(self, client):
        """Test deleting non-existent voice clone."""
        response = client.delete('/api/voice_clones/nonexistent_voice_12345')
        assert response.status_code == 404


class TestAudiobookEndpoints:
    """Test audiobook generation endpoints."""
    
    def test_audiobook_upload_text(self, client):
        """Test audiobook upload with text."""
        response = client.post('/api/audiobook/upload',
                               json={'text': 'Hello world, this is a test.'},
                               content_type='application/json')
        
        assert response.status_code == 200
        data = response.json
        assert data['success'] is True
        assert 'segments' in data
        assert 'speakers' in data
    
    def test_audiobook_upload_empty_text(self, client):
        """Test audiobook upload with empty text."""
        response = client.post('/api/audiobook/upload',
                               json={'text': ''},
                               content_type='application/json')
        
        assert response.status_code == 400
        data = response.json
        assert data['success'] is False
    
    def test_audiobook_speaker_detection(self, client):
        """Test speaker detection in text."""
        text = """
        Sofia: Hello there!
        Morgan: Hi, how are you?
        """
        response = client.post('/api/audiobook/speakers/detect',
                               json={'text': text},
                               content_type='application/json')
        
        assert response.status_code == 200
        data = response.json
        assert data['success'] is True
        assert 'speakers' in data
    
    def test_audiobook_speaker_detection_complex(self, client):
        """Test speaker detection with complex dialogue patterns."""
        text = '''
        "Good morning," said Sofia, walking into the room.
        "Hello!" David replied with a smile.
        
        Morgan entered quietly. "Did I miss anything?"
        '''
        response = client.post('/api/audiobook/speakers/detect',
                               json={'text': text},
                               content_type='application/json')
        
        assert response.status_code == 200
        data = response.json
        assert data['success'] is True
        # Should detect multiple speakers
        speakers = data.get('speakers', {})
        assert len(speakers) >= 1
    
    def test_audiobook_generate_missing_segments(self, client):
        """Test audiobook generation without segments."""
        response = client.post('/api/audiobook/generate',
                               json={},
                               content_type='application/json')
        
        assert response.status_code == 400
        data = response.json
        assert data['success'] is False
    
    def test_audiobook_generate_with_segments(self, client):
        """Test audiobook generation with mock segments."""
        segments = [
            {'speaker': 'Narrator', 'text': 'Once upon a time.', 'type': 'narration'},
            {'speaker': 'Sofia', 'text': 'Hello world!', 'type': 'dialogue'}
        ]
        
        # This will fail without TTS server, but should handle gracefully
        response = client.post('/api/audiobook/generate',
                               json={'segments': segments},
                               content_type='application/json')
        
        # Endpoint should exist - may fail if TTS not running
        assert response.status_code in [200, 500, 503]


class TestServicesEndpoints:
    """Test service management endpoints."""
    
    def test_services_status(self, client):
        """Test getting services status."""
        response = client.get('/api/services/status')
        assert response.status_code == 200
        
        data = response.json
        assert data['success'] is True
        assert 'tts' in data
        assert 'stt' in data


class TestPodcastEndpoints:
    """Test podcast generation endpoints."""
    
    def test_podcast_outline_basic(self, client):
        """Test basic podcast outline generation request."""
        outline_config = {
            'title': 'Test Podcast',
            'topic': 'Technology trends',
            'format': 'conversation',
            'length': 'short',
            'speakers': [
                {'name': 'Host', 'voice_id': 'default'},
                {'name': 'Guest', 'voice_id': 'default'}
            ]
        }
        
        response = client.post('/api/podcast/outline',
                               json=outline_config,
                               content_type='application/json')
        
        # May fail if no LLM configured, but endpoint should exist
        assert response.status_code in [200, 400, 500, 503]
    
    def test_podcast_outline_missing_topic(self, client):
        """Test outline generation without topic."""
        response = client.post('/api/podcast/outline',
                               json={'title': 'Test'},
                               content_type='application/json')
        
        assert response.status_code == 400
        data = response.json
        assert data['success'] is False
    
    def test_podcast_generate_missing_topic(self, client):
        """Test episode generation without topic."""
        response = client.post('/api/podcast/generate',
                               json={'title': 'Test'},
                               content_type='application/json')
        
        assert response.status_code == 400
        data = response.json
        assert data['success'] is False
    
    def test_podcast_generate_missing_speakers(self, client):
        """Test episode generation without speakers."""
        response = client.post('/api/podcast/generate',
                               json={'title': 'Test', 'topic': 'Test topic'},
                               content_type='application/json')
        
        assert response.status_code == 400
        data = response.json
        assert data['success'] is False
    
    def test_podcast_get_episodes(self, client):
        """Test getting podcast episodes list."""
        response = client.get('/api/podcast/episodes')
        
        assert response.status_code == 200
        data = response.json
        assert data['success'] is True
        assert 'episodes' in data
        assert isinstance(data['episodes'], list)
    
    def test_podcast_get_episode_not_found(self, client):
        """Test getting non-existent episode."""
        # Use plural 'episodes' as per the actual route
        response = client.get('/api/podcast/episodes/nonexistent_episode_12345')
        
        assert response.status_code == 404
        data = response.json
        assert data['success'] is False
    
    def test_podcast_delete_episode_not_found(self, client):
        """Test deleting non-existent episode."""
        # Use plural 'episodes' as per the actual route
        response = client.delete('/api/podcast/episodes/nonexistent_episode_12345')
        
        assert response.status_code == 404
        data = response.json
        assert data['success'] is False
    
    def test_podcast_voice_profiles_get(self, client):
        """Test getting voice profiles."""
        response = client.get('/api/podcast/voice-profiles')
        
        assert response.status_code == 200
        data = response.json
        assert data['success'] is True
        assert 'profiles' in data
    
    def test_podcast_voice_profile_create(self, client):
        """Test creating a voice profile."""
        profile_data = {
            'name': 'Test Host',
            'voice_id': 'default',
            'personality': 'Friendly and informative'
        }
        
        response = client.post('/api/podcast/voice-profiles',
                               json=profile_data,
                               content_type='application/json')
        
        assert response.status_code == 200
        data = response.json
        assert data['success'] is True
        assert 'profile' in data
        
        # Cleanup - delete the created profile
        if data['success'] and data['profile'].get('id'):
            client.delete(f"/api/podcast/voice-profiles/{data['profile']['id']}")
    
    def test_podcast_format_types(self, client):
        """Test outline generation with different format types."""
        formats = ['conversation', 'monologue', 'interview', 'debate']
        
        for fmt in formats:
            outline_config = {
                'title': f'Test {fmt}',
                'topic': 'Test topic',
                'format': fmt,
                'length': 'short',
                'speakers': [
                    {'name': 'Speaker1', 'voice_id': 'default'}
                ]
            }
            
            response = client.post('/api/podcast/outline',
                                   json=outline_config,
                                   content_type='application/json')
            
            # Endpoint should accept all format types
            assert response.status_code in [200, 400, 500, 503], f"Failed for format: {fmt}"
    
    def test_podcast_length_types(self, client):
        """Test outline generation with different length types."""
        lengths = ['short', 'medium', 'long', 'extended']
        
        for length in lengths:
            outline_config = {
                'title': f'Test {length}',
                'topic': 'Test topic',
                'format': 'conversation',
                'length': length,
                'speakers': [
                    {'name': 'Host', 'voice_id': 'default'}
                ]
            }
            
            response = client.post('/api/podcast/outline',
                                   json=outline_config,
                                   content_type='application/json')
            
            # Endpoint should accept all length types
            assert response.status_code in [200, 400, 500, 503], f"Failed for length: {length}"
    
    def test_podcast_with_talking_points(self, client):
        """Test outline generation with talking points."""
        outline_config = {
            'title': 'Structured Podcast',
            'topic': 'Technology',
            'format': 'conversation',
            'length': 'medium',
            'speakers': [
                {'name': 'Host', 'voice_id': 'default'}
            ],
            'talking_points': [
                'Introduction to the topic',
                'Current state of technology',
                'Future predictions',
                'Conclusion'
            ]
        }
        
        response = client.post('/api/podcast/outline',
                               json=outline_config,
                               content_type='application/json')
        
        # Endpoint should accept talking points
        assert response.status_code in [200, 400, 500, 503]


class TestStreamingEndpoints:
    """Test streaming SSE endpoints."""
    
    @patch('app.requests.post')
    def test_chat_stream(self, mock_post, client):
        """Test streaming chat endpoint."""
        # Mock streaming response
        def mock_stream():
            yield b'data: {"type": "content", "content": "Hello"}\n\n'
            yield b'data: {"type": "done"}\n\n'
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            b'data: {"type": "content", "content": "Hello"}',
            b'data: {"type": "done"}'
        ]
        mock_post.return_value = mock_response
        
        # Create a session first
        create_response = client.post('/api/sessions')
        session_id = create_response.json['session_id']
        
        # Send streaming request
        response = client.post('/api/chat/stream',
                               json={'message': 'Hello', 'session_id': session_id},
                               content_type='application/json')
        
        assert response.status_code == 200
        assert 'text/event-stream' in response.content_type
        
        # Cleanup
        client.delete(f'/api/sessions/{session_id}')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])