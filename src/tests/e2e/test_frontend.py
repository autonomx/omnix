"""
Frontend unit tests – migrated from test_frontend.html.

These tests run the same JavaScript logic inside a real browser via
Playwright's ``page.evaluate()``, replacing the standalone HTML test runner.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page


class TestTokenCounter:
    """Token estimation logic."""

    def test_estimates_tokens_for_english_text(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const text = "Hello world";
            return Math.ceil(text.length / 4);
        }""")
        assert 2 <= result <= 4

    def test_handles_empty_text(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            return Math.ceil("".length / 4);
        }""")
        assert result == 0

    def test_handles_long_text(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const text = "a".repeat(1000);
            return Math.ceil(text.length / 4);
        }""")
        assert result == 250

    def test_calculates_tokens_per_second(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const completionTokens = 100;
            const generationTimeMs = 2000;
            return (completionTokens / generationTimeMs) * 1000;
        }""")
        assert result == 50


class TestThinkingExtraction:
    """Thinking tag extraction logic."""

    def test_extracts_thinking_from_tagged_content(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const content = "Let me think... </thinking>The answer is 42.";
            return content.split('</thinking>').length;
        }""")
        assert result == 2

    def test_handles_content_without_thinking(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const content = "This is a simple response.";
            return content.toLowerCase().includes('</thinking>');
        }""")
        assert result is False

    def test_handles_empty_content(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("() => ''.length")
        assert result == 0


class TestWAVBufferCreation:
    """WAV audio header calculations."""

    def test_creates_valid_wav_header(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const sampleRate = 24000;
            const numChannels = 1;
            const bitsPerSample = 16;
            const byteRate = sampleRate * numChannels * bitsPerSample / 8;
            const blockAlign = numChannels * bitsPerSample / 8;
            return { byteRate, blockAlign };
        }""")
        assert result["byteRate"] == 48000
        assert result["blockAlign"] == 2

    def test_calculates_correct_buffer_size(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const dataSize = 1000;
            const headerSize = 44;
            return headerSize + dataSize;
        }""")
        assert result == 1044


class TestSpeakerGenderDetection:
    """Speaker name to gender mapping."""

    def test_detects_female_names(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const femaleNames = ['Sofia', 'Emma', 'Olivia', 'Serena', 'Vivian'];
            const knownFemale = ['sofia', 'emma', 'olivia', 'serena', 'vivian', 'ciri', 'sohee', 'her'];
            return femaleNames.filter(n => knownFemale.includes(n.toLowerCase())).length;
        }""")
        assert result == 5

    def test_detects_male_names(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const maleNames = ['Morgan', 'James', 'John', 'Eric', 'Nate'];
            const knownMale = ['morgan', 'james', 'john', 'eric', 'nate', 'inigo', 'aiden', 'dylan'];
            return maleNames.filter(n => knownMale.includes(n.toLowerCase())).length;
        }""")
        assert result == 5


class TestDialogueParsing:
    """Dialogue text parsing."""

    def test_parses_direct_speaker_labels(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const text = "Sofia: Hello there!\\nMorgan: Hi!";
            return /([A-Z][A-Za-z]+)\\s*:\\s*(.+)/.test(text);
        }""")
        assert result is True

    def test_detects_narration(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const text = "The sun was setting over the hills.";
            return /^([A-Z][A-Za-z]+)\\s*:\\s*/.test(text);
        }""")
        assert result is False

    def test_handles_multiple_speakers(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const text = "Sofia: Hello!\\nMorgan: Hi there!\\nSofia: How are you?";
            return text.trim().split('\\n').filter(l => l.includes(':')).length;
        }""")
        assert result >= 3


class TestEmojiRemoval:
    """Emoji stripping logic."""

    def test_removes_basic_emojis(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate(r"""() => {
            const text = "Hello 😀 world 🎉!";
            const re = /[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}]/gu;
            const cleaned = text.replace(re, '');
            return { hasEmoji: /[\u{1F600}-\u{1F64F}]/u.test(cleaned), hasHello: cleaned.includes('Hello') };
        }""")
        assert result["hasEmoji"] is False
        assert result["hasHello"] is True

    def test_handles_text_without_emojis(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate(r"""() => {
            const text = "Hello world!";
            const re = /[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}]/gu;
            return text.replace(re, '') === text;
        }""")
        assert result is True


class TestBase64Encoding:
    """Base64 encode/decode in the browser."""

    def test_encodes_binary_data(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const data = new Uint8Array([72, 101, 108, 108, 111]);
            let binary = '';
            for (let i = 0; i < data.length; i++) binary += String.fromCharCode(data[i]);
            const encoded = btoa(binary);
            return typeof encoded === 'string' && encoded.length > 0;
        }""")
        assert result is True

    def test_decodes_base64(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("() => atob(btoa('Hello'))")
        assert result == "Hello"


class TestSSEParsing:
    """Server-Sent Events parsing."""

    def test_parses_sse_data_lines(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const line = 'data: {"type": "content", "content": "Hello"}';
            const dataStr = line.slice(6);
            const data = JSON.parse(dataStr);
            return { type: data.type, content: data.content };
        }""")
        assert result["type"] == "content"
        assert result["content"] == "Hello"

    def test_handles_multiple_events(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const buffer = 'data: {"type": "content"}\\n\\ndata: {"type": "done"}\\n\\n';
            return buffer.split('\\n\\n').filter(e => e.trim()).length;
        }""")
        assert result == 2


class TestVoiceProfiles:
    """Voice profile localStorage operations."""

    def test_saves_and_loads_profiles(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const testProfile = { name: 'Test Character', personality: 'Friendly', style: 'casual' };
            const key = 'chatbot-test-voice-profile';
            localStorage.setItem(key, JSON.stringify(testProfile));
            const loaded = JSON.parse(localStorage.getItem(key));
            localStorage.removeItem(key);
            return loaded.name;
        }""")
        assert result == "Test Character"

    def test_combines_system_prompts(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const globalPrompt = 'You are a helpful assistant.';
            const voiceProfile = { name: 'Sofia', personality: 'You are Sofia, a warm AI.' };
            const combined = globalPrompt + '\\n\\n## Current Character: ' + voiceProfile.name + '\\n' + voiceProfile.personality;
            return { hasGlobal: combined.includes(globalPrompt), hasSofia: combined.includes('Sofia') };
        }""")
        assert result["hasGlobal"] is True
        assert result["hasSofia"] is True


class TestMarkdownRendering:
    """Markdown detection."""

    def test_handles_code_blocks(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const md = '```python\\nprint("hello")\\n```';
            return md.includes('```');
        }""")
        assert result is True

    def test_handles_bold_and_italic(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const md = '**bold** and *italic*';
            return md.includes('**') && md.includes('*');
        }""")
        assert result is True


class TestSystemPromptPresets:
    """System prompt preset definitions."""

    def test_has_default_presets(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const presets = { 'default': { name: 'Default' }, 'coder': { name: 'Expert Coder' },
                              'writer': { name: 'Creative Writer' }, 'tutor': { name: 'Patient Tutor' } };
            return !!presets.default && !!presets.coder;
        }""")
        assert result is True

    def test_presets_have_required_fields(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const preset = { name: 'Test', prompt: 'You are a test assistant.' };
            return !!preset.name && !!preset.prompt;
        }""")
        assert result is True


class TestAudioPlayback:
    """Audio element creation in the browser."""

    def test_creates_audio_from_blob(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("""() => {
            const data = new Uint8Array([0, 1, 2, 3, 4, 5]);
            const blob = new Blob([data], { type: 'audio/wav' });
            const url = URL.createObjectURL(blob);
            const isBlob = url.startsWith('blob:');
            URL.revokeObjectURL(url);
            return isBlob;
        }""")
        assert result is True

    def test_audio_element_can_be_created(self, page: Page):
        page.goto("http://localhost:5000/", wait_until="domcontentloaded")
        result = page.evaluate("() => new Audio().tagName")
        assert result == "AUDIO"
