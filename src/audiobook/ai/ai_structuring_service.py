import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Callable

from audiobook.segmentation.text_segmenter import TextSegmenter
from audiobook.segmentation.scene_detector import SceneDetector
from audiobook.ai.speaker_tracker import SpeakerTracker
from audiobook.ai.character_extractor import CharacterExtractor
from audiobook.ai.emotion_detector import EmotionDetector

STRUCTURE_PROMPT = """You are converting story text into an audiobook dialogue format.

Rules:
- Never summarize or remove any text.
- Preserve all words exactly as written.
- Narration text must use speaker "Narrator".
- Dialogue must be assigned to the speaking character by name.
- If the speaker of a quoted line cannot be determined, use "Narrator".
- Maintain strict chronological order.
- IMPORTANT: When a line contains both quoted dialogue AND narration (such as attribution tags like "said Tom" or action descriptions like "raising his coffee mug"), you MUST split them into separate entries. The quoted dialogue goes to the character, and the surrounding narration goes to "Narrator".
  Example input: "Heartless," said Tom, raising his coffee mug. "We're loyal customers."
  Correct output:
    {{"speaker": "Tom", "text": "Heartless,"}},
    {{"speaker": "Narrator", "text": "said Tom, raising his coffee mug."}},
    {{"speaker": "Tom", "text": "We're loyal customers."}}

Return ONLY valid JSON with this exact format:
{{
  "script": [
    {{"speaker": "Narrator", "text": ""}},
    {{"speaker": "CharacterName", "text": ""}}
  ]
}}

Text:
{input_text}
"""


def _parse_json_response(raw: str) -> Optional[List[Dict]]:
    """Extract the script array from an LLM JSON response."""
    # Try direct parse first
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "script" in data:
            return data["script"]
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Try to extract JSON object
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if "script" in data:
                return data["script"]
        except json.JSONDecodeError:
            pass

    return None


class AIStructuringService:
    """Converts raw story text into structured audiobook script using LLM."""

    MAX_RETRIES = 2

    def __init__(self, llm_fn: Optional[Callable[[str], str]] = None) -> None:
        """
        Args:
            llm_fn: Callable that accepts a prompt string and returns the LLM response.
                    If None, falls back to regex-based parsing.
        """
        self._llm = llm_fn
        self._segmenter = TextSegmenter()
        self._scene_detector = SceneDetector()
        self._speaker_tracker = SpeakerTracker()
        self._char_extractor = CharacterExtractor()

    def structure(self, text: str, title: str = "") -> Dict:
        """Parse *text* into a full directed script dict.

        Returns canonical JSON format:
        {
            "title": str,
            "characters": [...],
            "segments": [{"scene": int, "script": [...]}]
        }
        """
        segments = self._segmenter.segment(text)
        scenes = self._scene_detector.detect(segments)

        structured_scenes = []
        all_lines: List[Dict] = []

        # Process segments in parallel (max 4 workers)
        segment_results: Dict[int, List[Dict]] = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            future_map = {}
            flat_idx = 0
            for scene in scenes:
                for seg_text in scene["segments"]:
                    future = pool.submit(self._structure_segment, seg_text)
                    future_map[future] = (scene["scene_id"], flat_idx)
                    flat_idx += 1

            for future in as_completed(future_map):
                scene_id, idx = future_map[future]
                lines = future.result()
                if scene_id not in segment_results:
                    segment_results[scene_id] = []
                segment_results[scene_id].extend(lines)
                all_lines.extend(lines)

        for scene in scenes:
            sid = scene["scene_id"]
            scene_lines = segment_results.get(sid, [])
            structured_scenes.append({
                "scene": sid,
                "script": scene_lines,
            })

        characters = self._char_extractor.extract(all_lines)

        result = {
            "title": title,
            "characters": characters,
            "segments": structured_scenes,
        }

        # Dump structured script for debugging
        try:
            import hashlib
            debug_id = hashlib.md5(title.encode() if title else b"default").hexdigest()[:8]
            debug_path = f"/tmp/audiobook_structured_{debug_id}.json"
            with open(debug_path, "w", encoding="utf-8") as _fh:
                json.dump(result, _fh, indent=2)
        except Exception:
            pass

        return result

    def _structure_segment(self, text: str) -> List[Dict]:
        """Structure a single text segment into script lines."""
        if self._llm:
            for attempt in range(self.MAX_RETRIES):
                try:
                    lines = self._llm_structure(text)
                    if lines and self._validate_output(text, lines):
                        return lines
                except Exception:
                    pass

        return self._regex_fallback(text)

    def _llm_structure(self, text: str) -> Optional[List[Dict]]:
        prompt = STRUCTURE_PROMPT.format(input_text=text)
        raw = self._llm(prompt)  # type: ignore[misc]
        return _parse_json_response(raw)

    def _validate_output(self, original: str, lines: List[Dict]) -> bool:
        """Ensure the structured output preserves enough of the original text."""
        combined = " ".join(ln.get("text", "") for ln in lines)
        if not original.strip():
            return True
        ratio = len(combined) / len(original)
        return ratio >= 0.85

    def _regex_fallback(self, text: str) -> List[Dict]:
        """Simple regex-based fallback parser matching audiobook.py logic."""
        from app.audiobook import parse_dialogue  # type: ignore[import]
        return parse_dialogue(text)
