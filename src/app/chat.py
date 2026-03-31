import base64
import json
import re
from datetime import datetime
from io import BytesIO, StringIO

import numpy as np
from flask import Blueprint, Response, jsonify, request

import app.shared as shared
from app.providers import ChatMessage, ChatResponse

chat_bp = Blueprint('chat', __name__)

def process_attachment(attachment):
    """Process an attachment - extract text from documents or prepare images for vision."""
    att_type = attachment.get('type', '')
    
    if att_type == 'image':
        # Return image in base64 format for vision models
        return {
            'type': 'image',
            'data': attachment.get('data', ''),
            'name': attachment.get('name', '')
        }
    elif att_type == 'document':
        # Document processing will be handled separately
        return {
            'type': 'document',
            'name': attachment.get('name', ''),
            'mimeType': attachment.get('mimeType', '')
        }
    return None

def extract_document_text(file_data, filename):
    """Extract text from document files."""
    import docx
    import pandas as pd
    import PyPDF2
    
    text = ''
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    
    try:
        if ext == 'pdf':
            # Handle PDF
            if isinstance(file_data, str):
                # Base64 encoded
                file_bytes = base64.b64decode(file_data)
            else:
                file_bytes = file_data
                
            pdf_file = BytesIO(file_bytes)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            for page in pdf_reader.pages:
                text += page.extract_text() + '\n'
                
        elif ext == 'docx':
            # Handle DOCX
            if isinstance(file_data, str):
                file_bytes = base64.b64decode(file_data)
            else:
                file_bytes = file_data
                
            doc_file = BytesIO(file_bytes)
            doc = docx.Document(doc_file)
            for para in doc.paragraphs:
                text += para.text + '\n'
                
        elif ext == 'txt':
            # Handle TXT
            if isinstance(file_data, str):
                text = file_data
            else:
                text = file_data.decode('utf-8', errors='ignore')
                
        elif ext == 'csv':
            # Handle CSV
            if isinstance(file_data, str):
                csv_data = base64.b64decode(file_data)
            else:
                csv_data = file_data
                
            df = pd.read_csv(BytesIO(csv_data))
            text = df.to_string()
            
    except Exception as e:
        print(f'[CHAT] Error extracting text from {filename}: {e}')
        return f'[Error: Could not extract text from {filename}]'
    
    return text[:10000]  # Limit to first 10000 chars

def prepare_messages(data):
    """Prepare chat messages from request data."""
    if not data or ('message' not in data and 'attachments' not in data):
        return None, jsonify({"success": False, "error": "Message or attachments required"}), 400
    
    user_message = data.get('message', '')
    session_id = data.get('session_id', 'default')
    model = data.get('model', '')
    system_prompt = data.get('system_prompt', shared.get_global_system_prompt())
    attachments = data.get('attachments', [])
    
    shared.sessions_data = shared.load_sessions()
    
    if session_id not in shared.sessions_data:
        shared.sessions_data[session_id] = {
            'title': 'New Chat',
            'messages': [],
            'system_prompt': system_prompt,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
    
    # Process attachments - separate images and documents
    image_attachments = []
    doc_attachments = []
    
    for att in attachments:
        att_type = att.get('type', '')
        
        if att_type == 'image':
            image_attachments.append(att)
        elif att_type == 'document':
            doc_attachments.append(att)
    
    # Build message content - for vision models, use multi-part content
    message_content = user_message
    
    # Add document info to message
    if doc_attachments:
        message_content += '\n\n--- Attached Documents ---\n'
        for doc in doc_attachments:
            message_content += f'\n[{doc.get("name", "document")}]'
        message_content += '\n(Please analyze the document content)'
    
    # Build message list
    messages = [ChatMessage(role="system", content=system_prompt)]
    messages.extend([
        ChatMessage(role=m["role"], content=m["content"])
        for m in shared.sessions_data[session_id].get('messages', [])
        if m.get('role') != 'system'
    ])
    
    # Store vision images for provider to handle
    user_msg = ChatMessage(role="user", content=message_content)
    
    # Attach images as a special attribute (will be processed by provider)
    if image_attachments:
        user_msg.vision_images = image_attachments
    
    messages.append(user_msg)
    
    # Save user message to session (without vision content)
    shared.sessions_data[session_id]['messages'].append({
        "role": "user",
        "content": user_message
    })
    
    return session_id, user_message, model, messages, None, None

@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    """Non-streaming chat endpoint."""
    session_id, user_message, model, messages, err, status = prepare_messages(request.get_json())
    if err:
        return err, status
    
    # Get provider
    provider = shared.get_provider()
    if not provider:
        return jsonify({"success": False, "error": "Provider not available"}), 500
    
    try:
        # Call provider
        response = provider.chat_completion(
            messages=messages,
            model=model or provider.config.model,
            stream=False
        )
        
        # Extract content and thinking
        content = response.content
        thinking = response.thinking or response.reasoning or ""
        
        # Save assistant message to session
        shared.sessions_data[session_id]['messages'].append({
            "role": "assistant",
            "content": content,
            "thinking": thinking
        })
        
        # Update session title if it's the first response
        if len(shared.sessions_data[session_id]['messages']) == 2:
            shared.sessions_data[session_id]['title'] = user_message[:30] + "..."
        
        shared.sessions_data[session_id]['updated_at'] = datetime.now().isoformat()
        shared.save_sessions(shared.sessions_data)
        
        return jsonify({
            "success": True,
            "response": content,
            "thinking": thinking,
            "session_id": session_id,
            "tokens": response.usage
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@chat_bp.route('/api/chat/stream', methods=['POST'])
def chat_stream():
    """Streaming chat endpoint."""
    session_id, user_message, model, messages, err, status = prepare_messages(request.get_json())
    if err:
        return err, status
    
    # Get provider
    provider = shared.get_provider()
    if not provider:
        return jsonify({"success": False, "error": "Provider not available"}), 500
    
    # Check if provider supports streaming
    if not provider.supports_streaming():
        return jsonify({"success": False, "error": "Provider does not support streaming"}), 400
    
    try:
        stream_generator = provider.chat_completion(
            messages=messages,
            model=model or provider.config.model,
            stream=True
        )
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to start stream: {str(e)}"}), 500
    
    def generate():
        try:
            ai_message = ""
            thinking = ""
            
            for response_chunk in stream_generator:
                if response_chunk.content:
                    ai_message += response_chunk.content
                    yield f"data: {json.dumps({'type': 'content', 'content': response_chunk.content})}\n\n"
                
                if response_chunk.thinking or response_chunk.reasoning:
                    thinking += response_chunk.thinking or response_chunk.reasoning
            
            # Save assistant message to session
            shared.sessions_data[session_id]['messages'].append({
                "role": "assistant",
                "content": ai_message,
                "thinking": thinking
            })
            
            if len(shared.sessions_data[session_id]['messages']) == 2:
                shared.sessions_data[session_id]['title'] = user_message[:30] + "..."
            
            shared.sessions_data[session_id]['updated_at'] = datetime.now().isoformat()
            shared.save_sessions(shared.sessions_data)
            
            yield f"data: {json.dumps({'type': 'done', 'thinking': thinking, 'session_id': session_id})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')

@chat_bp.route('/api/chat/voice-stream', methods=['POST'])
def chat_voice_stream():
    """Voice-streaming chat endpoint with TTS integration."""
    data = request.get_json()
    session_id, user_message, model, messages, err, status = prepare_messages(data)
    if err:
        return err, status
    
    # Get provider
    provider = shared.get_provider()
    if not provider:
        return jsonify({"success": False, "error": "Provider not available"}), 500
    
    # Check if provider supports streaming
    if not provider.supports_streaming():
        return jsonify({"success": False, "error": "Provider does not support streaming"}), 400
    
    # Get raw speaker string
    speaker = data.get('speaker', 'default')
    # Resolve custom voice if any
    clean_speaker = speaker.replace(" (Custom)", "").strip()
    voice_clone_id = shared.custom_voices.get(clean_speaker, {}).get("voice_clone_id")
    
    final_speaker = voice_clone_id
    if not final_speaker and clean_speaker and clean_speaker.lower() != 'default':
        final_speaker = clean_speaker
    
    try:
        stream_generator = provider.chat_completion(
            messages=messages,
            model=model or provider.config.model,
            stream=True
        )
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to start stream: {str(e)}"}), 500
    
    def generate():
        import time
        SENTENCE_ENDINGS = re.compile(r'[.!?]\s+|\n')
        MIN_TOKENS, MAX_TOKENS, MIN_SENTENCE = 15, 60, 15
        
        def generate_tts(sentence, index):
            clean_text = shared.remove_emojis(sentence)
            if not clean_text.strip():
                return None
            try:
                # Call Provider directly instead of routing HTTP to ourselves (prevents deadlock)
                tts_provider = shared.get_tts_provider()
                if not tts_provider:
                    return None
                    
                if hasattr(tts_provider, 'generate_tts'):
                    result = tts_provider.generate_tts(text=clean_text, speaker=final_speaker, language="en")
                elif hasattr(tts_provider, 'generate_audio'):
                    result = tts_provider.generate_audio(text=clean_text, speaker=final_speaker, language="en")
                else:
                    return None
                    
                if result and result.get('success'):
                    return {
                        'audio': result.get('audio', ''),
                        'sample_rate': result.get('sample_rate', 24000)
                    }
            except Exception as e:
                import traceback
                print(f"[VOICE STREAM TTS ERROR] {e}")
                traceback.print_exc()
            return None
        
        try:
            ai_message = ""
            thinking = ""
            buffer = ""
            sentence_idx = 0
            generated = 0
            is_first = True
            sent_first = False
            
            for response_chunk in stream_generator:
                if response_chunk.content:
                    ai_message += response_chunk.content
                    buffer += response_chunk.content
                    yield f"data: {json.dumps({'type': 'content', 'content': response_chunk.content})}\n\n"
                    
                    chunks = []
                    if is_first and len(buffer) >= MIN_TOKENS:
                        split_idx = min(len(buffer), MAX_TOKENS)
                        last_space = buffer.rfind(' ', 0, split_idx)
                        split_idx = last_space if last_space > MIN_TOKENS else split_idx
                        chunks.append(buffer[:split_idx].strip())
                        buffer = buffer[split_idx:].lstrip()
                        is_first = False
                    else:
                        matches = list(SENTENCE_ENDINGS.finditer(buffer))
                        last_end = 0
                        for m in matches:
                            sentence = buffer[last_end:m.end()].strip()
                            if len(sentence) >= MIN_SENTENCE and not re.search(r'\b(Mr|Mrs|Ms|Dr|Sr|Jr)\.\s*$', sentence, re.IGNORECASE):
                                chunks.append(sentence)
                                last_end = m.end()
                        buffer = buffer[last_end:]
                    
                    for chunk in chunks:
                        if tts_res := generate_tts(chunk, sentence_idx):
                            generated += 1
                            yield f"data: {json.dumps({'type': 'tts_sentence', 'index': sentence_idx, 'audio': tts_res['audio'], 'sample_rate': tts_res['sample_rate'], 'text': chunk, 'is_first': not sent_first})}\n\n"
                            sent_first = True
                        sentence_idx += 1
                
                if response_chunk.thinking or response_chunk.reasoning:
                    thinking += response_chunk.thinking or response_chunk.reasoning
            
            # Handle remaining buffer
            if buffer.strip() and len(buffer.strip()) >= MIN_SENTENCE:
                if tts_res := generate_tts(buffer.strip(), sentence_idx):
                    generated += 1
                    yield f"data: {json.dumps({'type': 'tts_sentence', 'index': sentence_idx, 'audio': tts_res['audio'], 'sample_rate': tts_res['sample_rate'], 'text': buffer.strip()})}\n\n"
            
            # Extract thinking from content if not already captured
            if not thinking:
                thinking, ai_message = shared.extract_thinking(ai_message)
            
            # Save assistant message
            shared.sessions_data[session_id]['messages'].append({
                "role": "assistant",
                "content": ai_message,
                "thinking": thinking
            })
            shared.save_sessions(shared.sessions_data)
            
            yield f"data: {json.dumps({'type': 'done', 'thinking': thinking, 'session_id': session_id, 'sentences_generated': generated})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')

@chat_bp.route('/api/chat/streaming-conversation', methods=['POST'])
def chat_streaming_conversation():
    """Streaming conversation endpoint with full streaming pipeline."""
    data = request.get_json()
    session_id, user_message, model, messages, err, status = prepare_messages(data)
    if err:
        return err, status
    
    # Get providers
    provider = shared.get_provider()
    if not provider:
        return jsonify({"success": False, "error": "LLM provider not available"}), 500
    
    tts_provider = shared.get_tts_provider()
    if not tts_provider:
        return jsonify({"success": False, "error": "TTS provider not available"}), 500
    
    # Check if providers support streaming
    if not provider.supports_streaming():
        return jsonify({"success": False, "error": "LLM provider does not support streaming"}), 400
    
    if not tts_provider.supports_streaming():
        return jsonify({"success": False, "error": "TTS provider does not support streaming"}), 400
    
    # Get speaker configuration
    speaker = data.get('speaker', 'default')
    clean_speaker = speaker.replace(" (Custom)", "").strip()
    voice_clone_id = shared.custom_voices.get(clean_speaker, {}).get("voice_clone_id")
    
    final_speaker = voice_clone_id
    if not final_speaker and clean_speaker and clean_speaker.lower() != 'default':
        final_speaker = clean_speaker
    
    try:
        # Start LLM streaming
        stream_generator = provider.chat_completion(
            messages=messages,
            model=model or provider.config.model,
            stream=True
        )
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to start LLM stream: {str(e)}"}), 500
    
    def generate():
        import asyncio
        import queue
        import threading
        
        # Buffer for accumulating tokens before sending to TTS
        token_buffer = ""
        sentence_buffer = ""
        sentence_idx = 0
        ai_message = ""
        thinking = ""
        
        # Queue for TTS processing - each item is (sentence, is_first_for_sentence)
        tts_queue = queue.Queue()
        
        # Use a lock for thread-safe audio queue access
        audio_queue_lock = threading.Lock()
        audio_chunks_list = []
        
        # Track streaming state per sentence
        current_sentence_idx = -1
        
        import time as time_module
        tts_start_time = None
        chunk_start_time = None
        
        def tts_worker():
            """Background worker for TTS processing - streams chunks immediately."""
            nonlocal tts_start_time, chunk_start_time
            while True:
                try:
                    item = tts_queue.get(timeout=1)
                    if item is None:
                        break
                    
                    sentence, sentence_idx = item
                    tts_start_time = time_module.time()
                    print(f"[TTS DEBUG] Starting TTS for sentence {sentence_idx}: '{sentence[:30]}...'")
                    
                    # Generate TTS audio - stream EACH chunk immediately like reference
                    try:
                        if hasattr(tts_provider, 'generate_audio_stream'):
                            # Use streaming TTS - yield each chunk as it arrives
                            sample_rate = 24000
                            first_chunk = True
                            
                            for audio_chunk, sr, timing in tts_provider.generate_audio_stream(
                                text=sentence,
                                speaker=final_speaker,
                                language="English",
                                chunk_size=2,  # Smallest chunk for fastest first audio
                                non_streaming_mode=False,
                                temperature=0.6,
                                top_k=20,
                                top_p=0.85,
                                repetition_penalty=1.0,
                                append_silence=False,
                                max_new_tokens=180
                            ):
                                if audio_chunk is not None and len(audio_chunk) > 0:
                                    chunk_gen_time = (time_module.time() - tts_start_time) * 1000
                                    print(f"[TTS DEBUG] Sentence {sentence_idx} chunk generated in {chunk_gen_time:.0f}ms")
                                    if chunk_start_time is None:
                                        chunk_start_time = time_module.time()
                                    
                                    sample_rate = sr
                                    
                                    # Convert float32 to int16 PCM
                                    pcm_int16 = (audio_chunk * 32767).astype(np.int16).tobytes()
                                    audio_b64 = base64.b64encode(pcm_int16).decode('utf-8')
                                    
                                    # Stream each chunk immediately
                                    with audio_queue_lock:
                                        audio_chunks_list.append({
                                            'type': 'audio_chunk',
                                            'audio': audio_b64,
                                            'sample_rate': sample_rate,
                                            'text': sentence,
                                            'index': sentence_idx,
                                            'first_chunk': first_chunk
                                        })
                                        print(f"[TTS DEBUG] Added audio chunk to queue: sentence {sentence_idx}, first={first_chunk}, size={len(pcm_int16)} bytes")
                                    first_chunk = False
                        else:
                            # Fallback to batch TTS
                            if hasattr(tts_provider, 'generate_tts'):
                                result = tts_provider.generate_tts(text=sentence, speaker=final_speaker, language="en")
                            elif hasattr(tts_provider, 'generate_audio'):
                                result = tts_provider.generate_audio(text=sentence, speaker=final_speaker, language="en")
                            else:
                                continue
                            
                            if result and result.get('success'):
                                with audio_queue_lock:
                                    audio_chunks_list.append({
                                        'type': 'audio_chunk',
                                        'audio': result.get('audio', ''),
                                        'sample_rate': result.get('sample_rate', 24000),
                                        'text': sentence,
                                        'index': sentence_idx,
                                        'first_chunk': True
                                    })
                    except Exception as e:
                        print(f"[STREAMING CONVERSATION TTS ERROR] {e}")
                    finally:
                        tts_queue.task_done()
                        
                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"[STREAMING CONVERSATION TTS WORKER ERROR] {e}")
        
        # Start TTS worker thread
        tts_thread = threading.Thread(target=tts_worker, daemon=True)
        tts_thread.start()
        
        last_audio_idx = -1
        
        try:
            for response_chunk in stream_generator:
                if response_chunk.content:
                    token = response_chunk.content
                    ai_message += token
                    token_buffer += token
                    
                    # Accumulate tokens until we have a complete sentence
                    sentence_buffer += token
                    
                    # Check if we have a complete sentence OR enough text for TTS
                    if any(char in sentence_buffer for char in '.!?。！？'):
                        # Clean up the sentence
                        sentence = sentence_buffer.strip()
                        if len(sentence) >= 5:  # Minimum sentence length
                            # Send to TTS worker with sentence index
                            print(f"[CHAT DEBUG] Queuing sentence for TTS: '{sentence[:30]}...' at idx {sentence_idx}")
                            tts_queue.put((sentence, sentence_idx))
                            sentence_idx += 1
                        
                        # Yield the full accumulated text for display (not just current token)
                        yield f"data: {json.dumps({'type': 'content', 'content': sentence_buffer})}\n\n"
                        sentence_buffer = ""
                    elif len(sentence_buffer) >= 8:
                        # No sentence end yet but have enough text - start TTS anyway
                        sentence = sentence_buffer.strip()
                        print(f"[CHAT DEBUG] Queuing partial for TTS (no sentence end): '{sentence[:30]}...' at idx {sentence_idx}")
                        tts_queue.put((sentence, sentence_idx))
                        sentence_idx += 1
                        sentence_buffer = ""
                    else:
                        # No sentence complete yet, yield current token
                        yield f"data: {json.dumps({'type': 'content', 'content': token})}\n\n"
                
                if response_chunk.thinking or response_chunk.reasoning:
                    thinking += response_chunk.thinking or response_chunk.reasoning
                
                # Yield any new audio chunks that are ready
                with audio_queue_lock:
                    while len(audio_chunks_list) > last_audio_idx + 1:
                        last_audio_idx += 1
                        audio_data = audio_chunks_list[last_audio_idx]
                        print(f"[CHAT DEBUG] Yielding audio chunk to client: sentence {audio_data.get('index')}, first={audio_data.get('first_chunk')}")
                        yield f"data: {json.dumps(audio_data)}\n\n"
            
            # Process any remaining sentence buffer
            if sentence_buffer.strip():
                sentence = sentence_buffer.strip()
                if len(sentence) >= 10:
                    tts_queue.put((sentence, sentence_idx))
                    sentence_idx += 1
            
            # Wait for all TTS tasks to complete
            tts_queue.join()
            
            # Signal TTS worker to stop
            tts_queue.put(None)
            tts_thread.join(timeout=5)
            
            # Yield any remaining audio chunks
            with audio_queue_lock:
                while len(audio_chunks_list) > last_audio_idx + 1:
                    last_audio_idx += 1
                    audio_data = audio_chunks_list[last_audio_idx]
                    yield f"data: {json.dumps(audio_data)}\n\n"
            
            # Extract thinking from content if not already captured
            if not thinking:
                thinking, ai_message = shared.extract_thinking(ai_message)
            
            # Save assistant message
            shared.sessions_data[session_id]['messages'].append({
                "role": "assistant",
                "content": ai_message,
                "thinking": thinking
            })
            shared.save_sessions(shared.sessions_data)
            
            yield f"data: {json.dumps({'type': 'done', 'thinking': thinking, 'session_id': session_id})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        finally:
            # Clean up TTS worker
            try:
                # Clear any remaining items in queue
                while not tts_queue.empty():
                    tts_queue.get()
                    tts_queue.task_done()
                tts_queue.put(None)
            except:
                pass
    
    return Response(generate(), mimetype='text/event-stream')

@chat_bp.route('/api/conversation/greeting', methods=['POST'])
def conversation_greeting():
    """Generate a greeting when initially opening conversation mode."""
    data = request.get_json() or {}
    speaker = data.get('speaker', 'default')
    
    greeting_text = "Hello! I'm listening. How can I help you today?"
    
    try:
        tts_provider = shared.get_tts_provider()
        if not tts_provider:
            return jsonify({"success": False, "error": "No TTS provider"}), 500
            
        clean_speaker = speaker.replace(" (Custom)", "").strip()
        custom_vid = shared.custom_voices.get(clean_speaker, {}).get("voice_clone_id")
        final_speaker = custom_vid
        
        if not final_speaker and clean_speaker and clean_speaker.lower() != 'default':
            final_speaker = clean_speaker
            
        if hasattr(tts_provider, 'generate_tts'):
            result = tts_provider.generate_tts(text=greeting_text, speaker=final_speaker, language="en")
        elif hasattr(tts_provider, 'generate_audio'):
            result = tts_provider.generate_audio(text=greeting_text, speaker=final_speaker, language="en")
        else:
            return jsonify({"success": False, "error": "Provider missing method"}), 500
        
        try:
            if hasattr(tts_provider, 'generate_audio_stream'):
                import threading
                def warmup_streaming():
                    try:
                        print("[WARMUP] Starting streaming mode warmup...")
                        for _ in tts_provider.generate_audio_stream(
                            text="a", speaker=final_speaker, language="English",
                            chunk_size=2, non_streaming_mode=False,
                            temperature=0.6, top_k=20, append_silence=False,
                            max_new_tokens=60
                        ):
                            break
                        print("[WARMUP] Streaming mode warmed up!")
                    except Exception as e:
                        print(f"[WARMUP] Error: {e}")
                threading.Thread(target=warmup_streaming, daemon=True).start()
        except:
            pass
            
        if result and result.get('success'):
            return jsonify({
                "success": True,
                "text": greeting_text,
                "audio": result.get('audio', ''),
                "sample_rate": result.get('sample_rate', 24000)
            })
        else:
            return jsonify({"success": False, "error": result.get('error', 'TTS failed')}), 500
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500