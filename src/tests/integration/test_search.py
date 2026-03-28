"""
Tests for the chat search functionality.

This module tests:
1. Session API endpoints used by search (GET /sessions, GET /sessions/{id})
2. Session message storage and retrieval
3. Search query handling
"""

import pytest
import json
from unittest.mock import patch, MagicMock


class TestSearchSessionEndpoints:
    """Test session endpoints used by the search functionality."""
    
    def test_get_sessions_returns_list(self, client):
        """Test that /api/sessions returns a list of sessions."""
        response = client.get('/api/sessions')
        assert response.status_code == 200
        
        data = response.json
        assert data['success'] is True
        assert 'sessions' in data
        assert isinstance(data['sessions'], list)
    
    def test_get_sessions_includes_metadata(self, client):
        """Test that sessions include metadata needed for search."""
        # Create a session with messages
        create_response = client.post('/api/sessions')
        session_id = create_response.json['session_id']
        
        # Send a chat message to create content
        with patch('app.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                'choices': [{'message': {'content': 'Test response'}}],
                'usage': {'prompt_tokens': 5, 'completion_tokens': 10, 'total_tokens': 15}
            }
            
            chat_response = client.post('/api/chat',
                json={'message': 'Hello', 'session_id': session_id},
                content_type='application/json')
        
        # Get sessions list
        response = client.get('/api/sessions')
        data = response.json
        
        # Verify we can get session IDs from the list
        assert len(data['sessions']) > 0
        
        # Get the session ID from first session
        first_session = data['sessions'][0]
        assert 'id' in first_session
        
        # Cleanup
        client.delete(f'/api/sessions/{session_id}')
    
    def test_get_session_by_id_includes_messages(self, client):
        """Test that getting a session by ID includes messages for search."""
        # Create a session
        create_response = client.post('/api/sessions')
        session_id = create_response.json['session_id']
        
        # Add messages to the session
        with patch('app.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                'choices': [{'message': {'content': 'This is a test response with searchable content'}}],
                'usage': {'prompt_tokens': 5, 'completion_tokens': 10, 'total_tokens': 15}
            }
            
            client.post('/api/chat',
                json={'message': 'Test message', 'session_id': session_id},
                content_type='application/json')
        
        # Get the session by ID
        response = client.get(f'/api/sessions/{session_id}')
        data = response.json
        
        assert data['success'] is True
        assert 'session' in data
        
        session = data['session']
        assert 'messages' in session
        assert len(session['messages']) > 0
        
        # Verify message structure
        first_message = session['messages'][0]
        assert 'role' in first_message
        assert 'content' in first_message
        
        # Cleanup
        client.delete(f'/api/sessions/{session_id}')
    
    def test_search_scenario_user_message_found(self, client):
        """Test searching finds user messages."""
        # Create session and add specific user message
        create_response = client.post('/api/sessions')
        session_id = create_response.json['session_id']
        
        # Add user message with unique search term
        unique_term = "xyzsearchterm123"
        
        with patch('app.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                'choices': [{'message': {'content': 'AI response'}}],
                'usage': {'prompt_tokens': 5, 'completion_tokens': 10, 'total_tokens': 15}
            }
            
            client.post('/api/chat',
                json={'message': f'User said {unique_term}', 'session_id': session_id},
                content_type='application/json')
        
        # Fetch session and verify message contains search term
        response = client.get(f'/api/sessions/{session_id}')
        session = response.json['session']
        
        # Find the user message
        user_messages = [m for m in session['messages'] if m['role'] == 'user']
        assert len(user_messages) > 0
        
        # Check search term is present
        found = any(unique_term in m['content'] for m in user_messages)
        assert found, f"Search term '{unique_term}' not found in user messages"
        
        # Cleanup
        client.delete(f'/api/sessions/{session_id}')
    
    def test_search_scenario_ai_message_found(self, client):
        """Test searching finds AI messages."""
        # Create session
        create_response = client.post('/api/sessions')
        session_id = create_response.json['session_id']
        
        # Add AI message with unique search term
        unique_term = "aisearchterm456"
        
        with patch('app.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                'choices': [{'message': {'content': f'AI says {unique_term}'}}],
                'usage': {'prompt_tokens': 5, 'completion_tokens': 10, 'total_tokens': 15}
            }
            
            client.post('/api/chat',
                json={'message': 'Hello', 'session_id': session_id},
                content_type='application/json')
        
        # Fetch session and verify AI message contains search term
        response = client.get(f'/api/sessions/{session_id}')
        session = response.json['session']
        
        # Find the AI message
        ai_messages = [m for m in session['messages'] if m['role'] == 'assistant']
        assert len(ai_messages) > 0
        
        # Check search term is present
        found = any(unique_term in m['content'] for m in ai_messages)
        assert found, f"Search term '{unique_term}' not found in AI messages"
        
        # Cleanup
        client.delete(f'/api/sessions/{session_id}')
    
    def test_search_case_insensitive(self, client):
        """Test that search is case insensitive."""
        create_response = client.post('/api/sessions')
        session_id = create_response.json['session_id']
        
        with patch('app.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                'choices': [{'message': {'content': 'UPPERCASE SEARCH'}}],
                'usage': {'prompt_tokens': 5, 'completion_tokens': 10, 'total_tokens': 15}
            }
            
            client.post('/api/chat',
                json={'message': 'lowercase search', 'session_id': session_id},
                content_type='application/json')
        
        # Fetch session
        response = client.get(f'/api/sessions/{session_id}')
        session = response.json['session']
        
        # Check case-insensitive search would work
        all_content = ' '.join(m['content'].lower() for m in session['messages'])
        
        assert 'uppercase search' in all_content
        assert 'lowercase search' in all_content
        
        # Cleanup
        client.delete(f'/api/sessions/{session_id}')
    
    def test_search_multiple_sessions(self, client):
        """Test search across multiple sessions."""
        session_ids = []
        
        # Create multiple sessions with different content
        for i in range(3):
            create_response = client.post('/api/sessions')
            session_id = create_response.json['session_id']
            session_ids.append(session_id)
            
            with patch('app.requests.post') as mock_post:
                mock_post.return_value.status_code = 200
                mock_post.return_value.json.return_value = {
                    'choices': [{'message': {'content': f'Response from session {i}'}}],
                    'usage': {'prompt_tokens': 5, 'completion_tokens': 10, 'total_tokens': 15}
                }
                
                client.post('/api/chat',
                    json={'message': f'Message in session {i}', 'session_id': session_id},
                    content_type='application/json')
        
        # Get all sessions
        response = client.get('/api/sessions')
        data = response.json
        
        assert len(data['sessions']) >= 3
        
        # Search in each session
        for session_id in session_ids:
            response = client.get(f'/api/sessions/{session_id}')
            session = response.json['session']
            assert 'messages' in session
        
        # Cleanup
        for session_id in session_ids:
            client.delete(f'/api/sessions/{session_id}')
    
    def test_empty_session_search(self, client):
        """Test searching in empty session returns no messages."""
        create_response = client.post('/api/sessions')
        session_id = create_response.json['session_id']
        
        # Get session without any messages
        response = client.get(f'/api/sessions/{session_id}')
        session = response.json['session']
        
        assert 'messages' in session
        assert len(session['messages']) == 0
        
        # Cleanup
        client.delete(f'/api/sessions/{session_id}')


class TestSearchAPIIntegration:
    """Integration tests simulating the frontend search workflow."""
    
    def test_search_workflow_full(self, client):
        """Test the complete search workflow as the frontend does it."""
        # Step 1: Create a session with searchable content
        create_response = client.post('/api/sessions')
        session_id = create_response.json['session_id']
        
        search_term = "uniquepythoncode789"
        
        with patch('app.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                'choices': [{'message': {'content': f'Here is some {search_term} in the response'}}],
                'usage': {'prompt_tokens': 5, 'completion_tokens': 10, 'total_tokens': 15}
            }
            
            client.post('/api/chat',
                json={'message': 'Tell me about python', 'session_id': session_id},
                content_type='application/json')
        
        # Step 2: Get all sessions (like frontend does)
        sessions_response = client.get('/api/sessions')
        sessions = sessions_response.json['sessions']
        
        # Step 3: For each session, fetch full details (like frontend does)
        found_results = []
        
        for session in sessions:
            session_id_to_check = session['id']
            
            session_response = client.get(f'/api/sessions/{session_id_to_check}')
            if session_response.status_code == 200:
                session_data = session_response.json
                if session_data.get('success') and 'session' in session_data:
                    full_session = session_data['session']
                    
                    # Search in messages (like frontend does)
                    if 'messages' in full_session:
                        for msg in full_session['messages']:
                            if 'content' in msg and search_term in msg['content'].lower():
                                found_results.append({
                                    'session_id': session_id_to_check,
                                    'role': msg.get('role'),
                                    'content': msg['content']
                                })
        
        # Step 4: Verify we found the search term
        assert len(found_results) > 0, f"Search term '{search_term}' not found"
        
        # Verify the content contains our search term
        assert any(search_term in r['content'] for r in found_results)
        
        # Cleanup
        client.delete(f'/api/sessions/{session_id}')
    
    def test_search_no_results(self, client):
        """Test search that finds no results."""
        # Create session with known content
        create_response = client.post('/api/sessions')
        session_id = create_response.json['session_id']
        
        with patch('app.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                'choices': [{'message': {'content': 'This is about cats'}}],
                'usage': {'prompt_tokens': 5, 'completion_tokens': 10, 'total_tokens': 15}
            }
            
            client.post('/api/chat',
                json={'message': 'Tell me about cats', 'session_id': session_id},
                content_type='application/json')
        
        # Search for something not in the content
        search_term = "nonexistentdogquery123"
        
        # Get session
        response = client.get(f'/api/sessions/{session_id}')
        session = response.json['session']
        
        # Check search term is NOT present
        found = False
        if 'messages' in session:
            for msg in session['messages']:
                if 'content' in msg and search_term in msg['content']:
                    found = True
                    break
        
        assert not found, "Search term should not be found"
        
        # Cleanup
        client.delete(f'/api/sessions/{session_id}')
    
    def test_search_special_characters(self, client):
        """Test search with special characters."""
        create_response = client.post('/api/sessions')
        session_id = create_response.json['session_id']
        
        special_term = "test@email.com"
        
        with patch('app.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                'choices': [{'message': {'content': f'Contact: {special_term}'}}],
                'usage': {'prompt_tokens': 5, 'completion_tokens': 10, 'total_tokens': 15}
            }
            
            client.post('/api/chat',
                json={'message': 'What is your email?', 'session_id': session_id},
                content_type='application/json')
        
        # Search for special character term
        response = client.get(f'/api/sessions/{session_id}')
        session = response.json['session']
        
        # Verify special character search works
        content_text = ' '.join(m.get('content', '') for m in session.get('messages', []))
        assert special_term in content_text
        
        # Cleanup
        client.delete(f'/api/sessions/{session_id}')


class TestSearchEdgeCases:
    """Test edge cases for search functionality."""
    
    def test_very_long_message_search(self, client):
        """Test searching in very long messages."""
        create_response = client.post('/api/sessions')
        session_id = create_response.json['session_id']
        
        # Create long content
        long_content = "word " * 1000 + "uniquelongterm999" + " word" * 1000
        
        with patch('app.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                'choices': [{'message': {'content': long_content}}],
                'usage': {'prompt_tokens': 5, 'completion_tokens': 1000, 'total_tokens': 1005}
            }
            
            client.post('/api/chat',
                json={'message': 'Long response', 'session_id': session_id},
                content_type='application/json')
        
        # Search should still find the term
        response = client.get(f'/api/sessions/{session_id}')
        session = response.json['session']
        
        found = any('uniquelongterm999' in m.get('content', '') for m in session.get('messages', []))
        assert found
        
        # Cleanup
        client.delete(f'/api/sessions/{session_id}')
    
    def test_unicode_content_search(self, client):
        """Test searching in unicode content."""
        create_response = client.post('/api/sessions')
        session_id = create_response.json['session_id']
        
        unicode_term = "日本語テスト"
        
        with patch('app.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                'choices': [{'message': {'content': f'Content: {unicode_term}'}}],
                'usage': {'prompt_tokens': 5, 'completion_tokens': 10, 'total_tokens': 15}
            }
            
            client.post('/api/chat',
                json={'message': 'Japanese', 'session_id': session_id},
                content_type='application/json')
        
        # Search should find unicode
        response = client.get(f'/api/sessions/{session_id}')
        session = response.json['session']
        
        content_text = ' '.join(m.get('content', '') for m in session.get('messages', []))
        assert unicode_term in content_text
        
        # Cleanup
        client.delete(f'/api/sessions/{session_id}')
    
    def test_deleted_session_not_searchable(self, client):
        """Test that deleted sessions cannot be searched."""
        # Create and delete a session
        create_response = client.post('/api/sessions')
        session_id = create_response.json['session_id']
        
        # Delete it
        client.delete(f'/api/sessions/{session_id}')
        
        # Try to get it (should fail)
        response = client.get(f'/api/sessions/{session_id}')
        assert response.status_code == 404


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
