# Omnix Assistant Workspace Phase 7

Phase 7 adds context budgeting.

## Scope

- ContextBudget contract.
- BudgetedContextAssembly contract.
- ContextBudgetManager contract.
- Pure allocation helper.

## Acceptance Criteria

- Context sources compete for a bounded token budget.
- Included and omitted sources are explicit.
- Response tokens are reserved before prompt construction.
- The layer is independent of provider-specific request formatting.
