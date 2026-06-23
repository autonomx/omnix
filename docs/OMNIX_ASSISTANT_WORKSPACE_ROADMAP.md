# Omnix Assistant Workspace Roadmap

## Phase 0 Product Foundation

Omnix is an event-driven assistant workspace platform.

The system's source of truth is not the UI, individual chat messages, voice transcripts, memories, knowledge files, or tool outputs. The source of truth is the workspace and conversation event stream.

All user-facing experiences — chat, voice, memory, knowledge, tools, assistant identities, and future capabilities — are projections over the same domain model, event architecture, persistence layer, and context assembly pipeline.

New features must integrate into the event and context architecture rather than creating parallel state systems.

## Product Vision

Omnix should evolve from a chatbot screen into a persistent AI operating environment for users, projects, and workspaces. Regular chat and live voice are interaction modes over the same assistant core. Memory, knowledge retrieval, tools, provider selection, and assistant identities are platform capabilities that participate in the same event and context pipeline.

The v1 architecture prioritizes durable foundations before visual polish:

1. Assistant core and event architecture.
2. Persistent intelligence through workspaces, projects, memory, instructions, and knowledge retrieval.
3. Product experience through the modern shell, conversation timeline, and control dock.
4. Voice as another interface into the same conversation engine.
5. Tools, permissions, and execution history.
6. Accessibility, responsive layout, visual polish, and release hardening.

## Feature Hierarchy

```text
Omnix
├─ Workspaces
│  ├─ Projects
│  ├─ Conversations
│  ├─ Knowledge Sources
│  ├─ Memories
│  ├─ Instructions
│  └─ Workspace Settings
│
├─ Assistant Identities
│  ├─ Name and Avatar
│  ├─ Personality
│  ├─ Voice
│  ├─ System Prompt
│  ├─ Memory Policy
│  ├─ Tool Policy
│  └─ Provider Preferences
│
├─ Conversation Engine
│  ├─ Events
│  ├─ Turns
│  ├─ Persistence
│  ├─ Projections
│  └─ Audit Records
│
├─ Context Pipeline
│  ├─ Context Assembly
│  ├─ Context Budgeting
│  ├─ Prompt Builder
│  ├─ Provider Abstraction
│  └─ Response Provenance
│
├─ Knowledge & Retrieval System
│  ├─ Sources
│  ├─ Indexing
│  ├─ Chunks
│  ├─ Retrieval
│  └─ Traceability
│
├─ Voice
│  ├─ Live Sessions
│  ├─ STT
│  ├─ TTS
│  ├─ Transcript Events
│  └─ Interruptions
│
├─ Tools
│  ├─ Registry
│  ├─ Permissions
│  ├─ Execution
│  └─ History
│
└─ UI
   ├─ Shell
   ├─ Conversation Timeline
   ├─ Workspace Views
   ├─ Project Views
   ├─ Memory Views
   ├─ Knowledge Views
   ├─ Context and Audit Views
   └─ Voice Views
```

## Design Principles

- **Event-first:** meaningful changes emit domain events.
- **Projection-rendered UI:** UI components render state derived from events; they do not own canonical assistant state.
- **Workspace-first organization:** conversations, memory, knowledge, instructions, and tools belong to workspaces and optional projects.
- **Shared conversation pipeline:** text and voice use the same conversation engine, context assembly, provider layer, and persistence.
- **Transparent intelligence:** users can inspect memory, knowledge, instructions, token budgeting, provider/model metadata, and response provenance.
- **Provider-agnostic execution:** provider adapters isolate OpenAI, Anthropic, Gemini, Ollama, LM Studio, vLLM, OpenRouter, and future local runtimes.
- **Deterministic budgeting:** memory, knowledge, instructions, and conversation history compete for context through explicit budget policy.
- **User-controlled memory:** explicit memories are editable; assistant-suggested memories require confirmation.
- **Progressive implementation:** ship narrow, testable slices that do not create parallel state systems.

## Interaction Modes

```text
text   — regular typed conversation
voice  — live voice session using STT, transcript events, assistant turns, and TTS
mixed  — a conversation containing both typed messages and voice transcript events
```

Mode is session metadata and should not fork the conversation engine. Voice transcript events should project into the same timeline as user messages, assistant messages, tool calls, knowledge retrieval, and memory events.

## Core Pipeline

```text
User input
→ Conversation event
→ Event persistence
→ Projection builder
→ Context assembly
→ Context budget manager
→ Prompt builder
→ Model provider adapter
→ Assistant response event
→ Projection update
→ UI render
```

## Domain Model Sketch

```ts
type Workspace = {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
};

type Project = {
  id: string;
  workspaceId: string;
  name: string;
  description?: string;
  createdAt: string;
  updatedAt: string;
};

type ChatSession = {
  id: string;
  workspaceId: string;
  projectId?: string;
  title: string;
  mode: "text" | "voice" | "mixed";
  assistantIdentityId?: string;
  provider?: string;
  model?: string;
  createdAt: string;
  updatedAt: string;
};

type ConversationTurn = {
  id: string;
  sessionId: string;
  role: "user" | "assistant" | "tool" | "system";
  content: MessageContent[];
  metadata: {
    provider?: string;
    model?: string;
    assistantIdentityId?: string;
    latencyMs?: number;
    tokenUsage?: TokenUsage;
    voiceSessionId?: string;
  };
  createdAt: string;
};
```

## Event Model Sketch

```ts
type ConversationEvent =
  | UserMessageEvent
  | AssistantMessageEvent
  | ToolCallEvent
  | ToolResultEvent
  | MemoryCreatedEvent
  | MemoryRecalledEvent
  | FileAttachedEvent
  | KnowledgeRetrievedEvent
  | VoiceTranscriptEvent
  | ProviderChangedEvent
  | ModelChangedEvent
  | AssistantIdentityChangedEvent
  | ContextAssembledEvent;
```

## Context Assembly Sketch

```ts
type ContextAssembly = {
  conversation: ConversationProjection;
  workspaceInstructions: Instruction[];
  projectInstructions: Instruction[];
  sessionInstructions: Instruction[];
  memories: Memory[];
  retrievedKnowledge: KnowledgeChunk[];
  assistantIdentity: AssistantIdentity;
  activeTools: ToolDefinition[];
  provider: string;
  model: string;
};
```

## Provider Abstraction Sketch

```ts
interface ModelProvider {
  id: string;
  name: string;

  execute(request: ModelRequest): Promise<ModelResponse>;

  supportsTools(): boolean;
  supportsStreaming(): boolean;
  supportsVision(): boolean;
  supportsReasoning(): boolean;
  supportsJsonMode(): boolean;
}
```

Provider-specific formatting belongs in adapters, not in context assembly, prompt construction, UI components, or conversation state.

## Context Budgeting Sketch

```ts
type ContextBudget = {
  maxTokens: number;
  reserved: {
    system: number;
    conversation: number;
    memory: number;
    knowledge: number;
    tools: number;
    response: number;
  };
};
```

Budgeting priorities should be deterministic:

1. System and assistant identity.
2. Workspace and project instructions.
3. Current user message.
4. Recent conversation turns.
5. Pinned memories.
6. Relevant project and workspace memories.
7. Retrieved knowledge.
8. Older summarized conversation history.
9. Optional tool context.

## Auditability and Provenance Sketch

```ts
type ContextSource = {
  type:
    | "memory"
    | "knowledge"
    | "instruction"
    | "conversation"
    | "tool"
    | "assistant_identity";
  sourceId: string;
  title?: string;
  reasonIncluded: string;
  tokenEstimate?: number;
};
```

Each assistant response should be able to explain which memories, instructions, knowledge chunks, conversation turns, tools, and identity settings influenced the answer.

## MVP Breakdown

### MVP 1 — Assistant Core

- Domain model.
- Conversation engine.
- Event architecture.
- Persistence.
- Projections.
- Context assembly.
- Provider abstraction.
- Context budgeting.
- Prompt builder.
- Basic model execution.
- Audit and provenance foundation.

### MVP 2 — Persistent Intelligence

- Workspaces.
- Projects.
- Assistant identities.
- Scoped memory.
- Memory management.
- Instructions.
- Knowledge & Retrieval System.
- Context visualization.
- Response provenance.

### MVP 3 — Product Experience

- Modern app shell.
- Workspace and project navigation.
- Conversation sidebar.
- Conversation timeline.
- Composer and control dock.
- Context panel.
- Memory and knowledge views.

### MVP 4 — Voice Interface

- Live voice panel.
- Voice state machine.
- Mic capture.
- Audio devices.
- STT.
- Transcript events.
- Voice-to-assistant pipeline.
- TTS.
- Interruptions.
- Voice session persistence.

### MVP 5 — Tools and Advanced Capabilities

- Tool registry.
- Tool permissions.
- Tool execution events.
- Tool result rendering.
- Tool history.
- Workspace and project tool controls.

### MVP 6 — Polish and Release Hardening

- Settings.
- Accessibility.
- Responsive layout.
- Motion.
- Visual polish.
- QA.
- Performance tuning.

## Implementation Phases

| Phase | Name | Goal |
| --- | --- | --- |
| 0 | Product Foundation | Establish the platform vision, glossary, hierarchy, and architectural principles. |
| 1 | Core Domain Model | Add durable workspace, project, and session model contracts. |
| 2 | Conversation Engine | Represent conversations as turns with metadata instead of UI-owned bubbles. |
| 3 | Event Architecture | Make meaningful conversation/workspace changes first-class events. |
| 4 | Persistence and Projections | Rebuild visible state from persisted events and projections. |
| 5 | Context Assembly Layer | Assemble conversation, instructions, memory, knowledge, identity, and tools before prompting. |
| 6 | Provider Abstraction Layer | Isolate provider-specific execution behind model adapters. |
| 7 | Context Budgeting Layer | Allocate token budget deterministically across context sources. |
| 8 | Auditability and Provenance | Track why context was included and what influenced each response. |
| 9 | Assistant Identity System | Support named assistants with prompt, voice, memory policy, and tool policy. |
| 10 | Workspace and Project System | Scope conversations, memory, knowledge, and instructions. |
| 11 | Scoped Memory System | Split explicit user memory from assistant-suggested memory. |
| 12 | Memory Management UI | Make memory inspectable, editable, movable, pinnable, and forgettable. |
| 13 | Knowledge & Retrieval System | Store, index, retrieve, inject, and trace durable knowledge. |
| 14 | Workspace and Project Instructions | Add visible, ordered, scoped instructions. |
| 15 | Context Visualization Panel | Show active identity, model, instructions, memory, knowledge, tools, and budget. |
| 16 | Modern App Shell | Build the workspace/project/conversation shell over platform state. |
| 17 | Modern Conversation Timeline | Render timeline items from events and projections. |
| 18 | Composer and Control Dock | Make provider, model, identity, workspace, project, memory, knowledge, tools, voice, and context visible. |
| 19 | Live Voice Panel UI | Add the right-side voice panel as an interface over session state. |
| 20 | Voice State Machine | Make voice states deterministic and recoverable. |
| 21 | Browser Mic Capture | Add permission flow, audio capture, device selection, and cleanup. |
| 22 | STT Integration | Convert audio chunks into transcript events and user messages. |
| 23 | Voice Assistant Pipeline | Route voice turns through the same context and provider pipeline. |
| 24 | TTS Playback | Speak assistant responses without breaking text chat. |
| 25 | Tool Registry and Tool Events | Register tools, permissions, execution, results, and history as events. |
| 26 | Settings and Preferences | Persist defaults without bypassing event/context architecture. |
| 27 | Responsive Layout and Accessibility | Ensure keyboard, screen reader, reduced-motion, contrast, and responsive support. |
| 28 | Visual Polish and QA | Add premium motion and styling after the architecture is stable. |

## Phase 0 Acceptance Criteria

- The assistant workspace platform principle is documented.
- The feature hierarchy is explicit.
- Text, voice, and mixed modes are defined as modes over the same conversation engine.
- Core entities, event architecture, context assembly, provider abstraction, budgeting, and provenance are captured as implementation constraints.
- The v1 implementation phases and MVP breakdown are recorded so later slices can proceed without inventing parallel state systems.
