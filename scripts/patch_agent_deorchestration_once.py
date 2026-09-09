from __future__ import annotations

from pathlib import Path
import re


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def sub_once(path: str, pattern: str, replacement: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{path}: expected one regex match, found {count}: {pattern[:120]!r}")
    target.write_text(updated, encoding="utf-8")


# ---------------------------------------------------------------------------
# Planning becomes an advisory working artifact for ordinary coding. Hard plan
# authority remains only for consequential mutations.
# ---------------------------------------------------------------------------
replace_once(
    "src/app/agent_runtime/planning_contracts.py",
    'PlanningMode = Literal["off", "shadow", "enforce"]\n',
    'PlanningMode = Literal["off", "shadow", "enforce"]\nPlanningRequirement = Literal["free", "advisory", "hard"]\n',
)
replace_once(
    "src/app/agent_runtime/planning_contracts.py",
    '    mode: PlanningMode = "shadow"\n    tool_name: str\n',
    '    mode: PlanningMode = "shadow"\n    planning_requirement: PlanningRequirement = "advisory"\n    tool_name: str\n',
)

planning = Path("src/app/agent_runtime/planning.py")
text = planning.read_text(encoding="utf-8")
text = text.replace(
    '    PlanningMode,\n)',
    '    PlanningMode,\n    PlanningRequirement,\n)',
    1,
)
text = text.replace(
    '    value = str(source.get("OMNIX_AGENT_PLANNING_MODE", "shadow") or "shadow").strip().casefold()\n',
    '    value = str(source.get("OMNIX_AGENT_PLANNING_MODE", "enforce") or "enforce").strip().casefold()\n',
    1,
)
text, count = re.subn(
    r'def derive_planning_lenses\(revision: TaskRevision\) -> list\[str\]:\n.*?\n\ndef extract_change_literals',
    '''def derive_planning_lenses(revision: TaskRevision) -> list[str]:
    """Return no server-authored semantic task taxonomy.

    Pi owns ordinary semantic planning. Omnix persists model-supplied working-plan
    metadata and deterministic authority/evidence, but does not classify the task
    into UI/API/persistence/refactor lenses with regexes.
    """

    del revision
    return []


def extract_change_literals''',
    text,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit("planning.py: derive_planning_lenses replacement failed")
text, count = re.subn(
    r'def extract_change_literals\(revision: TaskRevision\) -> list\[str\]:\n.*?\n\ndef capture_planning_baseline',
    '''def extract_change_literals(revision: TaskRevision) -> list[str]:
    """Deprecated semantic helper retained for compatibility.

    Literal discovery is now explicitly requested by Pi through ``omnix_plan
    inspect`` instead of inferred by Omnix from arbitrary user language.
    """

    del revision
    return []


def capture_planning_baseline''',
    text,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit("planning.py: extract_change_literals replacement failed")
text = text.replace(
    '    for query in [*extract_change_literals(revision), *queries]:\n',
    '    for query in queries:\n',
    1,
)

# Simplify PlanGate to structural closure and workspace authority. Semantic
# coverage/candidate/causal judgments are Pi/reviewer intelligence, not server
# permission.
start = text.index('def plan_gate_failures(')
end = text.index('\ndef classify_operation_effect', start)
new_gate = '''def plan_gate_failures(
    spec: AgentRunSpec,
    revision: TaskRevision,
    submission: ImplementationPlanSubmission,
    candidates: Sequence[ImpactCandidate],
    evidence: Sequence[InspectionEvidence],
) -> list[str]:
    """Validate a persisted working/hard plan without reimplementing Pi reasoning.

    Omnix checks identity closure, workspace scope and explicit references. It no
    longer requires every requirement/candidate to be semantically classified,
    invents task lenses, or demands causal/waiver theories for ordinary coding.
    """

    failures: list[str] = []
    all_requirement_ids = {item.id for item in revision.requirements}
    plan_items = {item.id: item for item in submission.changes}
    candidate_map = {item.candidate_id: item for item in candidates}
    authoritative_validation_ids = {item.id for item in revision.validation_plan}
    custom_validation_ids = {item.id for item in submission.validations}
    validation_ids = authoritative_validation_ids | custom_validation_ids
    evidence_ids = {item.evidence_id for item in evidence}

    for validation in submission.validations:
        if validation.id in authoritative_validation_ids:
            failures.append(f"plan_validation_shadows_authoritative:{validation.id}")
        for requirement_id in validation.requirement_ids:
            if requirement_id not in all_requirement_ids:
                failures.append(f"validation_unknown_requirement:{validation.id}:{requirement_id}")

    workspace = spec.workspace
    authority = None
    if workspace is not None:
        authority = WorkspaceAuthority(
            workspace.worktree or workspace.root,
            allowed_paths=list(workspace.allowed_paths),
            forbidden_paths=list(workspace.forbidden_paths),
        )

    for item in submission.changes:
        for requirement_id in item.requirement_ids:
            if requirement_id not in all_requirement_ids:
                failures.append(f"plan_item_unknown_requirement:{item.id}:{requirement_id}")
        for candidate_id in item.candidate_ids:
            if candidate_id not in candidate_map:
                failures.append(f"plan_item_unknown_candidate:{item.id}:{candidate_id}")
        for validation_id in item.validation_ids:
            if validation_id not in validation_ids:
                failures.append(f"plan_item_unknown_validation:{item.id}:{validation_id}")
        for path in item.paths:
            if _plan_path_too_broad(path):
                failures.append(f"plan_path_too_broad:{item.id}:{path}")
            if authority is not None:
                try:
                    authority.resolve_path(path)
                except WorkspacePolicyError:
                    failures.append(f"plan_path_outside_workspace:{item.id}:{path}")

    for row in submission.requirement_coverage:
        if row.requirement_id not in all_requirement_ids:
            failures.append(f"coverage_unknown_requirement:{row.requirement_id}")
        for plan_item_id in row.plan_item_ids:
            if plan_item_id not in plan_items:
                failures.append(f"requirement_unknown_plan_item:{row.requirement_id}:{plan_item_id}")
        for validation_id in row.validation_ids:
            if validation_id not in validation_ids:
                failures.append(f"requirement_unknown_validation:{row.requirement_id}:{validation_id}")

    for disposition in submission.impacts:
        if disposition.candidate_id not in candidate_map:
            failures.append(f"impact_disposition_unknown_candidate:{disposition.candidate_id}")
            continue
        if not set(disposition.evidence_ids).issubset(evidence_ids):
            failures.append(f"impact_disposition_unknown_evidence:{disposition.candidate_id}")
        if not set(disposition.waiver_proof_ids).issubset(evidence_ids):
            failures.append(f"high_risk_waiver_unknown_proof:{disposition.candidate_id}")
        if disposition.disposition == "modify":
            candidate = candidate_map[disposition.candidate_id]
            linked = [item for item in submission.changes if candidate.candidate_id in item.candidate_ids]
            if linked and not any(
                _path_matches(path, candidate.path)
                for item in linked
                for path in item.paths
            ):
                failures.append(f"impact_modify_path_not_planned:{candidate.candidate_id}:{candidate.path}")

    for hypothesis in submission.causal_hypotheses:
        if not set(hypothesis.evidence_ids).issubset(evidence_ids):
            failures.append("causal_hypothesis_unknown_evidence")

    if submission.blockers:
        failures.extend(f"plan_blocker:{index + 1}" for index, _ in enumerate(submission.blockers))

    return list(dict.fromkeys(failures))


_CONSEQUENTIAL_BASENAMES = {
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb",
    "pyproject.toml", "poetry.lock", "uv.lock", "requirements.txt", "setup.py", "setup.cfg",
    "pom.xml", "build.gradle", "build.gradle.kts", "cargo.toml", "cargo.lock",
    "openapi.json", "openapi.yaml", "openapi.yml",
}
_CONSEQUENTIAL_COMMAND = re.compile(
    r"(?:\\bnpm(?:\\.cmd)?\\s+(?:--prefix\\s+\\S+\\s+)*(?:install|i|add|update|uninstall|remove)\\b|"
    r"\\b(?:makemigrations|alembic\\s+revision|codegen|generate(?:[-_:][A-Za-z0-9_.-]+)?)\\b|"
    r"\\bgit\\s+(?:push|commit|merge|rebase|reset\\s+--hard|clean)\\b|"
    r"\\brm\\s+-rf\\b|\\bremove-item\\b[^\\r\\n]*\\b-recurse\\b)",
    re.I,
)


def consequential_path(path: str | None) -> bool:
    normalized = str(path or "").replace("\\\\", "/").strip().lstrip("./").casefold()
    if not normalized:
        return False
    basename = normalized.rsplit("/", 1)[-1]
    if basename in _CONSEQUENTIAL_BASENAMES or basename.startswith("requirements") and basename.endswith(".txt"):
        return True
    segments = [segment for segment in normalized.split("/") if segment]
    if "migrations" in segments or ("alembic" in segments and "versions" in segments):
        return True
    if "generated" in segments or "/api/generated/" in f"/{normalized}/":
        return True
    if basename.startswith("schema.") and basename.endswith((".sql", ".json", ".yaml", ".yml")):
        return True
    return False


def planning_requirement_for_operation(
    effect: OperationEffect,
    *,
    target_path: str | None = None,
    command: str = "",
) -> PlanningRequirement:
    """Return the authority level for one operation.

    Normal in-scope source/test edits are Pi-managed and advisory. Omnix hard
    planning is reserved for changes whose blast radius or external consequence
    is not safely represented by a single ordinary edit.
    """

    if effect in {"read", "validate"}:
        return "free"
    if effect in {"external_mutate", "unknown"}:
        return "hard"
    if target_path and consequential_path(target_path):
        return "hard"
    normalized = str(command or "").strip()
    if normalized and _CONSEQUENTIAL_COMMAND.search(normalized):
        return "hard"
    if normalized and any(consequential_path(path) for path in command_target_paths(normalized)):
        return "hard"
    return "advisory"


def plan_requires_hard_planning(plan: ImplementationPlanRevision | None) -> bool:
    if plan is None:
        return False
    for item in plan.changes:
        if any(consequential_path(path) for path in item.paths):
            return True
        for hint in item.command_hints:
            effect = "unknown" if "unknown" in item.allowed_effects else "mutate"
            if planning_requirement_for_operation(effect, command=hint) == "hard":
                return True
    return False

'''
text = text[:start] + new_gate + text[end+1:]

# Replace operation-plan authority semantics: only hard operations consume plan
# authority. Normal edit/write paths may evolve without PlanDelta round trips.
start = text.index('def operation_plan_failures(')
end = text.index('\ndef plan_conformance_failures', start)
new_op = '''def operation_plan_failures(
    plan: ImplementationPlanRevision | None,
    revision: TaskRevision,
    *,
    effect: OperationEffect,
    target_path: str | None = None,
    command: str = "",
    current_evidence_digest: str | None = None,
    quality_stage: dict[str, object] | None = None,
) -> list[str]:
    del quality_stage
    requirement = planning_requirement_for_operation(
        effect,
        target_path=target_path,
        command=command,
    )
    if requirement != "hard":
        return []
    if plan is None:
        return ["approved_plan_missing"]
    failures: list[str] = []
    if plan.status != "approved":
        failures.append(f"plan_not_approved:{plan.status}")
    if plan.task_revision_id != revision.revision_id:
        failures.append("plan_task_revision_stale")
    if plan.authority.engineering_contract_digest != engineering_contract_digest(revision):
        failures.append("plan_engineering_contract_stale")
    if current_evidence_digest is not None and plan.authority.inspection_evidence_digest != current_evidence_digest:
        failures.append("plan_inspection_evidence_stale")

    if target_path:
        if not any(_path_matches(path, target_path) for path in planned_paths(plan)):
            failures.append(f"hard_mutation_not_in_plan:{target_path}")
    elif command:
        normalized = command.casefold()
        target_paths = command_target_paths(command)
        for target in target_paths:
            if consequential_path(target) and not any(_path_matches(path, target) for path in planned_paths(plan)):
                failures.append(f"hard_mutation_not_in_plan:{target}")
        explicit = any(
            effect in item.allowed_effects
            and any(normalized.startswith(hint.casefold()) for hint in item.command_hints)
            for item in plan.changes
        )
        path_referenced = any(path.casefold() in normalized for path in planned_paths(plan))
        if not explicit and not path_referenced:
            failures.append("hard_command_not_in_plan")
    else:
        failures.append("hard_operation_not_in_plan")
    return list(dict.fromkeys(failures))

'''
text = text[:start] + new_op + text[end+1:]

# Ordinary newly discovered source/test files are no longer conformance failures.
text = text.replace(
    '''    for path in sorted(run_owned):
        if not any(_path_matches(pattern, path) for pattern in patterns):
            failures.append(f"unplanned_modified_path:{path}")
''',
    '''    for path in sorted(run_owned):
        if consequential_path(path) and not any(_path_matches(pattern, path) for pattern in patterns):
            failures.append(f"unplanned_consequential_path:{path}")
''',
    1,
)
planning.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# Planning API: free/advisory operations never need plan authority; hard ones do.
# ---------------------------------------------------------------------------
api = Path("src/app/agent_runtime/planning_api.py")
text = api.read_text(encoding="utf-8")
text = text.replace(
    '    plan_gate_failures,\n    planned_paths,\n    planning_mode,\n',
    '    plan_gate_failures,\n    plan_requires_hard_planning,\n    planned_paths,\n    planning_mode,\n    planning_requirement_for_operation,\n',
    1,
)
# Do not invent semantic evidence/lenses when Pi did not request them.
text = text.replace(
    '''        if not evidence:
            fresh_evidence, fresh_candidates, _ = build_inspection_bundle(snapshot.spec, revision)
            for item in fresh_evidence:
                planning.add_inspection_evidence(item)
            for item in fresh_candidates:
                planning.add_impact_candidate(item)
            evidence = planning.list_inspection_evidence(run_id, task_revision_id=revision.revision_id)
            candidates = planning.list_impact_candidates(run_id, task_revision_id=revision.revision_id)

''',
    '',
    1,
)
text = text.replace(
    '''        server_lenses = derive_planning_lenses(revision)
        proposed = request.plan.model_copy(update={
            "previous_plan_revision_id": previous_id if amend else None,
            "planning_lenses": sorted(set(server_lenses) | set(request.plan.planning_lenses)),
        })
''',
    '''        proposed = request.plan.model_copy(update={
            "previous_plan_revision_id": previous_id if amend else None,
        })
''',
    1,
)
text = text.replace(
    '            "implementation may proceed"\n            if status == "approved"\n            else "inspect the reported gaps and submit an amended plan before implementation"\n',
    '            "working plan persisted; ordinary in-scope implementation may proceed"\n            if status == "approved"\n            else "fix structural plan errors; only consequential operations require hard plan approval"\n',
    1,
)
# Rewrite authorize endpoint body while preserving route/signature.
start = text.index('@router.post("/{run_id}/planning/authorize")')
new_authorize = '''@router.post("/{run_id}/planning/authorize")
def authorize_agent_planned_operation(
    run_id: str,
    request: PlanningAuthorizeRequest,
) -> dict[str, Any]:
    service = default_agent_run_service()
    snapshot = _load(service, run_id)
    mode = planning_mode()
    command = str(request.command or request.input.get("command") or "")
    target = str(request.path or request.input.get("path") or "").strip() or None
    effect = classify_operation_effect(request.tool_name, command=command)
    requirement = planning_requirement_for_operation(
        effect,
        target_path=target,
        command=command,
    )

    if mode == "off":
        return {
            "allowed": True,
            "would_block": False,
            "mode": mode,
            "effect": effect,
            "planning_requirement": requirement,
            "reasons": [],
        }

    with unit_of_work(service.database) as work:
        runs = PostgresAgentRunRepository(work.connection, service.context)
        quality = PostgresCodingQualityRepository(work.connection, service.context)
        planning = PostgresPlanningRepository(work.connection, service.context)
        revision = _current_revision(service, runs, run_id)
        state = planning.get_state(run_id)
        evidence = planning.list_inspection_evidence(run_id, task_revision_id=revision.revision_id)
        candidates = planning.list_impact_candidates(run_id, task_revision_id=revision.revision_id)
        plan = planning.latest_approved_plan(run_id, task_revision_id=revision.revision_id)

        reasons: list[str] = []
        if requirement == "hard":
            guidance_digest = _repository_guidance_digest(snapshot, revision, plan)
            reasons = operation_plan_failures(
                plan,
                revision,
                effect=effect,
                target_path=target,
                command=command,
                current_evidence_digest=inspection_evidence_digest(evidence),
                quality_stage=quality.get_stage(run_id),
            )
            reasons.extend(
                item for item in _plan_freshness_failures(
                    plan,
                    revision,
                    inspection_evidence_digest(evidence),
                    guidance_digest,
                )
                if item not in reasons
            )
            if state is None:
                reasons.append("planning_state_missing")
            else:
                if state.get("task_revision_id") != revision.revision_id:
                    reasons.append("planning_state_task_revision_stale")
                if str(state.get("status") or "") in {"rejected", "stale", "invalid", "required", "submitted"}:
                    reasons.append(f"latest_plan_state_not_approved:{state.get('status')}")
                active_id = str(state.get("active_plan_revision_id") or "") or None
                if plan is not None and active_id != plan.plan_revision_id:
                    reasons.append("planning_active_plan_identity_mismatch")
            if effect == "unknown" and command and not _unknown_command_is_explicitly_planned(plan, command):
                reasons.append("unknown_command_requires_explicit_plan_hint")
            if plan is not None:
                drift = plan_conformance_failures(snapshot.spec, plan, candidates)
                reasons.extend(
                    item for item in drift
                    if item.startswith("unplanned_consequential_path:")
                    or item.startswith("preexisting_dirty_path_modified:")
                    or item == "planning_base_commit_changed"
                )

        reasons = list(dict.fromkeys(reasons))
        would_block = requirement == "hard" and bool(reasons)
        allowed = not would_block or mode == "shadow"
        if would_block and plan is not None and _planning_state_should_stale(reasons):
            planning.mark_state_stale(run_id)
        decision = PlanningDecision(
            run_id=run_id,
            task_revision_id=revision.revision_id,
            plan_revision_id=plan.plan_revision_id if plan else None,
            mode=mode,
            planning_requirement=requirement,
            tool_name=request.tool_name,
            effect=effect,
            target=target or (command[:500] if command else None),
            allowed=allowed,
            would_block=would_block,
            reasons=reasons,
        )
        planning.add_decision(decision)
        work.commit()

    return {
        "allowed": allowed,
        "would_block": would_block,
        "mode": mode,
        "effect": effect,
        "planning_requirement": requirement,
        "plan_revision_id": plan.plan_revision_id if plan else None,
        "reasons": reasons,
        "reason": (
            "Omnix hard planning authority blocked this consequential operation: " + ", ".join(reasons)
            if not allowed else None
        ),
    }
'''
text = text[:start] + new_authorize + "\n"
# check endpoint remains before authorize; make its would_block reflect hard plans.
text = text.replace(
    '''    return {
        "mode": mode,
        "passed": not failures,
        "would_block": bool(failures),
        "plan_revision_id": plan.plan_revision_id if plan else None,
        "failures": failures,
    }
''',
    '''    hard_gate_required = plan_requires_hard_planning(plan)
    return {
        "mode": mode,
        "passed": not failures,
        "would_block": hard_gate_required and bool(failures),
        "planning_requirement": "hard" if hard_gate_required else "advisory",
        "plan_revision_id": plan.plan_revision_id if plan else None,
        "failures": failures,
    }
''',
    1,
)
api.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# Final planning acceptance blocks only when the actual run-owned final diff
# contains consequential paths.
# ---------------------------------------------------------------------------
pa = Path("src/app/agent_runtime/planning_acceptance.py")
text = pa.read_text(encoding="utf-8")
text = text.replace(
    '    planning_mode,\n)',
    '    planning_mode,\n    planning_requirement_for_operation,\n)',
    1,
)
text = text.replace(
    '    failures: tuple[str, ...] = ()\n',
    '    failures: tuple[str, ...] = ()\n    hard_gate_required: bool = False\n',
    1,
)
text = text.replace(
    '        return self.mode == "enforce" and self.would_block\n',
    '        return self.mode == "enforce" and self.hard_gate_required and self.would_block\n',
    1,
)
text = text.replace(
    '        return self.mode == "enforce" and any(\n',
    '        return self.mode == "enforce" and self.hard_gate_required and any(\n',
    1,
)
text = text.replace(
    '''    revision: TaskRevision | None,
) -> PlanningAcceptanceAssessment:
''',
    '''    revision: TaskRevision | None,
    *,
    modified_paths: list[str] | tuple[str, ...] = (),
) -> PlanningAcceptanceAssessment:
''',
    1,
)
needle = '''    if revision is None:
        return PlanningAcceptanceAssessment(
            mode=mode,
            plan_revision_id=None,
            failures=("planning_task_revision_unavailable",),
        )

    planning = PostgresPlanningRepository(connection, context)
'''
replacement = '''    hard_gate_required = any(
        planning_requirement_for_operation("mutate", target_path=path) == "hard"
        for path in modified_paths
    )
    if not hard_gate_required:
        return PlanningAcceptanceAssessment(
            mode=mode,
            plan_revision_id=None,
            hard_gate_required=False,
        )
    if revision is None:
        return PlanningAcceptanceAssessment(
            mode=mode,
            plan_revision_id=None,
            failures=("planning_task_revision_unavailable",),
            hard_gate_required=True,
        )

    planning = PostgresPlanningRepository(connection, context)
'''
if needle not in text:
    raise SystemExit("planning_acceptance.py: hard gate insertion anchor missing")
text = text.replace(needle, replacement, 1)
text = text.replace(
    '''        failures=tuple(dict.fromkeys(failures)),
    )
''',
    '''        failures=tuple(dict.fromkeys(failures)),
        hard_gate_required=True,
    )
''',
    1,
)
pa.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# Pi gets trusted native skills and owns its normal inspect/replan/self-review
# loop. Omnix hard planning is reactive only for consequential operations.
# ---------------------------------------------------------------------------
pi = Path("src/app/agent_runtime/pi_runtime.py")
text = pi.read_text(encoding="utf-8")
text = text.replace(
    '''Pi's arbitrary skills, templates and context-file loading remain disabled by the
core launcher. Omnix adds only allowlisted methodology and explicitly compiled
repository guidance here, preserving capability and completion authority.
''',
    '''Pi resource discovery remains disabled, but Omnix explicitly loads trusted
repository-owned Pi skills while continuing to sanitize repository guidance and
preserve capability/completion authority.
''',
    1,
)
text = text.replace(
    'from .coding_skills import compile_coding_skills\n',
    'from .coding_skills import compile_coding_skills, trusted_skill_paths\n',
    1,
)
start = text.index('_ENGINEERING_WORKFLOW = """')
end = text.index('"""\n\n\n# Keep the internal durable planning tool', start) + 3
new_workflow = '''_ENGINEERING_WORKFLOW = """PI-OWNED ENGINEERING LOOP FOR MUTATING CODING TASKS
Use your normal coding-agent loop: inspect architecture/callers/tests, form a working plan, implement, test, diagnose, discover additional callers, replan, and repair as needed. The working plan is informative rather than permission for ordinary in-scope source/test edits.
Do not stop for a PlanDelta merely because new evidence changes which ordinary in-scope files are relevant. Omnix capability, workspace, approval, budget, and external-system policies remain independently authoritative.
If Omnix explicitly blocks a consequential operation because hard planning authority is required (for example dependency/schema/migration/generated-contract or broad destructive work), use `omnix_plan` to record the narrow operation/paths and retry only after authorization.
Before settling, inspect the complete final diff, reread the authoritative objective, search affected callers where relevant, run required validation after the final mutation, and critically self-review the candidate. Fix issues you find inside this same Pi loop.
For governed UI validation, use `omnix_capability` with `browser.open` and `{\"workspace_preview\": true, \"path\": \"/<route>\"}`; do not launch a separate Vite/dev server through the shell.
Pi settling is only a completion request. Omnix freezes the final WorkspaceState, verifies fresh evidence, may launch an independent read-only reviewer, and alone decides acceptance.
"""'''
text = text[:start] + new_workflow + text[end:]
# Load explicit trusted skills while keeping arbitrary discovery disabled.
anchor = '''    argv = list(_CORE_PI_RPC_ARGV(spec, pi_path=pi_path))
    planning_enabled = (
'''
replacement = '''    argv = list(_CORE_PI_RPC_ARGV(spec, pi_path=pi_path))
    for skill_path in trusted_skill_paths(profile=spec.profile):
        argv.extend(["--skill", str(skill_path)])
    planning_enabled = (
'''
if anchor not in text:
    raise SystemExit("pi_runtime.py: argv anchor missing")
text = text.replace(anchor, replacement, 1)
text = text.replace(
    '        skills, skills_digest = compile_coding_skills(profile=spec.profile)\n',
    '        _skills, skills_digest = compile_coding_skills(profile=spec.profile)\n',
    1,
)
text = text.replace(
    '            "Omnix allowlisted coding methodology skills:\\n" + (skills or "none"),\n',
    '            "Trusted native Pi skill digest: " + skills_digest,\n',
    1,
)
pi.write_text(text, encoding="utf-8")

# Native plan tool copy: advisory by default, hard authority only on explicit block.
broker = Path("src/app/agent_runtime/pi_broker_extension.ts")
text = broker.read_text(encoding="utf-8")
old = '''    description: "Inspect, submit, amend, or check the server-authoritative implementation plan for this coding run.",
    promptSnippet: "Use Omnix durable planning before mutating coding workspaces",
    promptGuidelines: [
      "For mutating coding tasks, inspect the repository first, then call omnix_plan with action=inspect before the first edit or mutating command.",
      "Use the returned TaskRevision requirements, planning lenses, inspection evidence, and impact candidates to build the implementation plan.",
      "Submit the plan with action=submit. Every required requirement needs plan or verification coverage and validation; classify every high-impact candidate.",
      "If new repository evidence, a failed validation, reviewer finding, repair request, or user steering changes the intended implementation, use action=inspect with focused queries/paths and then action=amend before further mutation.",
      "A NOT_IMPACTED disposition for high-risk evidence cannot be justified by prose alone; provide evidence-backed waiver proof and expect Omnix to fail closed when semantic adjudication is still required.",
      "Use action=check before requesting completion to compare the approved plan with the current workspace.",
      "Omnix plan approval does not grant capabilities or user approvals. Existing workspace, command, external capability, and approval policies remain independently authoritative.",
    ],
'''
new = '''    description: "Persist or inspect the coding agent's working plan. Ordinary in-scope edits are advisory; Omnix requires hard plan authority only for consequential mutations.",
    promptSnippet: "Working plans are informative; use hard planning when Omnix explicitly requires it",
    promptGuidelines: [
      "Use your normal Pi planning/replanning loop for ordinary coding. A working plan is useful for audit/recovery/review context but is not permission for normal in-scope source/test edits.",
      "Do not stop to amend the plan merely because you discover another ordinary in-scope caller or test while implementing.",
      "Use action=inspect only when an explicit deterministic repository search would help your own reasoning or provide audit evidence; Omnix does not infer semantic task lenses for you.",
      "If Omnix blocks a consequential mutation because hard planning authority is required, submit or amend a narrow plan covering that exact path/command, then retry it.",
      "Use action=check for diagnostics when useful; advisory conformance is not completion authority.",
      "Plan approval never grants capabilities, external authority, or user approval. Workspace, capability, approval, budget, and final acceptance policies remain independent.",
    ],
'''
if old not in text:
    raise SystemExit("pi_broker_extension.ts: plan guidelines anchor missing")
text = text.replace(old, new, 1)
broker.write_text(text, encoding="utf-8")

guard = Path("src/app/agent_runtime/pi_guard_extension.ts")
text = guard.read_text(encoding="utf-8")
text = text.replace(
    '    return `Omnix planning authority blocked this operation: ${reasons}. Inspect repository evidence and submit/amend the durable plan with omnix_plan before retrying.`;\n',
    '    return `Omnix hard planning authority blocked this consequential operation: ${reasons}. Record the narrow required path/command with omnix_plan before retrying; ordinary in-scope edits do not require PlanDelta round trips.`;\n',
    1,
)
text = text.replace(
    '''      // Capability/scope authority remains independent of planning. Only after
      // the command is known to be within an issued local capability do we ask
      // the server whether its workspace effect is backed by the active plan.
''',
    '''      // Capability/scope authority remains independent of planning. The
      // server classifies ordinary operations as free/advisory and reserves
      // hard plan authority for consequential mutations.
''',
    1,
)
guard.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# Self-review returns to Pi's normal loop for new runs. Legacy persisted
# self_review stages remain parsable/recoverable.
# ---------------------------------------------------------------------------
cq = Path("src/app/agent_runtime/coding_quality.py")
text = cq.read_text(encoding="utf-8")
old = '''    self_review_ok = any(
        isinstance(item, SelfReviewResult)
        and item.workspace_state_id == workspace_state.state_id
        and item.task_revision_id == revision_id
        and revision is not None
        and self_review_is_acceptable(item, revision)
        for item in self_reviews
    )
    if not self_review_ok:
        failures.append("quality_self_review_stale_or_missing")

'''
if old not in text:
    raise SystemExit("coding_quality.py: self review acceptance block missing")
text = text.replace(old, '    # Pi performs ordinary self-review inside its coding loop. Persisted legacy\n    # SelfReviewResult rows remain readable but are no longer a separate server\n    # completion prerequisite.\n    del self_reviews\n\n', 1)
start = text.index('def repair_prompt(')
end = text.index('\ndef self_review_prompt', start)
old_block = text[start:end]
# Preserve function signature, replace return body only by building a concise
# implementation here.
sig_end = old_block.index('    findings =')
signature = old_block[:sig_end]
new_body = '''    findings = [] if review is None else [item.model_dump(mode="json") for item in review.findings]
    missing_tests = [] if review is None else list(review.missing_tests)
    missing = [item.model_dump(mode="json") for item in missing_validation]
    return (
        f"Omnix coding quality attempt {attempt} has substantive findings to address. Re-read the authoritative "
        f"task and continue the normal Pi inspect/reason/edit/test loop. Objective: {revision.effective_objective}\\n"
        f"Independent review findings JSON: {json.dumps(findings, ensure_ascii=False)}\\n"
        f"Reviewer missing tests JSON: {json.dumps(missing_tests, ensure_ascii=False)}\\n"
        f"Missing/stale final-state validation JSON: {json.dumps(missing, ensure_ascii=False)}\\n"
        "Treat these as evidence, not as an Omnix-authored implementation sequence. Inspect the relevant source and "
        "callers, repair the actual cause, revise your working plan freely, inspect the final diff, and rerun required "
        "validation after the last mutation. Ordinary in-scope repair edits do not require a PlanDelta. If Omnix "
        "explicitly blocks a consequential operation because hard planning authority is required, then use omnix_plan "
        "to record/amend that narrow operation before retrying it. Do not ask the user to restate the already-"
        "authoritative objective."
    )

'''
text = text[:start] + signature + new_body + text[end+1:]
cq.write_text(text, encoding="utf-8")

service = Path("src/app/agent_runtime/service.py")
text = service.read_text(encoding="utf-8")
text = text.replace(
    '''The Phase 1-19 durable orchestration remains in service_core. This layer adds the
coding quality state machine: TaskRevision engineering contracts, exact workspace
identity, mandatory self-review, fresh validation, immutable independent review,
and one repair/revalidate/re-review convergence loop. Pi can request completion;
Omnix remains the only completion authority.
''',
    '''The Phase 1-19 durable orchestration remains in service_core. This layer keeps
TaskRevision contracts, exact workspace identity, fresh validation, immutable
independent review and bounded repair convergence. Pi owns ordinary planning and
self-review inside its coding loop; Omnix remains the only completion authority.
''',
    1,
)
text = text.replace(
    '    return "self_review", []\n',
    '    return "ready", []\n',
    1,
)
# New runs start directly in Pi's coding loop rather than server cognitive phases.
text = text.replace('                    stage="inspect",\n', '                    stage="implementing",\n', 2)
text = text.replace('                            "stage": "inspect",\n', '                            "stage": "implementing",\n', 2)
# Candidate-ready path no longer opens a new self-review RPC turn.
old = '''            self._set_quality_stage(
                repository,
                run_id=current.run_id,
                stage="self_review",
                attempt=attempt,
                task_revision_id=revision.revision_id,
                workspace_state_id=state.state_id,
                reason="validated_implementation_candidate_ready",
            )
            prompt = self_review_prompt(
                revision,
                attempt=attempt,
                validations=current_validations,
            )
            return self._queue_quality_resume(
                repository,
                run_id=current.run_id,
                prompt=prompt,
                idempotency_key=(
                    f"quality-self-review:{current.run_id}:{revision.revision_id}:"
                    f"{state.state_id}:{attempt}"
                ),
                quality_stage="self_review",
                quality_attempt=attempt,
                task_revision_id=revision.revision_id,
                workspace_state_id=state.state_id,
            )
'''
new = '''            self._set_quality_stage(
                repository,
                run_id=current.run_id,
                stage="validating",
                attempt=attempt,
                task_revision_id=revision.revision_id,
                workspace_state_id=state.state_id,
                reason="pi_candidate_ready_for_verification",
            )
            # Pi already performed ordinary self-review inside the same coding
            # turn. Continue directly to exact-state verification/reviewer
            # orchestration without a second implementer RPC turn.
            stage = "validating"
'''
if old not in text:
    raise SystemExit("service.py: candidate self-review transition missing")
text = text.replace(old, new, 1)
# Remove the current-state mandatory self-review refresh. Legacy stage==self_review
# block above remains intact for durable runs created by older versions.
pattern = r'''        self_reviews = quality\.list_self_review_results\(\n            current\.run_id,\n            task_revision_id=revision\.revision_id,\n        \)\n        self_review_fresh = any\(.*?\n            \)\n\n        missing = missing_final_validations'''
replacement = '''        missing = missing_final_validations'''
text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
if count != 1:
    raise SystemExit("service.py: mandatory self-review freshness block replacement failed")
# Workspace refresh goes validation -> independent review, not another self-review turn.
text = text.replace(
    '            "Validate the current state against the authoritative task. If validation proves a real "\n            "implementation change is needed, inspect the new evidence and amend the active plan before "\n            "any mutation. Otherwise finish the requested validation so Omnix can self-review and "\n            "independently review this exact current state."\n',
    '            "Validate the current state against the authoritative task. If validation proves a real "\n            "implementation change is needed, continue the normal Pi repair loop; ordinary in-scope edits "\n            "do not require a PlanDelta. Otherwise finish the requested validation so Omnix can independently "\n            "review this exact current state."\n',
    1,
)
# Final planning acceptance is evaluated only against actual run-owned modified paths.
text = text.replace(
    '''        planning_assessment = evaluate_planning_acceptance(
            repository.connection,
            self.context,
            current,
            revision,
        )
''',
    '''        planning_assessment = evaluate_planning_acceptance(
            repository.connection,
            self.context,
            current,
            revision,
            modified_paths=list(result.modified_paths),
        )
''',
    1,
)
# Surface whether planning was truly a hard acceptance gate.
text = text.replace(
    '                    "fail_closed": planning_assessment.fail_closed,\n                    "failures": list(planning_assessment.failures),\n',
    '                    "fail_closed": planning_assessment.fail_closed,\n                    "hard_gate_required": planning_assessment.hard_gate_required,\n                    "failures": list(planning_assessment.failures),\n',
    2,
)
service.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# Regressions for the new boundary.
# ---------------------------------------------------------------------------
Path("src/tests/agent_runtime/test_deorchestrated_pi_boundary.py").write_text(
    '''from __future__ import annotations\n\nfrom pathlib import Path\n\nfrom app.agent_runtime.contracts import AgentRunSpec, ModelRef, TaskRevision, WorkspaceSpec\nfrom app.agent_runtime.pi_runtime import pi_rpc_argv\nfrom app.agent_runtime.planning import (\n    build_inspection_bundle,\n    operation_plan_failures,\n    planning_requirement_for_operation,\n)\nfrom app.agent_runtime.planning_acceptance import PlanningAcceptanceAssessment\n\n\ndef _revision() -> TaskRevision:\n    return TaskRevision(\n        revision_id="revision-1",\n        run_id="run-1",\n        sequence=1,\n        user_instruction="Fix the dropdown",\n        effective_objective="Fix the dropdown",\n    )\n\n\ndef test_normal_in_scope_edits_are_advisory_not_plan_authority() -> None:\n    revision = _revision()\n    assert planning_requirement_for_operation("mutate", target_path="src/app/service.py") == "advisory"\n    assert planning_requirement_for_operation("mutate", target_path="tests/test_service.py") == "advisory"\n    assert operation_plan_failures(None, revision, effect="mutate", target_path="src/app/service.py") == []\n\n\ndef test_consequential_mutations_remain_hard_gated() -> None:\n    revision = _revision()\n    for path in (\n        "src/app/persistence/migrations/0066_change.sql",\n        "package-lock.json",\n        "src/apps/web/src/api/generated/types.ts",\n    ):\n        assert planning_requirement_for_operation("mutate", target_path=path) == "hard"\n        assert operation_plan_failures(None, revision, effect="mutate", target_path=path) == ["approved_plan_missing"]\n    assert planning_requirement_for_operation("mutate", command="npm --prefix src/apps/web install react") == "hard"\n    assert planning_requirement_for_operation("unknown", command="custom-generator --output src/generated.py") == "hard"\n\n\ndef test_advisory_planning_failures_cannot_block_acceptance() -> None:\n    assessment = PlanningAcceptanceAssessment(\n        mode="enforce",\n        plan_revision_id="plan-1",\n        failures=("plan_inspection_evidence_stale",),\n        hard_gate_required=False,\n    )\n    assert assessment.would_block\n    assert not assessment.blocks_acceptance\n    assert not assessment.fail_closed\n\n\ndef test_explicit_trusted_pi_skill_is_loaded_while_discovery_stays_disabled(tmp_path: Path) -> None:\n    spec = AgentRunSpec(\n        run_id="run-skill",\n        task="Fix code",\n        profile="coding",\n        model=ModelRef(provider_id="test", model_id="model"),\n        workspace=WorkspaceSpec(root=str(tmp_path)),\n        capabilities=["workspace.read", "workspace.edit"],\n        expected_artifacts=["diff"],\n    )\n    argv = pi_rpc_argv(spec)\n    assert "--no-skills" in argv\n    assert "--no-prompt-templates" in argv\n    assert "--no-context-files" in argv\n    assert "--skill" in argv\n    skill = Path(argv[argv.index("--skill") + 1])\n    assert skill.name == "SKILL.md"\n    assert skill.parent.name == "engineering"\n    assert skill.exists()\n\n\ndef test_omnix_no_longer_infers_semantic_inspection_from_user_language(tmp_path: Path) -> None:\n    # No workspace is enough to prove Omnix no longer invents task lenses or\n    # quoted-literal searches merely from the objective.\n    spec = AgentRunSpec(\n        run_id="run-inspect",\n        task='Rename "Old" to "New" in the UI',\n        objective='Rename "Old" to "New" in the UI',\n        profile="coding",\n        model=ModelRef(provider_id="test", model_id="model"),\n    )\n    revision = TaskRevision(\n        revision_id="revision-inspect",\n        run_id=spec.run_id,\n        sequence=1,\n        user_instruction=spec.task,\n        effective_objective=spec.objective,\n    )\n    evidence, candidates, lenses = build_inspection_bundle(spec, revision)\n    assert evidence == []\n    assert candidates == []\n    assert lenses == []\n''',
    encoding="utf-8",
)

# Update old tests whose assertions represented the old execution-plan authority.
path = Path("src/tests/agent_runtime/test_planning_authority_semantics.py")
text = path.read_text(encoding="utf-8")
text = text.replace(
    '    assert operation_plan_failures(None, revision, effect="mutate") == ["approved_plan_missing"]\n',
    '    assert operation_plan_failures(None, revision, effect="mutate", target_path="src/example.py") == []\n    assert operation_plan_failures(None, revision, effect="mutate", target_path="package-lock.json") == ["approved_plan_missing"]\n',
    1,
)
path.write_text(text, encoding="utf-8")

path = Path("src/tests/agent_runtime/test_planning_acceptance.py")
text = path.read_text(encoding="utf-8")
text = text.replace(
    'def test_enforce_conformance_failure_blocks_but_can_remain_repairable() -> None:\n',
    'def test_enforce_hard_conformance_failure_blocks_but_can_remain_repairable() -> None:\n',
    1,
)
text = text.replace(
    '        failures=("planned_impact_not_modified:candidate-1:src/caller.py",),\n    )\n\n    assert assessment.would_block\n    assert assessment.blocks_acceptance\n',
    '        failures=("planned_impact_not_modified:candidate-1:src/caller.py",),\n        hard_gate_required=True,\n    )\n\n    assert assessment.would_block\n    assert assessment.blocks_acceptance\n',
    1,
)
text = text.replace(
    '            failures=(failure,),\n        )\n',
    '            failures=(failure,),\n            hard_gate_required=True,\n        )\n',
    1,
)
path.write_text(text, encoding="utf-8")

path = Path("src/tests/agent_runtime/test_plan_gate_closure.py")
text = path.read_text(encoding="utf-8")
text = re.sub(
    r'def test_high_risk_verify_cannot_bypass_semantic_adjudication\(\) -> None:\n.*?\n\ndef test_plan_gate_rejects_authoritative_validation_shadowing',
    '''def test_semantic_waiver_is_not_server_authored_execution_authority() -> None:
    spec, revision, evidence, candidate = _fixture()
    submission = _submission().model_copy(
        update={
            "impacts": [
                PlanImpactDisposition(
                    candidate_id="C1",
                    disposition="verify",
                    evidence_ids=["E1"],
                    invariant="Reviewer/Pi may reason about this invariant.",
                )
            ]
        }
    )
    failures = plan_gate_failures(spec, revision, submission, [candidate], [evidence])
    assert not [item for item in failures if "critic" in item or "waiver" in item]


def test_plan_gate_rejects_authoritative_validation_shadowing''',
    text,
    count=1,
    flags=re.S,
)
path.write_text(text, encoding="utf-8")

path = Path("src/tests/agent_runtime/test_evidence_backed_planning.py")
text = path.read_text(encoding="utf-8")
text = text.replace('    evidence, candidates, lenses = build_inspection_bundle(spec, revision)\n', '    evidence, candidates, lenses = build_inspection_bundle(spec, revision, queries=["Character settings"])\n', 1)
text = text.replace('    assert {"ui_behavior", "refactor", "regression"} <= set(lenses)\n', '    assert lenses == []\n', 1)
# Remaining fixture calls need explicit query now.
text = text.replace('    evidence, candidates, _ = build_inspection_bundle(spec, revision)\n', '    evidence, candidates, _ = build_inspection_bundle(spec, revision, queries=["Character settings"])\n')
# Unclassified candidates are advisory rather than a server semantic gate.
text = text.replace(
    '    assert f"impact_candidate_unclassified:{e2e.candidate_id}" in failures\n',
    '    assert f"impact_candidate_unclassified:{e2e.candidate_id}" not in failures\n',
    1,
)
text = text.replace(
    '    assert f"semantic_waiver_requires_critic:{target.candidate_id}" in failures\n',
    '    assert f"semantic_waiver_requires_critic:{target.candidate_id}" not in failures\n',
    1,
)
old = '''    failures = operation_plan_failures(
        plan,
        revision,
        effect="mutate",
        target_path="src/apps/web/Unplanned.tsx",
        current_evidence_digest=inspection_evidence_digest(evidence),
    )
    assert "mutation_not_in_plan:src/apps/web/Unplanned.tsx" in failures
    stale = operation_plan_failures(
        plan,
        revision,
        effect="mutate",
        target_path="src/apps/web/ChatIdentityModeControl.tsx",
        current_evidence_digest="new-evidence",
    )
    assert "plan_inspection_evidence_stale" in stale
'''
new = '''    failures = operation_plan_failures(
        plan,
        revision,
        effect="mutate",
        target_path="src/apps/web/Unplanned.tsx",
        current_evidence_digest=inspection_evidence_digest(evidence),
    )
    assert failures == []
    stale = operation_plan_failures(
        plan,
        revision,
        effect="mutate",
        target_path="src/apps/web/ChatIdentityModeControl.tsx",
        current_evidence_digest="new-evidence",
    )
    assert stale == []
    assert operation_plan_failures(
        None,
        revision,
        effect="mutate",
        target_path="package-lock.json",
    ) == ["approved_plan_missing"]
'''
if old not in text:
    raise SystemExit("test_evidence_backed_planning.py: operation authorization anchor missing")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")

print("agent de-orchestration patch applied")
