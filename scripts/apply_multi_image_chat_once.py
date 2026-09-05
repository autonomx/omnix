from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _path(relative: str) -> Path:
    return ROOT / relative


def replace_once(relative: str, old: str, new: str) -> None:
    path = _path(relative)
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{relative}: expected one occurrence, found {count}: {old[:160]!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def regex_replace_once(relative: str, pattern: str, replacement: str, *, flags: int = re.S) -> None:
    path = _path(relative)
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"{relative}: expected one regex match, found {count}: {pattern[:160]!r}")
    path.write_text(updated, encoding="utf-8")


def append_once(relative: str, marker: str, addition: str) -> None:
    path = _path(relative)
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    path.write_text(text.rstrip() + "\n\n" + addition.strip() + "\n", encoding="utf-8")


def patch_chat_contract() -> None:
    relative = "src/app/chat/models.py"
    replace_once(
        relative,
        '_MAX_CHAT_IMAGE_DATA_URL_CHARS = 8_000_000\n_MAX_CHAT_TEXT_ATTACHMENT_CHARS = 100_000',
        '_MAX_CHAT_IMAGE_DATA_URL_CHARS = 8_000_000\n_MAX_CHAT_IMAGE_ATTACHMENTS = 8\n_MAX_CHAT_TEXT_ATTACHMENT_CHARS = 100_000',
    )
    replace_once(
        relative,
        '''_SUPPORTED_CHAT_IMAGE_PREFIXES = (\n    "data:image/png;base64,",\n    "data:image/jpeg;base64,",\n    "data:image/webp;base64,",\n)''',
        '''_SUPPORTED_CHAT_IMAGE_PREFIXES = (\n    "data:image/png;base64,",\n    "data:image/jpeg;base64,",\n    "data:image/webp;base64,",\n)\n\n\ndef _normalize_chat_image_data_url(value: str | None) -> str | None:\n    if value is None:\n        return None\n    normalized = value.strip()\n    if not normalized:\n        return None\n    if len(normalized) > _MAX_CHAT_IMAGE_DATA_URL_CHARS:\n        raise ValueError("image data URL is too large")\n    prefix = next(\n        (candidate for candidate in _SUPPORTED_CHAT_IMAGE_PREFIXES if normalized.startswith(candidate)),\n        None,\n    )\n    if prefix is None:\n        raise ValueError("image data URL must be a PNG, JPEG, or WebP data URL")\n    try:\n        base64.b64decode(normalized[len(prefix):], validate=True)\n    except (binascii.Error, ValueError) as error:\n        raise ValueError("image data URL must contain valid base64 data") from error\n    return normalized''',
    )
    replace_once(
        relative,
        '    image_data_url: str | None = Field(default=None, max_length=_MAX_CHAT_IMAGE_DATA_URL_CHARS)\n    text_attachment: ChatTextAttachment | None = None',
        '    image_data_url: str | None = Field(default=None, max_length=_MAX_CHAT_IMAGE_DATA_URL_CHARS)\n    image_data_urls: list[str] = Field(default_factory=list, max_length=_MAX_CHAT_IMAGE_ATTACHMENTS)\n    text_attachment: ChatTextAttachment | None = None',
    )
    replace_once(
        relative,
        '''    @field_validator("image_data_url")\n    @classmethod\n    def validate_image_data_url(cls, value: str | None) -> str | None:\n        if value is None:\n            return None\n        normalized = value.strip()\n        if not normalized:\n            return None\n        prefix = next(\n            (candidate for candidate in _SUPPORTED_CHAT_IMAGE_PREFIXES if normalized.startswith(candidate)),\n            None,\n        )\n        if prefix is None:\n            raise ValueError("image_data_url must be a PNG, JPEG, or WebP data URL")\n        try:\n            base64.b64decode(normalized[len(prefix):], validate=True)\n        except (binascii.Error, ValueError) as error:\n            raise ValueError("image_data_url must contain valid base64 data") from error\n        return normalized''',
        '''    @field_validator("image_data_url")\n    @classmethod\n    def validate_image_data_url(cls, value: str | None) -> str | None:\n        return _normalize_chat_image_data_url(value)\n\n    @field_validator("image_data_urls")\n    @classmethod\n    def validate_image_data_urls(cls, values: list[str]) -> list[str]:\n        normalized: list[str] = []\n        for value in values:\n            image = _normalize_chat_image_data_url(value)\n            if image is not None:\n                normalized.append(image)\n        return normalized\n\n    @model_validator(mode="after")\n    def normalize_image_attachments(self) -> "SendChatMessageRequest":\n        images: list[str] = []\n        for value in ([self.image_data_url] if self.image_data_url else []) + list(self.image_data_urls):\n            if value and value not in images:\n                images.append(value)\n        if len(images) > _MAX_CHAT_IMAGE_ATTACHMENTS:\n            raise ValueError(f"at most {_MAX_CHAT_IMAGE_ATTACHMENTS} chat images may be attached")\n        self.image_data_urls = images\n        self.image_data_url = images[0] if images else None\n        return self''',
    )


def patch_chat_storage_and_provider() -> None:
    relative = "src/app/chat/store.py"
    replace_once(
        relative,
        '''            if request.image_data_url:\n                message_metadata["image_data_url"] = request.image_data_url\n            if request.text_attachment:''',
        '''            if request.image_data_urls:\n                message_metadata["image_data_urls"] = list(request.image_data_urls)\n                # Keep the legacy first-image projection for older persisted consumers.\n                message_metadata["image_data_url"] = request.image_data_urls[0]\n            if request.text_attachment:''',
    )
    replace_once(
        relative,
        '''    metadata = getattr(message, "metadata", {})\n    image_data_url = metadata.get("image_data_url") if message.role == "user" else None\n    vision_images = [{"data": image_data_url}] if isinstance(image_data_url, str) and image_data_url else None\n    text_attachment = metadata.get("text_attachment") if message.role == "user" else None''',
        '''    metadata = getattr(message, "metadata", {})\n    image_data_urls = _chat_image_data_urls(metadata) if message.role == "user" else []\n    vision_images = [{"data": image_data_url} for image_data_url in image_data_urls] or None\n    text_attachment = metadata.get("text_attachment") if message.role == "user" else None''',
    )
    replace_once(
        relative,
        '''\ndef _text_attachment_prompt(value: object) -> str:\n''',
        '''\ndef _chat_image_data_urls(metadata: object) -> list[str]:\n    if not isinstance(metadata, dict):\n        return []\n    values: list[str] = []\n    raw = metadata.get("image_data_urls")\n    if isinstance(raw, list):\n        values.extend(value for value in raw if isinstance(value, str) and value)\n    legacy = metadata.get("image_data_url")\n    if isinstance(legacy, str) and legacy:\n        values.insert(0, legacy)\n    return list(dict.fromkeys(values))\n\n\ndef _text_attachment_prompt(value: object) -> str:\n''',
    )

    relative = "src/app/gateway/live_chat_postgres_fast_path.py"
    replace_once(
        relative,
        '''    if request.image_data_url:\n        message_metadata["image_data_url"] = request.image_data_url\n    if request.text_attachment:''',
        '''    if request.image_data_urls:\n        message_metadata["image_data_urls"] = list(request.image_data_urls)\n        message_metadata["image_data_url"] = request.image_data_urls[0]\n    if request.text_attachment:''',
    )


def patch_assistant_context() -> None:
    relative = "src/app/assistant_context/models.py"
    replace_once(
        relative,
        '    image_data_url: str | None = None\n    text_attachment: dict[str, Any] | None = None',
        '    image_data_url: str | None = None\n    image_data_urls: list[str] = Field(default_factory=list, max_length=8)\n    text_attachment: dict[str, Any] | None = None',
    )
    replace_once(
        relative,
        '''            image_data_url=self.image_data_url,\n            text_attachment=self.text_attachment,''',
        '''            image_data_url=self.image_data_url,\n            image_data_urls=self.image_data_urls,\n            text_attachment=self.text_attachment,''',
    )
    replace_once(
        relative,
        '''        self.image_data_url = validated.image_data_url\n        self.user_turn_id = validated.user_turn_id''',
        '''        self.image_data_url = validated.image_data_url\n        self.image_data_urls = list(validated.image_data_urls)\n        self.user_turn_id = validated.user_turn_id''',
    )

    relative = "src/app/assistant_context/routes.py"
    replace_once(
        relative,
        '''        image_data_url=request.image_data_url,\n        text_attachment=request.text_attachment,''',
        '''        image_data_url=request.image_data_url,\n        image_data_urls=request.image_data_urls,\n        text_attachment=request.text_attachment,''',
    )


def patch_agent_image_projection() -> None:
    relative = "src/app/agent_runtime/chat_bridge.py"
    regex_replace_once(
        relative,
        r'''def _agent_reference_images\(metadata: dict\[str, Any\] \| None\) -> list\[dict\[str, str\]\]:\n.*?\n\n\ndef _pending_failed_agent_retry''',
        '''def _agent_reference_images(metadata: dict[str, Any] | None) -> list[dict[str, str]]:\n    source = metadata or {}\n    values: list[str] = []\n    raw_values = source.get("image_data_urls")\n    if isinstance(raw_values, list):\n        values.extend(value for value in raw_values if isinstance(value, str) and value)\n    legacy = source.get("image_data_url")\n    if isinstance(legacy, str) and legacy:\n        values.insert(0, legacy)\n\n    images: list[dict[str, str]] = []\n    seen: set[str] = set()\n    for value in values:\n        normalized = value.strip()\n        if not normalized or normalized in seen:\n            continue\n        seen.add(normalized)\n        match = _AGENT_IMAGE_DATA_URL.fullmatch(normalized)\n        if match is None:\n            continue\n        images.append({\n            "type": "image",\n            "data": match.group(2),\n            "mimeType": match.group(1).lower(),\n        })\n        if len(images) >= 8:\n            break\n    return images\n\n\ndef _pending_failed_agent_retry''',
    )

    relative = "src/app/agent_runtime/active_objective.py"
    replace_once(
        relative,
        '''    if selected:\n        kinds.append("local_folder")\n    if isinstance(metadata.get("image_data_url"), str) and metadata.get("image_data_url"):\n        kinds.append("image")\n    raw_attachments = metadata.get("attachments")\n    attachment_count = len(raw_attachments) if isinstance(raw_attachments, list) else 0\n    if attachment_count:\n        kinds.append("file")''',
        '''    if selected:\n        kinds.append("local_folder")\n    raw_images = metadata.get("image_data_urls")\n    image_values = (\n        [value for value in raw_images if isinstance(value, str) and value]\n        if isinstance(raw_images, list)\n        else []\n    )\n    legacy_image = metadata.get("image_data_url")\n    if isinstance(legacy_image, str) and legacy_image and legacy_image not in image_values:\n        image_values.insert(0, legacy_image)\n    if image_values:\n        kinds.append("image")\n    raw_attachments = metadata.get("attachments")\n    attachment_count = (len(raw_attachments) if isinstance(raw_attachments, list) else 0) + len(image_values)\n    if isinstance(raw_attachments, list) and raw_attachments:\n        kinds.append("file")''',
    )


def patch_attachment_picker() -> None:
    relative = "src/apps/web/src/features/assistant-workspace/assistant-context-controller.ts"
    replace_once(
        relative,
        'const MAX_CHAT_IMAGE_BYTES = 5 * 1024 * 1024;\nconst MAX_CHAT_TEXT_FILE_BYTES = 100 * 1024;',
        'const MAX_CHAT_IMAGE_BYTES = 5 * 1024 * 1024;\nconst MAX_CHAT_IMAGE_ATTACHMENTS = 8;\nconst MAX_CHAT_TEXT_FILE_BYTES = 100 * 1024;',
    )
    replace_once(
        relative,
        '''  input.accept = 'image/png,image/jpeg,image/webp,.txt,.text,.md,.markdown,.csv,.json,.yaml,.yml,.xml,.html,.htm,.css,.js,.jsx,.ts,.tsx,.py,.java,.c,.cpp,.h,.hpp,.go,.rs,.sh,.sql';\n  input.setAttribute('aria-label', 'Choose photos and files from computer');\n  input.addEventListener('click', (event) => event.stopPropagation());\n  input.addEventListener('change', () => {\n    const file = input.files?.[0];\n    input.value = '';\n    if (file) void dispatchChatAttachment(file, item);\n  });''',
        '''  input.accept = 'image/png,image/jpeg,image/webp,.txt,.text,.md,.markdown,.csv,.json,.yaml,.yml,.xml,.html,.htm,.css,.js,.jsx,.ts,.tsx,.py,.java,.c,.cpp,.h,.hpp,.go,.rs,.sh,.sql';\n  input.multiple = true;\n  input.setAttribute('aria-label', 'Choose photos and files from computer');\n  input.addEventListener('click', (event) => event.stopPropagation());\n  input.addEventListener('change', () => {\n    const files = Array.from(input.files ?? []);\n    input.value = '';\n    if (files.length) void dispatchChatAttachments(files, item);\n  });''',
    )
    replace_once(
        relative,
        '''async function dispatchChatAttachment(file: File, item: HTMLButtonElement): Promise<void> {''',
        '''async function dispatchChatAttachments(files: File[], item: HTMLButtonElement): Promise<void> {\n  const imageFiles = files.filter((file) => SUPPORTED_CHAT_IMAGE_TYPES.has(file.type));\n  if (imageFiles.length === files.length) {\n    if (imageFiles.length > MAX_CHAT_IMAGE_ATTACHMENTS) {\n      dispatchChatImageError(`Attach at most ${MAX_CHAT_IMAGE_ATTACHMENTS} images at a time.`);\n      return;\n    }\n    if (imageFiles.some((file) => file.size > MAX_CHAT_IMAGE_BYTES)) {\n      dispatchChatImageError('Each image must be 5 MB or smaller.');\n      return;\n    }\n    try {\n      const images = await Promise.all(imageFiles.map(async (file) => ({\n        dataUrl: await readFileAsDataUrl(file),\n        mimeType: file.type,\n        size: file.size,\n      })));\n      for (const image of images) {\n        window.dispatchEvent(new CustomEvent('omnix:chat-image-selected', { detail: image }));\n      }\n      closeChatAttachmentMenu(item);\n    } catch {\n      dispatchChatImageError('Unable to read one or more selected images.');\n    }\n    return;\n  }\n\n  if (files.length !== 1) {\n    dispatchChatImageError('Select multiple images together, or attach one text document separately.');\n    return;\n  }\n  await dispatchChatAttachment(files[0], item);\n}\n\nasync function dispatchChatAttachment(file: File, item: HTMLButtonElement): Promise<void> {''',
    )


def patch_chatbot_workspace() -> None:
    relative = "src/apps/web/src/features/chatbot/ChatbotWorkspace.tsx"
    replace_once(
        relative,
        '''const MAX_CHAT_IMAGE_BYTES = 5 * 1024 * 1024;\nconst MAX_CHAT_TEXT_FILE_BYTES = 100 * 1024;\nconst SUPPORTED_CHAT_IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp']);\nconst DEFAULT_IMAGE_MESSAGE = 'Please analyze the attached image.';''',
        '''const MAX_CHAT_IMAGE_BYTES = 5 * 1024 * 1024;\nconst MAX_CHAT_IMAGE_ATTACHMENTS = 8;\nconst MAX_CHAT_TEXT_FILE_BYTES = 100 * 1024;\nconst SUPPORTED_CHAT_IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp']);\nconst DEFAULT_IMAGE_MESSAGE = 'Please analyze the attached image.';\nconst DEFAULT_IMAGES_MESSAGE = 'Please analyze the attached images.';''',
    )
    replace_once(
        relative,
        '  const [pastedChatImage, setPastedChatImage] = useState<PastedChatImage | null>(null);',
        '  const [pastedChatImages, setPastedChatImages] = useState<PastedChatImage[]>([]);',
    )
    regex_replace_once(
        relative,
        r'''  useEffect\(\(\) => \{\n    const handleSelectedChatImage = \(event: Event\): void => \{.*?\n  \}, \[\]\);\n\n  useEffect\(\(\) => \{\n    if \(activeView !== 'chats'\)''',
        '''  useEffect(() => {\n    const handleSelectedChatImage = (event: Event): void => {\n      const detail = (event as CustomEvent<Partial<PastedChatImage>>).detail;\n      if (!detail || typeof detail.dataUrl !== 'string' || typeof detail.mimeType !== 'string' || !SUPPORTED_CHAT_IMAGE_TYPES.has(detail.mimeType) || chatImageDataUrls({ image_data_url: detail.dataUrl }).length !== 1) {\n        setChatImageError('The selected file is not a supported image.');\n        return;\n      }\n      const image = {\n        dataUrl: detail.dataUrl,\n        mimeType: detail.mimeType,\n        size: typeof detail.size === 'number' && Number.isFinite(detail.size) ? detail.size : 0,\n      };\n      if (pastedChatImages.length >= MAX_CHAT_IMAGE_ATTACHMENTS && !pastedChatImages.some((candidate) => candidate.dataUrl === image.dataUrl)) {\n        setChatImageError(`You can attach up to ${MAX_CHAT_IMAGE_ATTACHMENTS} images.`);\n        return;\n      }\n      setPastedChatImages((current) => {\n        if (current.some((candidate) => candidate.dataUrl === image.dataUrl)) return current;\n        return [...current, image].slice(0, MAX_CHAT_IMAGE_ATTACHMENTS);\n      });\n      setPastedChatTextFile(null);\n      setChatImageError(null);\n    };\n    const handleSelectedChatTextFile = (event: Event): void => {\n      const detail = (event as CustomEvent<Partial<PastedChatTextFile>>).detail;\n      if (!detail || typeof detail.filename !== 'string' || typeof detail.mimeType !== 'string' || typeof detail.text !== 'string' || !detail.filename.trim() || !detail.mimeType.trim() || !detail.text.trim() || detail.text.length > MAX_CHAT_TEXT_FILE_BYTES) {\n        setChatImageError('The selected file is empty or too large. Choose a text file smaller than 100 KB.');\n        return;\n      }\n      setPastedChatTextFile({\n        filename: detail.filename.trim(),\n        mimeType: detail.mimeType.trim(),\n        size: typeof detail.size === 'number' && Number.isFinite(detail.size) ? detail.size : detail.text.length,\n        text: detail.text,\n      });\n      setPastedChatImages([]);\n      setChatImageError(null);\n    };\n    const handleChatImageError = (event: Event): void => {\n      const detail = (event as CustomEvent<{ message?: unknown }>).detail;\n      setChatImageError(typeof detail?.message === 'string' ? detail.message : 'Unable to attach the selected image.');\n    };\n    window.addEventListener('omnix:chat-image-selected', handleSelectedChatImage);\n    window.addEventListener('omnix:chat-text-file-selected', handleSelectedChatTextFile);\n    window.addEventListener('omnix:chat-image-error', handleChatImageError);\n    return () => {\n      window.removeEventListener('omnix:chat-image-selected', handleSelectedChatImage);\n      window.removeEventListener('omnix:chat-text-file-selected', handleSelectedChatTextFile);\n      window.removeEventListener('omnix:chat-image-error', handleChatImageError);\n    };\n  }, [pastedChatImages.length]);\n\n  useEffect(() => {\n    if (activeView !== 'chats')''',
    )
    # Submission and optimistic transcript use the ordered canonical image list.
    text_path = _path(relative)
    text = text_path.read_text(encoding="utf-8")
    text = text.replace('attachmentDefaultMessage(pastedChatImage, pastedChatTextFile)', 'attachmentDefaultMessage(pastedChatImages, pastedChatTextFile)')
    text_path.write_text(text, encoding="utf-8")
    replace_once(relative, '        image_data_url: pastedChatImage?.dataUrl,', '        image_data_urls: pastedChatImages.map((image) => image.dataUrl),')
    replace_once(
        relative,
        '''        ...((pastedChatImage || pastedChatTextFile) ? {\n          metadata: {\n            ...(pastedChatImage ? { image_data_url: pastedChatImage.dataUrl } : {}),\n            ...(pastedChatTextFile ? { text_attachment: { filename: pastedChatTextFile.filename, mime_type: pastedChatTextFile.mimeType, text: pastedChatTextFile.text } } : {}),\n          },\n        } : {}),''',
        '''        ...((pastedChatImages.length > 0 || pastedChatTextFile) ? {\n          metadata: {\n            ...(pastedChatImages.length > 0 ? {\n              image_data_urls: pastedChatImages.map((image) => image.dataUrl),\n              image_data_url: pastedChatImages[0].dataUrl,\n            } : {}),\n            ...(pastedChatTextFile ? { text_attachment: { filename: pastedChatTextFile.filename, mime_type: pastedChatTextFile.mimeType, text: pastedChatTextFile.text } } : {}),\n          },\n        } : {}),''',
    )
    replace_once(relative, '      setPastedChatImage(null);', '      setPastedChatImages([]);')
    replace_once(relative, '      pastedChatImage?.dataUrl ?? null,', '      pastedChatImages.map((image) => image.dataUrl),')
    regex_replace_once(
        relative,
        r'''  function handleComposerPaste\(event: ReactClipboardEvent<HTMLTextAreaElement>\): void \{.*?\n  \}\n\n  function toggleAssistantMessageFeedback''',
        '''  function handleComposerPaste(event: ReactClipboardEvent<HTMLTextAreaElement>): void {\n    const imageItems = Array.from(event.clipboardData.items).filter((item) => item.type.startsWith('image/'));\n    if (!imageItems.length) return;\n\n    event.preventDefault();\n    const files = imageItems.map((item) => item.getAsFile()).filter((file): file is File => Boolean(file));\n    if (files.length !== imageItems.length) {\n      setChatImageError('Unable to read one or more pasted images.');\n      return;\n    }\n    if (files.some((file) => !SUPPORTED_CHAT_IMAGE_TYPES.has(file.type))) {\n      setChatImageError('Paste PNG, JPEG, or WebP images.');\n      return;\n    }\n    if (files.some((file) => file.size > MAX_CHAT_IMAGE_BYTES)) {\n      setChatImageError('Each image must be 5 MB or smaller.');\n      return;\n    }\n    if (files.length > MAX_CHAT_IMAGE_ATTACHMENTS - pastedChatImages.length) {\n      setChatImageError(`You can attach up to ${MAX_CHAT_IMAGE_ATTACHMENTS} images.`);\n      return;\n    }\n\n    setChatImageError(null);\n    void Promise.all(files.map(async (file) => ({\n      dataUrl: await readFileAsDataUrl(file),\n      mimeType: file.type,\n      size: file.size,\n    })))\n      .then((images) => {\n        setPastedChatImages((current) => {\n          const next = [...current];\n          for (const image of images) {\n            if (next.length >= MAX_CHAT_IMAGE_ATTACHMENTS) break;\n            if (!next.some((candidate) => candidate.dataUrl === image.dataUrl)) next.push(image);\n          }\n          return next;\n        });\n        setPastedChatTextFile(null);\n      })\n      .catch(() => setChatImageError('Unable to read one or more pasted images.'));\n  }\n\n  function toggleAssistantMessageFeedback''',
    )
    replace_once(
        relative,
        '''                      {chatImageDataUrl(message.metadata) ? <img className="assistant-chat-message-image" src={chatImageDataUrl(message.metadata) ?? undefined} alt="User-provided attachment" /> : null}''',
        '''                      {chatImageDataUrls(message.metadata).length ? <div className="assistant-chat-message-images">{chatImageDataUrls(message.metadata).map((dataUrl, index) => <img className="assistant-chat-message-image" src={dataUrl} alt={index === 0 ? 'User-provided attachment' : `User-provided attachment ${index + 1}`} key={`${message.id}:image:${index}`} />)}</div> : null}''',
    )
    replace_once(
        relative,
        '''                {pastedChatImage ? <div className="assistant-chat-image-attachment" role="status"><img src={pastedChatImage.dataUrl} alt="Pasted image preview" /><div><strong>Image attached</strong><small>{pastedChatImage.mimeType.replace('image/', '').toUpperCase()} · {(pastedChatImage.size / 1024).toFixed(0)} KB</small></div><button type="button" aria-label="Remove pasted image" onClick={() => { setPastedChatImage(null); setChatImageError(null); }}>×</button></div> : null}\n                {pastedChatTextFile ?''',
        '''                {pastedChatImages.length ? <div className="assistant-chat-image-attachments" role="status" aria-label={`${pastedChatImages.length} image attachment${pastedChatImages.length === 1 ? '' : 's'}`}>{pastedChatImages.map((image, index) => <div className="assistant-chat-image-attachment" key={`${image.dataUrl.slice(-24)}:${index}`}><img src={image.dataUrl} alt={`Attached image preview ${index + 1}`} /><div><strong>Image {index + 1}</strong><small>{image.mimeType.replace('image/', '').toUpperCase()} · {(image.size / 1024).toFixed(0)} KB</small></div><button type="button" aria-label={`Remove attached image ${index + 1}`} onClick={() => { setPastedChatImages((current) => current.filter((_, candidateIndex) => candidateIndex !== index)); setChatImageError(null); }}>×</button></div>)}</div> : null}\n                {pastedChatTextFile ?''',
    )
    replace_once(
        relative,
        '''validate: (value) => (value.trim() || pastedChatImage || pastedChatTextFile) ? true : 'Enter a message, paste an image, or add a file before sending.' ''',
        '''validate: (value) => (value.trim() || pastedChatImages.length > 0 || pastedChatTextFile) ? true : 'Enter a message, paste an image, or add a file before sending.' ''',
    )
    # The JSX is minified on this line; handle the no-space variant too when needed.
    path = _path(relative)
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "validate: (value) => (value.trim() || pastedChatImage || pastedChatTextFile) ? true : 'Enter a message, paste an image, or add a file before sending.'",
        "validate: (value) => (value.trim() || pastedChatImages.length > 0 || pastedChatTextFile) ? true : 'Enter a message, paste an image, or add a file before sending.'",
    )
    path.write_text(text, encoding="utf-8")
    regex_replace_once(
        relative,
        r'''function attachmentDefaultMessage\(image: PastedChatImage \| null, textFile: PastedChatTextFile \| null\): string \{.*?\}\nfunction chatImageDataUrl\(metadata\?: Record<string, unknown>\): string \| null \{.*?\}\n''',
        '''function attachmentDefaultMessage(images: PastedChatImage[], textFile: PastedChatTextFile | null): string { return images.length > 1 ? DEFAULT_IMAGES_MESSAGE : images.length === 1 ? DEFAULT_IMAGE_MESSAGE : textFile ? DEFAULT_TEXT_FILE_MESSAGE : ''; }\nfunction chatImageDataUrls(metadata?: Record<string, unknown>): string[] {\n  const candidates: unknown[] = [];\n  if (Array.isArray(metadata?.image_data_urls)) candidates.push(...metadata.image_data_urls);\n  if (metadata?.image_data_url) candidates.unshift(metadata.image_data_url);\n  const images: string[] = [];\n  for (const value of candidates) {\n    if (typeof value !== 'string') continue;\n    if (![...SUPPORTED_CHAT_IMAGE_TYPES].some((mimeType) => value.startsWith(`data:${mimeType};base64,`))) continue;\n    if (!images.includes(value)) images.push(value);\n    if (images.length >= MAX_CHAT_IMAGE_ATTACHMENTS) break;\n  }\n  return images;\n}\n''',
    )

    final = _path(relative).read_text(encoding="utf-8")
    if re.search(r"\bpastedChatImage\b|\bsetPastedChatImage\b|\bchatImageDataUrl\(", final):
        raise RuntimeError("ChatbotWorkspace.tsx still contains a singular image attachment identifier")


def patch_chat_css() -> None:
    append_once(
        "src/apps/web/src/features/chatbot/ChatbotWorkspaceAssistantNav.css",
        ".assistant-chat-image-attachments {",
        '''.assistant-chat-image-attachments {\n  display: grid;\n  gap: 0.55rem;\n  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));\n}\n\n.assistant-chat-image-attachments .assistant-chat-image-attachment {\n  margin: 0;\n  min-width: 0;\n}\n\n.assistant-chat-message-images {\n  display: grid;\n  gap: 0.45rem;\n  grid-template-columns: repeat(auto-fit, minmax(8.5rem, 1fr));\n  margin: 0.35rem 0 0.55rem;\n  max-width: 34rem;\n}\n\n.assistant-chat-message-images .assistant-chat-message-image {\n  height: 100%;\n  margin: 0;\n  max-height: 18rem;\n  object-fit: cover;\n  width: 100%;\n}''',
    )


def patch_backend_tests() -> None:
    relative = "src/tests/unit/chat/test_chat_images.py"
    replace_once(
        relative,
        'IMAGE_DATA_URL = "data:image/png;base64,aW1hZ2UtZGF0YQ=="',
        'IMAGE_DATA_URL = "data:image/png;base64,aW1hZ2UtZGF0YQ=="\nSECOND_IMAGE_DATA_URL = "data:image/jpeg;base64,c2Vjb25kLWltYWdl"',
    )
    regex_replace_once(
        relative,
        r'''def test_send_chat_request_validates_supported_image_data_url\(\):.*?\n\n\ndef test_provider_messages_preserve_pasted_image_for_base_and_prompt_stores''',
        '''def test_send_chat_request_validates_supported_image_data_url():\n    legacy = SendChatMessageRequest(content="Describe this", image_data_url=IMAGE_DATA_URL)\n    assert legacy.image_data_url == IMAGE_DATA_URL\n    assert legacy.image_data_urls == [IMAGE_DATA_URL]\n\n    request = SendChatMessageRequest(\n        content="Compare these",\n        image_data_urls=[IMAGE_DATA_URL, SECOND_IMAGE_DATA_URL],\n    )\n    assert request.image_data_url == IMAGE_DATA_URL\n    assert request.image_data_urls == [IMAGE_DATA_URL, SECOND_IMAGE_DATA_URL]\n\n    with pytest.raises(ValidationError, match="PNG, JPEG, or WebP"):\n        SendChatMessageRequest(content="Describe this", image_data_urls=["data:image/gif;base64,R0lGODlh"])\n\n    with pytest.raises(ValidationError, match="valid base64"):\n        SendChatMessageRequest(content="Describe this", image_data_urls=["data:image/png;base64,not base64"])\n\n    with pytest.raises(ValidationError):\n        SendChatMessageRequest(content="Too many", image_data_urls=[IMAGE_DATA_URL] * 9)\n\n\ndef test_provider_messages_preserve_pasted_image_for_base_and_prompt_stores''',
    )
    replace_once(
        relative,
        '''        metadata={\n            "image_data_url": IMAGE_DATA_URL,\n            "text_attachment": {''',
        '''        metadata={\n            "image_data_url": IMAGE_DATA_URL,\n            "image_data_urls": [IMAGE_DATA_URL, SECOND_IMAGE_DATA_URL],\n            "text_attachment": {''',
    )
    replace_once(
        relative,
        '''    assert base_messages[-1].to_dict()["content"][-1]["image_url"]["url"] == IMAGE_DATA_URL\n    assert "[Attached file: notes.md (text/markdown)]" in base_messages[-1].content''',
        '''    base_image_urls = [item["image_url"]["url"] for item in base_messages[-1].to_dict()["content"] if item.get("type") == "image_url"]\n    assert base_image_urls == [IMAGE_DATA_URL, SECOND_IMAGE_DATA_URL]\n    assert "[Attached file: notes.md (text/markdown)]" in base_messages[-1].content''',
    )
    replace_once(
        relative,
        '''    assert prompt_messages[-1].to_dict()["content"][-1]["image_url"]["url"] == IMAGE_DATA_URL\n    assert "# Important notes" in prompt_messages[-1].content''',
        '''    prompt_image_urls = [item["image_url"]["url"] for item in prompt_messages[-1].to_dict()["content"] if item.get("type") == "image_url"]\n    assert prompt_image_urls == [IMAGE_DATA_URL, SECOND_IMAGE_DATA_URL]\n    assert "# Important notes" in prompt_messages[-1].content''',
    )
    replace_once(
        relative,
        '''def test_chat_store_persists_text_file_attachment(tmp_path):''',
        '''def test_chat_store_persists_multiple_image_attachments(tmp_path):\n    store = ChatSessionStore(tmp_path / "chat.json")\n    session = store.create_session(CreateChatSessionRequest(title="Images"))\n    appended = store.begin_user_message(\n        session.id,\n        SendChatMessageRequest(\n            content="Compare these",\n            image_data_urls=[IMAGE_DATA_URL, SECOND_IMAGE_DATA_URL],\n        ),\n    )\n\n    assert appended is not None\n    _session, message = appended\n    assert message.metadata["image_data_urls"] == [IMAGE_DATA_URL, SECOND_IMAGE_DATA_URL]\n    assert message.metadata["image_data_url"] == IMAGE_DATA_URL\n\n\ndef test_chat_store_persists_text_file_attachment(tmp_path):''',
    )

    relative = "src/tests/agent_runtime/test_chat_bridge.py"
    append_once(
        relative,
        "def test_agent_reference_images_accept_multiple_supported_chat_data_urls",
        '''def test_agent_reference_images_accept_multiple_supported_chat_data_urls() -> None:\n    images = chat_bridge._agent_reference_images({\n        "image_data_url": "data:image/png;base64,YWJj",\n        "image_data_urls": [\n            "data:image/png;base64,YWJj",\n            "data:image/jpeg;base64,ZGVm",\n        ],\n    })\n\n    assert images == [\n        {"type": "image", "data": "YWJj", "mimeType": "image/png"},\n        {"type": "image", "data": "ZGVm", "mimeType": "image/jpeg"},\n    ]''',
    )


def patch_frontend_test() -> None:
    relative = "src/apps/web/src/features/chatbot/ChatbotWorkspace.test.tsx"
    regex_replace_once(
        relative,
        r'''  it\('accepts a pasted image, previews it, and sends it with the chat message', async \(\) => \{.*?\n  \}\);\n\n  it\('sends a text file chosen from the add menu through the normal chat request' ''',
        '''  it('accepts multiple pasted images, previews them, and sends them with the chat message', async () => {\n    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {\n      configurable: true,\n      value: vi.fn(),\n    });\n    const firstImageDataUrl = 'data:image/png;base64,Zmlyc3QtaW1hZ2U=';\n    const secondImageDataUrl = 'data:image/jpeg;base64,c2Vjb25kLWltYWdl';\n    let session = {\n      id: 'chat:image',\n      title: 'Image chat',\n      provider_id: 'openai',\n      model_id: 'gpt-mini',\n      message_count: 0,\n      messages: [] as Array<{ id: string; role: 'user' | 'assistant'; content: string; created_at: string; metadata?: Record<string, unknown> }>,\n      created_at: '2026-06-14T00:00:00Z',\n      updated_at: '2026-06-14T00:00:00Z',\n    };\n    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {\n      const path = requestPath(input);\n\n      if (path === '/api/providers') return Response.json(providerPayload());\n      if (path === '/api/assets') return Response.json(assetPayload());\n      if (path === '/api/chat/sessions' && init?.method === 'POST') return Response.json(session);\n      if (path === '/api/chat/sessions') return Response.json({ sessions: [] });\n      if (path === '/api/chat/sessions/chat%3Aimage') return Response.json(session);\n      if (path === '/api/chat/sessions/chat%3Aimage/messages') {\n        session = {\n          ...session,\n          message_count: 2,\n          messages: [\n            { id: 'msg:image-user', role: 'user', content: 'Compare these images', created_at: '2026-06-14T00:00:01Z', metadata: { image_data_url: firstImageDataUrl, image_data_urls: [firstImageDataUrl, secondImageDataUrl] } },\n            { id: 'msg:image-assistant', role: 'assistant', content: 'I can see both attached images.', created_at: '2026-06-14T00:00:02Z' },\n          ],\n        };\n        return Response.json({\n          generation_status: 'queued',\n          session,\n          user_message: session.messages[0],\n          job: { id: 'job:image', module: 'chatbot', type: 'chat.generate', status: 'queued', resource_class: 'gpu:llm', created_at: '2026-06-14T00:00:01Z', updated_at: '2026-06-14T00:00:01Z', priority: 0 },\n        });\n      }\n      return new Response('not found', { status: 404 });\n    });\n    vi.stubGlobal('fetch', fetchMock);\n\n    const originalFileReader = globalThis.FileReader;\n    class TestFileReader {\n      result: string | ArrayBuffer | null = null;\n      error: DOMException | null = null;\n      onload: ((this: FileReader, ev: ProgressEvent<FileReader>) => unknown) | null = null;\n      onerror: ((this: FileReader, ev: ProgressEvent<FileReader>) => unknown) | null = null;\n      readAsDataURL(file: Blob): void {\n        const typed = file as File;\n        this.result = typed.type === 'image/jpeg' ? secondImageDataUrl : firstImageDataUrl;\n        queueMicrotask(() => this.onload?.call(this as unknown as FileReader, new ProgressEvent('load')));\n      }\n    }\n    vi.stubGlobal('FileReader', TestFileReader as unknown as typeof FileReader);\n\n    renderChatbot();\n\n    await screen.findByText('No chat messages yet.');\n    const textarea = screen.getByLabelText('Message');\n    const firstImage = new File(['first-image'], 'first.png', { type: 'image/png' });\n    const secondImage = new File(['second-image'], 'second.jpg', { type: 'image/jpeg' });\n    fireEvent.paste(textarea, {\n      clipboardData: {\n        items: [\n          { type: 'image/png', getAsFile: () => firstImage },\n          { type: 'image/jpeg', getAsFile: () => secondImage },\n        ],\n      },\n    });\n\n    expect(await screen.findByAltText('Attached image preview 1')).toBeInTheDocument();\n    expect(await screen.findByAltText('Attached image preview 2')).toBeInTheDocument();\n    expect(screen.getByRole('button', { name: 'Remove attached image 1' })).toBeInTheDocument();\n    expect(screen.getByRole('button', { name: 'Remove attached image 2' })).toBeInTheDocument();\n    fireEvent.change(textarea, { target: { value: 'Compare these images' } });\n    fireEvent.click(screen.getByRole('button', { name: 'Queue response' }));\n\n    await waitFor(() => {\n      const messageCall = fetchMock.mock.calls.find(\n        ([input, callInit]) => requestPath(input as RequestInfo | URL).endsWith('/messages') && callInit?.method === 'POST',\n      );\n      expect(messageCall?.[1]?.body).toContain(`"image_data_urls":["${firstImageDataUrl}","${secondImageDataUrl}"]`);\n      expect(messageCall?.[1]?.body).not.toContain('"image_data_url":');\n    });\n    expect(await screen.findByAltText('User-provided attachment')).toBeInTheDocument();\n    expect(await screen.findByAltText('User-provided attachment 2')).toBeInTheDocument();\n    expect((await screen.findAllByText('I can see both attached images.')).length).toBeGreaterThan(0);\n\n    vi.stubGlobal('FileReader', originalFileReader);\n  });\n\n  it('sends a text file chosen from the add menu through the normal chat request' ''',
    )


def main() -> None:
    patch_chat_contract()
    patch_chat_storage_and_provider()
    patch_assistant_context()
    patch_agent_image_projection()
    patch_attachment_picker()
    patch_chatbot_workspace()
    patch_chat_css()
    patch_backend_tests()
    patch_frontend_test()
    print("Applied multi-image chat support (up to 8 images per turn).")


if __name__ == "__main__":
    main()
