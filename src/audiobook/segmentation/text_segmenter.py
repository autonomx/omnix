import re
from typing import List


class TextSegmenter:
    """Intelligently segments large texts into LLM-friendly chunks."""

    MAX_CHARS = 3500

    # Patterns that indicate chapter or scene boundaries
    CHAPTER_PATTERN = re.compile(
        r'^\s*(chapter\s+\w+|part\s+\w+|section\s+\w+|prologue|epilogue)',
        re.IGNORECASE | re.MULTILINE,
    )

    def segment(self, text: str) -> List[str]:
        """Split text into segments respecting natural boundaries."""
        if not text:
            return [text]

        # Try chapter-level splits first
        chapter_splits = self._split_by_chapters(text)
        if len(chapter_splits) > 1:
            return self._enforce_max_size(chapter_splits)

        # Fall back to paragraph grouping, then sentence grouping
        return self._enforce_max_size(self._split_by_paragraphs(text))

    def _split_by_chapters(self, text: str) -> List[str]:
        parts = self.CHAPTER_PATTERN.split(text)
        if len(parts) <= 1:
            return [text]

        segments = []
        for i in range(0, len(parts), 2):
            chunk = parts[i]
            if i + 1 < len(parts):
                chunk = parts[i + 1] + chunk
            if chunk.strip():
                segments.append(chunk.strip())
        return segments if segments else [text]

    def _split_by_paragraphs(self, text: str) -> List[str]:
        paragraphs = re.split(r'\n\s*\n', text)
        segments: List[str] = []
        chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if chunk and len(chunk) + len(para) + 2 > self.MAX_CHARS:
                segments.append(chunk)
                chunk = para
            else:
                chunk = (chunk + "\n\n" + para).strip() if chunk else para

        if chunk:
            segments.append(chunk)

        return segments if segments else [text]

    def _split_by_sentences(self, text: str) -> List[str]:
        """Split a single long block by sentence boundaries."""
        sentence_ends = re.compile(r'(?<=[.!?])\s+')
        sentences = sentence_ends.split(text)
        segments: List[str] = []
        chunk = ""

        for sentence in sentences:
            if not sentence.strip():
                continue
            if chunk and len(chunk) + len(sentence) + 1 > self.MAX_CHARS:
                segments.append(chunk)
                chunk = sentence
            else:
                chunk = (chunk + " " + sentence).strip() if chunk else sentence

        if chunk:
            segments.append(chunk)

        return segments if segments else [text]

    def _enforce_max_size(self, segments: List[str]) -> List[str]:
        result: List[str] = []
        for seg in segments:
            if len(seg) <= self.MAX_CHARS:
                result.append(seg)
            else:
                # Try paragraph split first, then sentence split
                sub = self._split_by_paragraphs(seg)
                if len(sub) > 1:
                    result.extend(self._enforce_max_size(sub))
                else:
                    result.extend(self._split_by_sentences(seg))
        return result
