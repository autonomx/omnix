from rpg.models.npc import NPC


def build_prompt(npc, scene, memory):
    # Determine tone based on emotional state
    dominant_emotion = max(npc.emotional_state.items(), key=lambda x: x[1])
    emotion_name, intensity = dominant_emotion

    tone = "neutral"
    if intensity > 0.7:
        if emotion_name == "angry":
            tone = "aggressive"
        elif emotion_name == "fearful":
            tone = "hesitant"
        elif emotion_name == "happy":
            tone = "enthusiastic"

    return f"""
You are an RPG narration engine.

Return ONLY valid JSON. No explanation, no text outside JSON.

If you fail, the system will discard your response.

STRICT FORMAT:
{{
  "description": string,
  "dialogue": string,
  "emotion": "neutral" | "angry" | "happy" | "fearful"
}}

Tone: {tone}
NPC Personality: {npc.personality}
Goal: {npc.current_goal.type if npc.current_goal else "none"}
Scene: {scene.summary}
Recent Memory: {memory}

Respond ONLY with JSON.
"""