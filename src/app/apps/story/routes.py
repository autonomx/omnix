"""Story project routes (ST-1.2): the story feature registers them, so they need story:read or story:write."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import APIRouter, HTTPException, Query, Response

from app.persistence.database import default_database
from app.runtime.tenant_context import current_tenant

from . import export, service, voices
from .contracts import (
    StoryCharactersReplace,
    StoryDeleted,
    StoryImportRequest,
    StoryImportResult,
    StoryNotesReplace,
    StoryOutlineReplace,
    StoryPageCreate,
    StoryPageUpdate,
    StoryProject,
    StoryProjectCreate,
    StoryProjectList,
    StoryProjectUpdate,
    StorySpeechPlan,
    StorySpeechPlanRequest,
    StorySpeechSentence,
    StoryVersion,
    StoryVersionCreate,
    StoryVoiceCast,
    StoryVoiceChoice,
)

router = APIRouter()
_T = TypeVar("_T")


def _call(operation: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
    try:
        return operation(default_database(), current_tenant(), *args, **kwargs)
    except service.StoryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.StoryConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except voices.VoiceNotCastable as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/story/projects", response_model=StoryProjectList)
def list_story_projects(trashed: bool = Query(False)) -> StoryProjectList:
    """The account's stories, newest first; with trashed, the ones in the trash."""
    return StoryProjectList(projects=_call(service.list_projects, trashed=trashed))


@router.post("/api/story/projects", response_model=StoryProject, status_code=201)
def create_story_project(request: StoryProjectCreate) -> StoryProject:
    return _call(service.create_project, request)


@router.post("/api/story/projects/import", response_model=StoryImportResult)
def import_story_projects(request: StoryImportRequest) -> StoryImportResult:
    """Make projects of the stories the browser still holds (ST-1.4); importing again makes nothing new."""
    return _call(service.import_items, request.items)


@router.get("/api/story/projects/{project_id}", response_model=StoryProject)
def get_story_project(project_id: str) -> StoryProject:
    return _call(service.get_project, project_id)


@router.patch("/api/story/projects/{project_id}", response_model=StoryProject)
def update_story_project(project_id: str, request: StoryProjectUpdate) -> StoryProject:
    return _call(service.update_project, project_id, **request.model_dump(exclude_unset=True))


@router.post("/api/story/projects/{project_id}/trash", response_model=StoryProject)
def trash_story_project(project_id: str) -> StoryProject:
    return _call(service.set_trashed, project_id, True)


@router.post("/api/story/projects/{project_id}/restore", response_model=StoryProject)
def restore_story_project(project_id: str) -> StoryProject:
    return _call(service.set_trashed, project_id, False)


@router.delete("/api/story/projects/{project_id}", response_model=StoryDeleted)
def purge_story_project(project_id: str) -> StoryDeleted:
    """Delete a story in the trash for good."""
    _call(service.purge_project, project_id)
    return StoryDeleted(id=project_id)


@router.post("/api/story/projects/{project_id}/pages", response_model=StoryProject, status_code=201)
def append_story_page(project_id: str, request: StoryPageCreate) -> StoryProject:
    return _call(service.append_page, project_id, blocks=[block.model_dump() for block in request.blocks],
                 title=request.title, chapter=request.chapter)


@router.patch("/api/story/projects/{project_id}/pages/{page_id}", response_model=StoryProject)
def update_story_page(project_id: str, page_id: str, request: StoryPageUpdate) -> StoryProject:
    values = request.model_dump(exclude_unset=True)
    if request.blocks is not None:
        values["blocks"] = [block.model_dump() for block in request.blocks]
    if request.base_blocks is not None:
        values["base_blocks"] = [block.model_dump() for block in request.base_blocks]
    return _call(service.update_page, project_id, page_id, **values)


@router.post("/api/story/projects/{project_id}/undo", response_model=StoryProject)
def undo_story_move(project_id: str) -> StoryProject:
    """Take back the player's last move; its page stays as a branch."""
    return _call(service.undo_move, project_id)


@router.post("/api/story/projects/{project_id}/pages/{page_id}/open", response_model=StoryProject)
def open_story_page(project_id: str, page_id: str) -> StoryProject:
    """Make the run that ends at this page the story (go back to a move, or open a branch)."""
    return _call(service.open_page, project_id, page_id)


@router.get("/api/story/projects/{project_id}/export/{export_format}", response_class=Response)
def export_story(project_id: str, export_format: export.ExportFormat) -> Response:
    """The story as a book file (ST-6.5): EPUB, DOCX or PDF of its visible pages, as an attachment."""
    project = _call(service.get_project, project_id)
    book = export.book_of(project)
    return Response(
        content=export.render(book, export_format),
        media_type=export.MEDIA_TYPES[export_format],
        headers={"Content-Disposition": f'attachment; filename="{export.file_name(book, export_format)}"'},
    )


@router.post("/api/story/projects/{project_id}/versions", response_model=StoryProject, status_code=201)
def save_story_version(project_id: str, request: StoryVersionCreate) -> StoryProject:
    return _call(service.save_version, project_id, title=request.title, kind=request.kind)


@router.get("/api/story/projects/{project_id}/versions/{version_id}", response_model=StoryVersion)
def get_story_version(project_id: str, version_id: str) -> StoryVersion:
    return _call(service.get_version, project_id, version_id)


@router.post("/api/story/projects/{project_id}/versions/{version_id}/restore", response_model=StoryProject)
def restore_story_version(project_id: str, version_id: str) -> StoryProject:
    """Make a version the manuscript; the one it replaces is kept as a version."""
    return _call(service.restore_version, project_id, version_id)


@router.post("/api/story/projects/{project_id}/versions/{version_id}/accept", response_model=StoryProject)
def accept_story_selection(project_id: str, version_id: str) -> StoryProject:
    """Make the change a selection version proposes (ST-6.2); 409 when the page changed since."""
    return _call(service.accept_selection, project_id, version_id)


@router.post("/api/story/projects/{project_id}/versions/{version_id}/reject", response_model=StoryProject)
def reject_story_selection(project_id: str, version_id: str) -> StoryProject:
    return _call(service.reject_selection, project_id, version_id)


@router.put("/api/story/projects/{project_id}/characters", response_model=StoryProject)
def replace_story_characters(project_id: str, request: StoryCharactersReplace) -> StoryProject:
    return _call(service.replace_characters, project_id, [character.model_dump() for character in request.characters])


@router.put("/api/story/projects/{project_id}/notes", response_model=StoryProject)
def replace_story_notes(project_id: str, request: StoryNotesReplace) -> StoryProject:
    return _call(service.replace_notes, project_id, request.notes)


@router.put("/api/story/projects/{project_id}/outline", response_model=StoryProject)
def replace_story_outline(project_id: str, request: StoryOutlineReplace) -> StoryProject:
    """The writer's plan, chapter by chapter; a beat already drafted keeps its page."""
    return _call(service.replace_outline, project_id, request.chapters)


# -- voices (ST-4.2) ------------------------------------------------------------------------------


@router.get("/api/story/projects/{project_id}/voices", response_model=StoryVoiceCast)
def get_story_voices(project_id: str) -> StoryVoiceCast:
    """Who speaks in the story and in which voice; anyone not cast yet is cast now."""
    return _call(voices.voice_cast, project_id)


@router.put("/api/story/projects/{project_id}/voices/{speaker_id}", response_model=StoryVoiceCast)
def choose_story_voice(project_id: str, speaker_id: str, request: StoryVoiceChoice) -> StoryVoiceCast:
    """The writer's choice of any library voice for the narrator or a character."""
    return _call(voices.choose_voice, project_id, speaker_id, request.voice_id)


@router.post("/api/story/projects/{project_id}/speech-plan", response_model=StorySpeechPlan)
def plan_story_speech(project_id: str, request: StorySpeechPlanRequest) -> StorySpeechPlan:
    """How a page is spoken: block by block in its speakers' voices, sentence by sentence."""
    return _call(voices.speech_plan, project_id, request.page_id)


@router.post("/api/story/projects/{project_id}/speech-audio", response_class=Response)
def speak_story_sentence(project_id: str, request: StorySpeechSentence) -> Response:
    """A sentence of a page in its speaker's voice, as PCM16 (``application/x-omnix-pcm16`` at
    ``X-Omnix-Sample-Rate``): from the project's audio, else streamed as it is synthesized. 503 when the speech
    service is down."""
    return _call(voices.speak, project_id, page_id=request.page_id, speaker_id=request.speaker_id, text=request.text)
