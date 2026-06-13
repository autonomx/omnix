"""Split helpers for RPG world scene narration."""
from __future__ import annotations

# ruff: noqa: F401,F403,F405
from app.rpg.ai.world_scene_narrator_common import *
from app.rpg.ai.world_scene_narrator_dialogue_grounding import *
from app.rpg.ai.world_scene_narrator_service_grounding import *
from app.rpg.ai.world_scene_narrator_payloads import *
from app.rpg.ai.world_scene_narrator_structured import *
from app.rpg.ai.world_scene_narrator_prompts import *

class SceneNarrator:
    """Orchestrates scene narration with NPC reactions and player choices.

    This is the main entry point for Phase 5. It coordinates:
    1. Narrative generation from scene data
    2. NPC reaction generation
    3. Player choice generation
    4. Assembly into a complete NarrativeResult
    """

    def __init__(
        self,
        llm_gateway: Optional[Any] = None,
        *,
        default_tone: str = "dramatic",
        simulate_mode: bool = False,
    ):
        self.llm_gateway = llm_gateway
        self.default_tone = default_tone
        self.simulate_mode = simulate_mode
        self.live_mode = bool(llm_gateway) and not simulate_mode
        self._last_llm_success = False

    def narrate_scene(
        self,
        scene: Dict[str, Any],
        state: Dict[str, Any],
        *,
        tone: Optional[str] = None,
        include_npc_reactions: bool = True,
        include_choices: bool = True,
        max_npc_reactions: int = 3,
    ) -> NarrativeResult:
        """Generate a complete narrated scene.

        Args:
            scene: Scene dict to narrate.
            state: Current game state dict.
            tone: Override default tone.
            include_npc_reactions: Whether to generate NPC reactions.
            include_choices: Whether to generate player choices.
            max_npc_reactions: Max NPC reactions to generate.

        Returns:
            NarrativeResult with narrative, choices, and NPC reactions.
        """
        tone = tone or self.default_tone

        # Step 1: Generate narrative
        narrative = self._generate_narrative(scene, state, tone=tone)

        # Step 2: Generate NPC reactions
        npc_reactions: List[NPCReaction] = []
        if include_npc_reactions:
            npc_reactions = self._generate_npc_reactions(
                scene, narrative, state,
                max_reactions=max_npc_reactions,
            )

        # Step 3: Generate choices
        choices: List[Dict[str, Any]] = []
        if include_choices:
            choices = self._generate_choices(scene, narrative)

        # Step 4: Build dialogue blocks from NPC reactions
        dialogue_blocks = [
            {
                "speaker": r.npc_name,
                "npc_id": r.npc_id,
                "text": r.dialogue,
                "emotion": r.emotion,
            }
            for r in npc_reactions
            if r.dialogue
        ]

        # Phase 8: player-facing packaged view
        player_view = {
            "scene_id": scene.get("scene_id") or scene.get("id", ""),
            "scene_title": scene.get("title", ""),
            "mode": "scene",
            "active_npc_id": (
                npc_reactions[0].npc_id
                if npc_reactions
                else ""
            ),
            "encounter": build_encounter_view(scene, state),
            "active_rumors": list(scene.get("active_rumors") or [])[:3],
            "active_alliances": list(scene.get("active_alliances") or [])[:3],
            "faction_positions": dict(scene.get("faction_positions") or {}),
        }

        llm_success = getattr(self, "_last_llm_success", False)

        return NarrativeResult(
            narrative=narrative,
            choices=choices,
            npc_reactions=npc_reactions,
            dialogue_blocks=dialogue_blocks,
            metadata={
                "tone": tone,
                "scene_id": scene.get("id"),
                "npc_count": len(npc_reactions),
                "choice_count": len(choices),
                "llm_live": bool(self.live_mode and llm_success),
                "llm_attempted": bool(self.live_mode),
                "llm_fallback_used": not llm_success,
                "player_view": player_view,
                "sandbox_summary": scene.get("sandbox_summary", {}),
            },
        )

    def _generate_narrative(
        self,
        scene: Dict[str, Any],
        state: Dict[str, Any],
        tone: str,
    ) -> str:
        """Generate narrative text for a scene."""
        # Inject player_input from state into scene so simulation fallback sees it
        scene = dict(scene or {})
        if "player_input" not in scene and state:
            pi = state.get("player_input", "")
            if pi:
                scene["player_input"] = str(pi)

        if not self.live_mode:
            return self._simulate_narrative(scene, tone)

        try:
            prompt = build_scene_prompt(scene, state, tone=tone)
            response = _llm_text(self.llm_gateway, prompt, context={"scene": scene})
            parsed = parse_scene_response(response)
            narrative = parsed.get("narrative") or ""

            if narrative:
                self._last_llm_success = True
                return narrative
        except Exception:
            pass

        # fallback
        self._last_llm_success = False
        return self._simulate_narrative(scene, tone)

    def _generate_npc_reactions(
        self,
        scene: Dict[str, Any],
        narrative: str,
        state: Dict[str, Any],
        *,
        max_reactions: int = 3,
    ) -> List[NPCReaction]:
        """Generate NPC reactions for actors in the scene."""
        actors = scene.get("actors", [])
        if isinstance(actors, dict):
            actor_list = [{"id": k, "name": k, **v} for k, v in actors.items()]
        elif isinstance(actors, list):
            actor_list = [
                a if isinstance(a, dict) else {"id": a, "name": str(a)}
                for a in actors
            ]
        else:
            actor_list = [{"id": "unknown", "name": str(actors)}]

        reactions: List[NPCReaction] = []
        for actor in actor_list[:max_reactions]:
            npc_id = actor.get("id", "unknown")
            npc_name = actor.get("name", "Unknown")

            if not self.live_mode:
                reaction = self._simulate_npc_reaction(npc_name)
            else:
                try:
                    prompt = build_npc_reaction_prompt(actor, scene, narrative, state=state)
                    response = _llm_text(self.llm_gateway, prompt, context={"npc": npc_id})
                    reaction = parse_npc_reaction(response, npc_id=npc_id, npc_name=npc_name)
                    if reaction and reaction.reaction:
                        self._last_llm_success = True
                    else:
                        raise ValueError("empty reaction")
                except Exception:
                    self._last_llm_success = False
                    reaction = self._simulate_npc_reaction(npc_name)

            reactions.append(reaction)

        return reactions

    def _generate_choices(
        self,
        scene: Dict[str, Any],
        narrative: str,
    ) -> List[Dict[str, Any]]:
        """Generate player choices."""
        source = scene.get("id", scene.get("source", ""))
        action_hooks = scene.get("action_hooks", None)

        if not self.live_mode:
            return self._simulate_choices(scene, source)

        try:
            prompt = build_choice_prompt(scene, narrative, action_hooks=action_hooks)
            response = _llm_text(self.llm_gateway, prompt, context={"scene": scene.get("id")})
            parsed = parse_choices(response, source=source)
            if parsed:
                self._last_llm_success = True
                return parsed
        except Exception:
            pass

        self._last_llm_success = False
        return self._simulate_choices(scene, source)

    # ------------------------------------------------------------------
    # Simulation fallbacks (no LLM required)
    # ------------------------------------------------------------------

    @staticmethod
    def _simulate_narrative(scene: Dict[str, Any], tone: str) -> str:
        """Generate simulated narrative text without LLM.

        Incorporates player input and scene actors for varied responses.
        """
        title = scene.get("title", "The Scene")
        summary = scene.get("summary", "Events unfold around you.")
        stakes = scene.get("stakes", "much is at stake")
        player_input = scene.get("player_input", "")
        actors_data = scene.get("actors", [])

        # Extract NPC names from actor dicts
        npc_names = []
        if isinstance(actors_data, list):
            for a in actors_data[:5]:
                if isinstance(a, dict):
                    name = a.get("name", a.get("id", ""))
                    if name:
                        npc_names.append(str(name))
                else:
                    npc_names.append(str(a))
        elif isinstance(actors_data, dict):
            npc_names = list(actors_data.keys())[:5]

        npc_text = f"{', '.join(npc_names)} {'are' if len(npc_names) != 1 else 'is'} {'present' if npc_names else 'absent'}" if npc_names else "You are alone for now"

        # Acknowledge player's action
        action_text = ""
        if player_input:
            action_lower = player_input.lower().strip()
            if any(w in action_lower for w in ("look", "observe", "see", "examine", "search")):
                action_text = "You carefully observe your surroundings. "
            elif any(w in action_lower for w in ("talk", "speak", "ask", "question", "whisper", "say")):
                npc = npc_names[0] if npc_names else "those nearby"
                action_text = f"You try to speak with {npc}. "
            elif any(w in action_lower for w in ("attack", "hit", "strike", "kill", "fight")):
                npc = npc_names[0] if npc_names else "your target"
                action_text = f"You lash out toward {npc}. "
            elif any(w in action_lower for w in ("move", "go", "walk", "run", "leave", "head")):
                loc = scene.get("location", "another area")
                action_text = f"You start to move toward {loc}. "
            elif any(w in action_lower for w in ("take", "grab", "pick up", "use")):
                action_text = "You reach for something. "
            else:
                action_text = f"Your words echo: \"{player_input[:80]}\". "
        else:
            action_text = "You hesitate, weighing your options. "

        title_scene = f"{title}\n\n" if title != "The Scene" else ""

        return (
            f"{title_scene}{action_text}"
            f"{summary}\n\n"
            f"{npc_text}, the weight of the moment pressing down. "
            f"The stakes are clear: {stakes}. "
            f"The air is thick with {tone} tension as the scene unfolds."
        )

    @staticmethod
    def _simulate_npc_reaction(npc_name: str) -> NPCReaction:
        """Generate a simulated NPC reaction without LLM."""
        emotions = ["tense", "curious", "determined", "cautious", "alert"]
        intents = ["observe", "act", "confront", "wait", "negotiate"]
        reactions = [
            f"{npc_name} considers the situation carefully.",
            f"{npc_name}'s expression grows serious.",
            f"{npc_name} shifts uneasily, weighing options.",
            f"{npc_name} meets your gaze with quiet resolve.",
        ]
        dialogues = [
            "We should act quickly.",
            "This changes everything.",
            "I've seen this before.",
            "What do you think we should do?",
        ]
        # Use hash of name for deterministic selection
        idx = hash(npc_name)
        return NPCReaction(
            npc_id=npc_name.lower().replace(" ", "_"),
            npc_name=npc_name,
            reaction=reactions[idx % len(reactions)],
            dialogue=dialogues[idx % len(dialogues)],
            emotion=emotions[idx % len(emotions)],
            intent=intents[idx % len(intents)],
        )

    @staticmethod
    def _simulate_choices(scene: Dict[str, Any], source: str = "") -> List[Dict[str, Any]]:
        """Generate simulated choices without LLM.

        Adapts choices based on player input for more relevant options.
        """
        player_input = scene.get("player_input", "").lower().strip() if isinstance(scene.get("player_input", ""), str) else ""

        # Base choice pool — rotate based on what player did
        if player_input:
            if any(w in player_input for w in ("talk", "speak", "ask", "question")):
                # After talking, offer follow-up options
                return [
                    {"id": "choice_1", "text": "Press for more information", "type": "dialogue", "action": {"type": "escalate_conflict", "target_id": source}},
                    {"id": "choice_2", "text": "Change the subject", "type": "dialogue", "action": {"type": "intervene_thread", "target_id": source}},
                    {"id": "choice_3", "text": "Step back and consider", "type": "observe", "action": {"type": "observe_situation", "target_id": source}},
                ]
            elif any(w in player_input for w in ("look", "observe", "see", "examine", "search")):
                # After observing, offer action options
                return [
                    {"id": "choice_1", "text": "Act on what you've learned", "type": "action", "action": {"type": "intervene_thread", "target_id": source}},
                    {"id": "choice_2", "text": "Investigate further", "type": "observe", "action": {"type": "observe_situation", "target_id": source}},
                    {"id": "choice_3", "text": "Share your findings", "type": "dialogue", "action": {"type": "escalate_conflict", "target_id": source}},
                ]
            elif any(w in player_input for w in ("attack", "hit", "strike", "kill", "fight", "draw")):
                # After combat action, offer escalation
                return [
                    {"id": "choice_1", "text": "Press the attack", "type": "action", "action": {"type": "escalate_conflict", "target_id": source}},
                    {"id": "choice_2", "text": "Stand down", "type": "observe", "action": {"type": "intervene_thread", "target_id": source}},
                    {"id": "choice_3", "text": "Call for parley", "type": "dialogue", "action": {"type": "intervene_thread", "target_id": source}},
                ]
            elif any(w in player_input for w in ("move", "go", "walk", "run", "leave", "head")):
                # After movement
                return [
                    {"id": "choice_1", "text": "Continue forward", "type": "action", "action": {"type": "intervene_thread", "target_id": source}},
                    {"id": "choice_2", "text": "Reassess your route", "type": "observe", "action": {"type": "observe_situation", "target_id": source}},
                    {"id": "choice_3", "text": "Return to where you started", "type": "action", "action": {"type": "intervene_thread", "target_id": source}},
                ]

        # Default varied choices
        return [
            {"id": "choice_1", "text": "Take decisive action", "type": "action", "action": {"type": "intervene_thread", "target_id": source}},
            {"id": "choice_2", "text": "Observe the situation carefully", "type": "observe", "action": {"type": "observe_situation", "target_id": source}},
            {"id": "choice_3", "text": "Speak with those present", "type": "dialogue", "action": {"type": "escalate_conflict", "target_id": source}},
        ]


# ---------------------------------------------------------------------------
# Convenience functions (service layer)
# ---------------------------------------------------------------------------

def _generate_live_narrative(
    scene: Dict[str, Any],
    narration_context: Dict[str, Any],
    llm_gateway: Any,
    tone: str = "dramatic",
    retry_on_invalid: bool = True,
    debug_logging: bool = False,
    on_chunk: Optional[Callable[[str], None]] = None,
    require_live_llm: bool = False,
) -> str:
    """Generate narrative using LLM."""
    # Inject player_input from narration_context into scene
    scene = dict(scene or {})
    if "player_input" not in scene and narration_context:
        pi = narration_context.get("player_input", "")
        if pi:
            scene["player_input"] = str(pi)

    prompt = build_scene_prompt(scene, narration_context, tone=tone)
    if debug_logging:
        logger.warning("[RPG LLM PROMPT]\n%s", prompt)
    else:
        logger.debug("[RPG LLM PROMPT] prompt length: %d", len(prompt))
    max_attempts = 2 if retry_on_invalid else 1
    llm_narrative = ""

    logger.info(
        "[RPG NARRATOR] live_narrative_start prompt_len=%d retry_on_invalid=%s max_attempts=%d",
        len(prompt),
        retry_on_invalid,
        max_attempts,
    )

    import time

    for attempt in range(max_attempts):
        attempt_t0 = time.monotonic()
        logger.info("[RPG NARRATOR] attempt_start attempt=%d/%d", attempt + 1, max_attempts)
        try:
            response = _llm_text(llm_gateway, prompt, context={}, on_chunk=on_chunk if attempt == 0 else None)
            print("[LLM RAW]", repr(response)[:500])
            llm_narrative = _extract_llm_text(response)
            print("[LLM TEXT]", repr(llm_narrative)[:500])
            logger.info(
                "[RPG NARRATOR] attempt_end attempt=%d/%d dt=%.3fs response_len=%d",
                attempt + 1,
                max_attempts,
                time.monotonic() - attempt_t0,
                len(str(llm_narrative or "")),
            )
            if debug_logging:
                logger.warning("[RPG LLM RAW OUTPUT attempt %d]\n%s", attempt + 1, llm_narrative)
            else:
                logger.debug("[RPG LLM RAW OUTPUT attempt %d] length: %d", attempt + 1, len(str(llm_narrative or "")))

            # Check if response contains invalid content (like ambient updates)
            response_lower = _safe_str(llm_narrative).lower()
            if any(phrase in response_lower for phrase in [
                "faction loyalty baseline",
                "maintain awareness",
                "playertick",
                "📜 📜"
            ]):
                logger.error("LLM response contains invalid ambient-like content, rejecting: %s", llm_narrative[:200])
                continue

            parsed = parse_scene_response(llm_narrative)
            if debug_logging:
                logger.warning("[RPG PARSED RESPONSE]\n%s", parsed)
            else:
                logger.debug("[RPG PARSED RESPONSE] keys: %s", list(parsed.keys()) if isinstance(parsed, dict) else type(parsed))

            if _is_valid_scene_response(parsed):
                logger.debug("LLM response validation successful")
                return llm_narrative
            else:
                logger.warning(
                    "[RPG NARRATOR] attempt_rejected attempt=%d/%d reason=invalid_scene_format",
                    attempt + 1,
                    max_attempts,
                )
                logger.error("LLM response failed validation, parsed: %s", parsed)
        except Exception as exc:
            print("[RPG][narrator] provider call failed", {
                "error": repr(exc),
                "traceback": traceback.format_exc()[-4000:],
            })
            if require_live_llm:
                raise
            logger.exception("Exception during LLM narration")

    # fallback if LLM fails format - return raw text for recovery
    logger.error("Structured RPG narration LLM output failed validation after %d attempt(s), returning raw text", max_attempts)
    if require_live_llm:
        raise RuntimeError(
            "live_llm_required_but_llm_failed: empty_response_from_provider"
        )
    return (
        llm_narrative
        if 'llm_narrative' in locals() and llm_narrative
        else _structured_fallback_response(narration_context)
    )


def _simulate_narrative(scene: Dict[str, Any], narration_context: Dict[str, Any], tone: str = "dramatic") -> str:
    """Generate simulated narrative text without LLM.

    Incorporates player input and scene actors for varied responses.
    """
    title = scene.get("title", "The Scene")
    summary = scene.get("summary", "Events unfold around you.")
    stakes = scene.get("stakes", "much is at stake")
    player_input = narration_context.get("player_input", scene.get("player_input", ""))
    actors_data = scene.get("actors", [])

    # Extract NPC names from actor dicts
    npc_names = []
    if isinstance(actors_data, list):
        for a in actors_data[:5]:
            if isinstance(a, dict):
                name = a.get("name", a.get("id", ""))
                if name:
                    npc_names.append(str(name))
            else:
                npc_names.append(str(a))
    elif isinstance(actors_data, dict):
        npc_names = list(actors_data.keys())[:5]

    npc_text = f"{', '.join(npc_names)} {'are' if len(npc_names) != 1 else 'is'} {'present' if npc_names else 'absent'}" if npc_names else "You are alone for now"

    # Acknowledge player's action
    action_text = ""
    if player_input:
        action_lower = player_input.lower().strip()
        if any(w in action_lower for w in ("look", "observe", "see", "examine", "search")):
            action_text = "You carefully observe your surroundings. "
        elif any(w in action_lower for w in ("talk", "speak", "ask", "question", "whisper", "say")):
            npc = npc_names[0] if npc_names else "those nearby"
            action_text = f"You try to speak with {npc}. "
        elif any(w in action_lower for w in ("attack", "hit", "strike", "kill", "fight")):
            npc = npc_names[0] if npc_names else "your target"
            action_text = f"You lash out toward {npc}. "
        elif any(w in action_lower for w in ("move", "go", "walk", "run", "leave", "head")):
            loc = scene.get("location", "another area")
            action_text = f"You start to move toward {loc}. "
        elif any(w in action_lower for w in ("take", "grab", "pick up", "use")):
            action_text = "You reach for something. "
        else:
            action_text = f"Your words echo: \"{player_input[:80]}\". "
    else:
        action_text = "You hesitate, weighing your options. "

    title_scene = f"{title}\n\n" if title != "The Scene" else ""

    return (
        f"{title_scene}{action_text}"
        f"{summary}\n\n"
        f"{npc_text}, the weight of the moment pressing down. "
        f"The stakes are clear: {stakes}. "
        f"The air is thick with {tone} tension as the scene unfolds."
    )


def narrate_scene(
    scene: Dict[str, Any],
    narration_context: Dict[str, Any],
    llm_gateway: Any | None = None,
    tone: str = "dramatic",
    retry_on_invalid: bool = True,
    debug_logging: bool = False,
    on_chunk: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    scene = _safe_dict(scene)
    narration_context = _safe_dict(narration_context)
    require_live_llm = _force_live_llm_required(narration_context)
    print("[RPG][narrator] entering narrate_scene", {
        "require_live_llm": require_live_llm,
        "has_turn_contract": bool(_safe_dict(narration_context.get("turn_contract"))),
        "has_resolved_result": bool(_safe_dict(narration_context.get("resolved_result"))),
    })
    turn_id = narration_context.get("turn_id")
    if turn_id and turn_id in _ACTIVE_NARRATIONS:
        if require_live_llm:
            raise RuntimeError("live_llm_required_but_narrator_fallback_selected")
        return {
            "narration": "",
            "used_llm": False,
            "raw_llm_narrative": "",
            "narration_json": {},
            "speaker_presentation": {},
            "format_warning": False,
        }
    if turn_id:
        _ACTIVE_NARRATIONS.add(turn_id)
    try:
        try_ambient = _safe_str(narration_context.get("mode")) == "ambient_conversation"
        if try_ambient:
            if require_live_llm:
                raise RuntimeError("live_llm_required_but_ambient_fallback_selected")
            text = _build_ambient_conversation_line(narration_context)
            return {
                "narration": text,
                "structured_narration": {"markdown": text, "speaker_turns": []},
                "speaker_turns": [],
                "used_llm": False,
                "raw_llm_narrative": "",
                "llm_error": False,
            }

        turn_contract = _safe_dict(narration_context.get("turn_contract"))
        state_snapshot = _safe_dict(narration_context.get("simulation_state"))
        runtime_settings = _safe_dict(
            narration_context.get("runtime_settings")
            or narration_context.get("settings")
        )
        grounding_settings = normalize_grounding_settings(
            _safe_dict(runtime_settings.get("grounding"))
        )

        if llm_gateway:
            print("[RPG][narrator] provider resolved", {
                "provider_type": type(llm_gateway).__name__ if llm_gateway else "",
                "provider_truthy": bool(llm_gateway),
            })

            if require_live_llm and not llm_gateway:
                raise RuntimeError("live_llm_required_but_no_provider_available")

            llm_narrative = _generate_live_narrative(
                scene,
                narration_context,
                llm_gateway=llm_gateway,
                tone=tone,
                retry_on_invalid=retry_on_invalid,
                debug_logging=debug_logging,
                on_chunk=on_chunk,
                require_live_llm=require_live_llm,
            )

            # Parse JSON response with tolerant fallback
            parsed_json = _parse_llm_narration_payload(llm_narrative)
            print("[RPG][LLM PARSED]", parsed_json)
            if _safe_str(_safe_dict(parsed_json).get("format_version")) == "rpg_narration_candidates_v1":
                narration_json = select_grounded_narration_candidate(
                    parsed_json,
                    turn_contract,
                    state_snapshot=state_snapshot,
                    grounding_settings=grounding_settings,
                    strict_named_fact_check=False,
                )
            elif parsed_json and _safe_str(parsed_json.get("format_version")) == "rpg_narration_v2":
                narration_json = select_grounded_narration_candidate(
                    _strict_narration_payload(parsed_json),
                    turn_contract,
                    state_snapshot=state_snapshot,
                    grounding_settings=grounding_settings,
                    strict_named_fact_check=False,
                )
            else:
                narration_json = select_grounded_narration_candidate(
                    _strict_narration_payload(_normalize_narration_json(parsed_json or {})),
                    turn_contract,
                    state_snapshot=state_snapshot,
                    grounding_settings=grounding_settings,
                    strict_named_fact_check=False,
                )

            print("[RPG][LLM RAW ACTION]", _safe_dict(parsed_json).get("action"))
            print("[RPG][STRICT ACTION]", narration_json.get("action"))

            if not narration_json.get("narration") and not narration_json.get("action") and not _safe_str(_safe_dict(narration_json.get("npc")).get("line")).strip():
                logger.warning("Narration JSON parse failed or empty; recovering from raw text")
                recovered_json = _strict_narration_payload(_recover_narration_from_raw_text(llm_narrative))
                narration_json = select_grounded_narration_candidate(
                    recovered_json,
                    turn_contract,
                    state_snapshot=state_snapshot,
                    grounding_settings=grounding_settings,
                    strict_named_fact_check=False,
                )

            print("[RPG][PRE-SANITIZE ACTION]", narration_json.get("action"))
            authoritative_action = _build_authoritative_action_line(narration_context)
            grounded_json = _sanitize_narration_payload(narration_json, scene, narration_context, authoritative_action=authoritative_action)
            if isinstance(narration_json, dict) and narration_json.get("grounding_validation"):
                grounded_json["grounding_validation"] = narration_json.get("grounding_validation")
            if isinstance(narration_json, dict) and narration_json.get("grounding_fallback"):
                grounded_json["grounding_fallback"] = True
                grounded_json["grounding_fallback_reason"] = narration_json.get("grounding_fallback_reason")

            print("[RPG][SANITIZED ACTION]", grounded_json.get("action"))

            parts = []

            if grounded_json["narration"]:
                parts.append(grounded_json["narration"])

            if authoritative_action:
                parts.append(authoritative_action)

            llm_action = _safe_str(grounded_json.get("action")).strip()
            if llm_action and llm_action != authoritative_action:
                parts.append(f"Result: {llm_action}")

            npc = _safe_dict(grounded_json.get("npc"))
            if npc.get("speaker") and npc.get("line"):
                parts.append(f"{npc['speaker']}: \"{npc['line']}\"")

            rendered_narration = _naturalize_service_debug_language("\n\n".join(parts).strip())

            return {
                "narration": rendered_narration,
                "used_llm": True,
                "raw_llm_narrative": llm_narrative,
                "narration_json": grounded_json,
                "grounding_validation": _safe_dict(grounded_json.get("grounding_validation")),
                "grounding_fallback": bool(grounded_json.get("grounding_fallback")),
                "speaker_presentation": {},
                "format_warning": False,
            }
        else:
            if require_live_llm:
                raise RuntimeError("live_llm_required_but_simulation_fallback_selected")
            llm_narrative = _simulate_narrative(scene, narration_context, tone=tone)
            simulated_json = _normalize_narration_json({
                "narration": llm_narrative,
                "action": _authoritative_action_text(narration_context),
                "npc": {"speaker": "", "line": ""},
                "reward": _authoritative_reward_text(narration_context),
                "followup_hooks": [],
            })
            narration_json = select_grounded_narration_candidate(
                _strict_narration_payload(simulated_json),
                turn_contract,
                state_snapshot=state_snapshot,
                grounding_settings=grounding_settings,
                strict_named_fact_check=False,
            )
            print("[RPG][LLM RAW ACTION]", _safe_dict(simulated_json).get("action"))
            print("[RPG][STRICT ACTION]", narration_json.get("action"))
            print("[RPG][PRE-SANITIZE ACTION]", narration_json.get("action"))
            authoritative_action = _build_authoritative_action_line(narration_context)
            grounded_json = _sanitize_narration_payload(narration_json, scene, narration_context, authoritative_action=authoritative_action)
            if isinstance(narration_json, dict) and narration_json.get("grounding_validation"):
                grounded_json["grounding_validation"] = narration_json.get("grounding_validation")
            if isinstance(narration_json, dict) and narration_json.get("grounding_fallback"):
                grounded_json["grounding_fallback"] = True
                grounded_json["grounding_fallback_reason"] = narration_json.get("grounding_fallback_reason")

            print("[RPG][SANITIZED ACTION]", grounded_json.get("action"))

            parts = []

            if grounded_json["narration"]:
                parts.append(grounded_json["narration"])

            if authoritative_action:
                parts.append(authoritative_action)

            llm_action = _safe_str(grounded_json.get("action")).strip()
            if llm_action and llm_action != authoritative_action:
                parts.append(f"Result: {llm_action}")

            npc = _safe_dict(grounded_json.get("npc"))
            if npc.get("speaker") and npc.get("line"):
                parts.append(f"{npc['speaker']}: \"{npc['line']}\"")

            rendered_narration = _naturalize_service_debug_language("\n\n".join(parts).strip())

            return {
                "narration": rendered_narration,
                "used_llm": False,
                "raw_llm_narrative": llm_narrative,
                "narration_json": grounded_json,
                "grounding_validation": _safe_dict(grounded_json.get("grounding_validation")),
                "grounding_fallback": bool(grounded_json.get("grounding_fallback")),
                "speaker_presentation": {},
                "format_warning": False,
            }
    finally:
        if turn_id:
            _ACTIVE_NARRATIONS.discard(turn_id)


def play_scene(
    scene: Dict[str, Any],
    state: Dict[str, Any],
    *,
    llm_gateway: Optional[Any] = None,
    tone: str = "dramatic",
) -> Dict[str, Any]:
    """Play a scene and return narrated result as dict.

    This is the main service function called by routes.

    Args:
        scene: Scene dict to play.
        state: Game state dict.
        llm_gateway: Optional LLM gateway for real narration.
        tone: Narrative tone.

    Returns:
        Dict suitable for JSON response.
    """
    narrator = SceneNarrator(
        llm_gateway=llm_gateway,
        default_tone=tone,
        simulate_mode=not bool(llm_gateway),
    )
    result = narrator.narrate_scene(scene, state, tone=tone)

    return {
        "narrative": result.narrative,
        "choices": result.choices,
        "npc_reactions": [
            {
                "npc_id": r.npc_id,
                "npc_name": r.npc_name,
                "dialogue": r.dialogue,
                "emotion": r.emotion,
                "intent": r.intent,
            }
            for r in result.npc_reactions
        ],
        "dialogue_blocks": result.dialogue_blocks,
        "metadata": result.metadata,
    }


def apply_legacy_narration_emphasis(narration_payload: dict) -> dict:
    """Apply markdown emphasis to important narration elements.

    Deterministically formats structured result fields — does NOT ask
    the LLM to bold things randomly.
    """
    import re
    payload = dict(narration_payload or {})
    text = str(payload.get("narration") or payload.get("text") or payload.get("content") or "")

    if not text:
        return payload

    # Bold item names (from items list if available)
    items = payload.get("items", [])
    for item in (items if isinstance(items, list) else []):
        if isinstance(item, dict):
            name = str(item.get("name", ""))
            if name and len(name) > 2:
                text = text.replace(name, f"**{name}**")

    # Bold quest updates
    text = re.sub(r'(?i)(quest updated?:?\s*)', r'**\1**', text)
    text = re.sub(r'(?i)(quest complete[d]?:?\s*)', r'**\1**', text)

    # Bold damage numbers
    text = re.sub(r'(\d+)\s+(damage)', r'**\1 \2**', text)

    # Bold level ups
    text = re.sub(r'(?i)(level up!?)', r'**\1**', text)
    text = re.sub(r'(?i)(leveled? up!?)', r'**\1**', text)

    # Bold named enemies in combat results
    combat = payload.get("combat_result", {})
    if isinstance(combat, dict):
        enemy_name = str(combat.get("enemy_name") or combat.get("target_name") or "")
        if enemy_name and len(enemy_name) > 2:
            text = text.replace(enemy_name, f"**{enemy_name}**")

    # Avoid double-bold
    text = text.replace("****", "**")

    # Update payload
    if "narration" in payload:
        payload["narration"] = text
    elif "text" in payload:
        payload["text"] = text
    elif "content" in payload:
        payload["content"] = text

    return payload


# ── Living-world: ambient narration (Phase 5) ─────────────────────────────

__all__ = [name for name in globals() if not name.startswith("__")]
