from pathlib import Path

path = Path("scripts/patch_quality_budget_convergence.py")
text = path.read_text(encoding="utf-8")
text = text.replace(
    '"        resolved = _quality_sized_run_spec(resolve_run_model_fidelity(spec))\\n        return super().start_with_context(\\n            resolved,"',
    '"        resolved = resolve_run_model_fidelity(_quality_sized_run_spec(spec))\\n        return super().start_with_context(\\n            resolved,"',
)
text = text.replace(
    'provider_test.write_text(provider_text.rstrip() + provider_case + "\\n", encoding="utf-8")',
    'provider_test.write_text(provider_text.rstrip() + provider_case.rstrip() + "\\n", encoding="utf-8")',
)
path.write_text(text, encoding="utf-8")
print("one-shot quality patch helper corrected")
