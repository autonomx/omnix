from app.assistant_tools.models import AssistantToolRequest, AssistantToolResult
from app.assistant_tools.step_flow import (
    AssistantToolStep,
    approve_assistant_tool_step,
    create_assistant_tool_flow,
    record_assistant_tool_step_result,
    summarize_assistant_tool_flow,
)


def test_create_flow_waits_for_approval_on_first_sensitive_step():
    flow = create_assistant_tool_flow(
        flow_id="flow-1",
        user_request="Draft and schedule follow up",
        steps=[
            AssistantToolStep(
                id="step-1",
                label="Create draft",
                requires_approval=True,
                request=AssistantToolRequest(tool_id="gmail", action_id="gmail.create_draft"),
            ),
            AssistantToolStep(
                id="step-2",
                label="Create event",
                request=AssistantToolRequest(tool_id="calendar", action_id="calendar.create_event"),
            ),
        ],
    )

    assert flow.status == "waiting_for_approval"
    assert flow.current_step_id == "step-1"


def test_flow_approval_marks_request_as_approved():
    flow = create_assistant_tool_flow(
        flow_id="flow-1",
        user_request="Draft follow up",
        steps=[AssistantToolStep(id="step-1", requires_approval=True, request=AssistantToolRequest(tool_id="gmail", action_id="gmail.create_draft"))],
    )

    approved = approve_assistant_tool_step(flow, "step-1")

    assert approved.status == "ready"
    assert approved.steps[0].status == "approved"
    assert approved.steps[0].request.approved is True


def test_flow_result_advances_to_next_step_and_summarizes():
    flow = create_assistant_tool_flow(
        flow_id="flow-1",
        user_request="Lookup and draft",
        steps=[
            AssistantToolStep(id="step-1", request=AssistantToolRequest(tool_id="contacts", action_id="contacts.search_contacts")),
            AssistantToolStep(id="step-2", request=AssistantToolRequest(tool_id="gmail", action_id="gmail.create_draft")),
        ],
    )

    updated = record_assistant_tool_step_result(
        flow,
        "step-1",
        AssistantToolResult(tool_id="contacts", action_id="contacts.search_contacts", result_summary="Found 1 contact."),
    )

    assert updated.current_step_id == "step-2"
    assert updated.steps[0].status == "complete"
    assert summarize_assistant_tool_flow(updated) == "1/2 assistant tool steps complete; status=ready."
