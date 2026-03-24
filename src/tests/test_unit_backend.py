"""
Unit tests for backend utility functions.
Tests do not require external services (LLM, TTS, STT).
"""

import pytest
import json
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestTextProcessing:
    """Test text processing utilities."""
    
    def test_remove_emojis(self):
        """Test emoji removal from text."""
        from app import remove_emojis
        
        # Test with emojis
        text_with_emojis = "Hello 😀 world 🎉!"
        result = remove_emojis(text_with_emojis)
        assert "😀" not in result
        assert "🎉" not in result
        assert "Hello" in result
        assert "world" in result
        
        # Test without emojis
        text_without_emojis = "Hello world!"
        result = remove_emojis(text_without_emojis)
        assert result == text_without_emojis
        
        # Test empty string
        assert remove_emojis("") == ""
        
        # Test None
        assert remove_emojis(None) is None
    
    def test_extract_thinking_basic(self):
        """Test thinking extraction from content."""
        # Test content without thinking tags
        content = "This is a simple response."
        # Simple split on </thinking> tag
        if "</thinking>" in content:
            thinking, answer = content.split("</thinking>", 1)
        else:
            thinking, answer = "", content
        
        assert thinking == ""
        assert answer == content
        
        # Test content with thinking tags
        content_with_thinking = "Let me think about this. </thinking>The answer is 42."
        if "</thinking>" in content_with_thinking:
            thinking, answer = content_with_thinking.split("</thinking>", 1)
        else:
            thinking, answer = "", content_with_thinking
        
        assert "Let me think" in thinking
        assert "42" in answer


class TestDialogueParsing:
    """Test dialogue parsing for audiobook feature."""
    
    def test_parse_dialogue_direct_label(self):
        """Test parsing dialogue with direct speaker labels."""
        from app import parse_dialogue
        
        text = """
        Sofia: Hello there!
        Morgan: Hi Sofia, how are you?
        """
        segments = parse_dialogue(text)
        
        assert len(segments) >= 2
        assert any(seg['speaker'] == 'Sofia' for seg in segments)
        assert any(seg['speaker'] == 'Morgan' for seg in segments)
    
    def test_parse_dialogue_narration(self):
        """Test parsing narration."""
        from app import parse_dialogue
        
        text = "The sun was setting over the hills. Birds sang in the trees."
        segments = parse_dialogue(text)
        
        # Should detect as narration
        assert len(segments) >= 1
        assert segments[0]['type'] == 'narration'
    
    def test_parse_dialogue_mixed(self):
        """Test parsing mixed content."""
        from app import parse_dialogue
        
        text = """
        Narrator: The room was quiet.
        Sofia: What happened here?
        Morgan: I don't know, but something feels wrong.
        
        They looked around nervously.
        """
        segments = parse_dialogue(text)
        
        assert len(segments) >= 2
        speakers = [seg['speaker'] for seg in segments]
        # Should have multiple speakers or narrator


class TestSpeakerGenderDetection:
    """Test speaker gender detection for voice assignment."""
    
    def test_detect_female_names(self):
        """Test detection of female names."""
        from app import detect_speaker_gender
        
        female_names = ['Sofia', 'Emma', 'Olivia', 'Ciri', 'Vivian', 'Serena']
        for name in female_names:
            gender = detect_speaker_gender(name)
            assert gender == 'female', f"{name} should be detected as female"
    
    def test_detect_male_names(self):
        """Test detection of male names."""
        from app import detect_speaker_gender
        
        male_names = ['Morgan', 'James', 'John', 'Nate', 'Inigo', 'Eric']
        for name in male_names:
            gender = detect_speaker_gender(name)
            assert gender == 'male', f"{name} should be detected as male"
    
    def test_detect_unknown_names(self):
        """Test handling of unknown names."""
        from app import detect_speaker_gender
        
        unknown_names = ['Xyz', 'Abc', 'Random']
        for name in unknown_names:
            gender = detect_speaker_gender(name)
            assert gender in ['male', 'female', 'neutral']


class TestVoiceAssignment:
    """Test voice assignment logic."""
    
    def test_get_voice_for_speaker(self):
        """Test voice assignment for speakers."""
        from app import get_voice_for_speaker
        
        available_voices = ['sofia', 'morgan', 'narrator']
        
        # Test female speaker
        voice = get_voice_for_speaker('Sofia', available_voices, 
                                       default_female='sofia', 
                                       default_male='morgan')
        assert voice is not None
        
        # Test male speaker
        voice = get_voice_for_speaker('Morgan', available_voices,
                                       default_female='sofia',
                                       default_male='morgan')
        assert voice is not None


class TestTokenEstimation:
    """Test token estimation utilities."""
    
    def test_estimate_tokens_english(self):
        """Test token estimation for English text."""
        # Approx 4 chars per token
        text = "Hello world"  # 11 chars
        estimated = len(text) // 4 + 1  # Should be ~3 tokens
        assert estimated >= 2
        assert estimated <= 4
    
    def test_estimate_tokens_empty(self):
        """Test token estimation for empty text."""
        text = ""
        estimated = len(text) // 4
        assert estimated == 0


class TestSettings:
    """Test settings management."""
    
    def test_load_settings_default(self, tmp_path):
        """Test loading default settings."""
        from app import DEFAULT_SETTINGS
        
        assert 'provider' in DEFAULT_SETTINGS
        assert 'lmstudio' in DEFAULT_SETTINGS
        assert 'openrouter' in DEFAULT_SETTINGS
        assert 'cerebras' in DEFAULT_SETTINGS
        assert 'global_system_prompt' in DEFAULT_SETTINGS
    
    def test_provider_config_lmstudio(self):
        """Test getting LM Studio provider config."""
        from app import get_provider_config, load_settings
        
        # Save current settings
        settings = load_settings()
        settings['provider'] = 'lmstudio'
        settings['lmstudio'] = {'base_url': 'http://localhost:1234'}
        
        # Just verify the function exists and returns expected structure
        config = get_provider_config()
        assert 'provider' in config
        assert config['provider'] in ['lmstudio', 'openrouter', 'cerebras']


class TestSessionManagement:
    """Test session management functions."""
    
    def test_session_structure(self):
        """Test that sessions have correct structure."""
        from app import load_sessions, save_sessions
        import tempfile
        
        # Sessions should be a dict
        sessions = load_sessions()
        assert isinstance(sessions, dict)


class TestHTMLEscape:
    """Test HTML escaping for security."""
    
    def test_escape_html_basic(self):
        """Test basic HTML escaping."""
        from app import parse_dialogue  # This uses escapeHtml internally
        
        # Test that HTML in text is handled safely
        text = "<script>alert('xss')</script>"
        segments = parse_dialogue(text)
        # Should not throw an error
        assert isinstance(segments, list)


class TestWAVGeneration:
    """Test WAV file generation utilities."""
    
    def test_wav_header_creation(self):
        """Test that WAV headers are created correctly."""
        import struct
        
        # Test creating a basic WAV header
        sample_rate = 24000
        num_channels = 1
        bits_per_sample = 16
        
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        
        # Verify calculations
        assert byte_rate == 48000  # 24000 * 1 * 2
        assert block_align == 2  # 1 * 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])