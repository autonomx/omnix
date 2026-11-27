/**
 * The story's voices (ST-4.2, ST-4.3): the narrator and each character with the voice they are read in, cast
 * from their description on the server; the writer may choose any castable voice for anyone, and the choice is
 * kept with the project.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { storyApiClient, type StoryProject } from './api/storyClient';

const voicesKey = (project: StoryProject) => ['story', 'voices', project.id, project.characters.map((character) => character.id).join(',')];

export function StoryVoicesPanel({ project }: { project: StoryProject | null }) {
  const queryClient = useQueryClient();
  const castQuery = useQuery({
    enabled: Boolean(project),
    queryKey: project ? voicesKey(project) : ['story', 'voices', 'none'],
    queryFn: () => storyApiClient.voiceCast(project?.id ?? ''),
  });
  const choose = useMutation({
    // The choice carries its own project, so a reply that lands after another story opened updates the right cast.
    mutationFn: ({ target, speakerId, voiceId }: { target: StoryProject; speakerId: string; voiceId: string }) =>
      storyApiClient.chooseVoice(target.id, speakerId, voiceId),
    onSuccess: (cast, { target }) => queryClient.setQueryData(voicesKey(target), cast),
  });
  const cast = castQuery.data;

  return (
    <section className="storyteller-cast-panel" aria-label="Story voices">
      <div className="storyteller-cast-heading">
        <div><p className="eyebrow">Voices</p><h3>Who reads each part</h3></div>
      </div>
      {!project ? <p>Open a story to choose its voices.</p> : null}
      {project && castQuery.isError ? <p role="status">The voices could not be loaded.</p> : null}
      {cast && !cast.voices.length ? <p>No cloned voices yet: add one in Voice to give the cast their own voices.</p> : null}
      {cast?.voices.length ? (
        <div className="storyteller-voice-cast-table">
          {cast.cast.map((row) => (
            <article className="storyteller-voice-row" key={row.speaker_id}>
              <div><strong>{row.name}</strong><span>{row.chosen_by === 'writer' ? 'your choice' : 'matched to the part'}</span></div>
              <select
                aria-label={`${row.name}'s voice`}
                disabled={choose.isPending}
                onChange={(event) => project && choose.mutate({ target: project, speakerId: row.speaker_id, voiceId: event.currentTarget.value })}
                value={row.voice_id}
              >
                {cast.voices.map((voice) => <option key={voice.voice_id} title={voice.description} value={voice.voice_id}>{voice.name}</option>)}
              </select>
            </article>
          ))}
        </div>
      ) : null}
      {choose.isError ? <p role="status">That voice could not be chosen.</p> : null}
    </section>
  );
}
