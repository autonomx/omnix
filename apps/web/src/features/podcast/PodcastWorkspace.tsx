import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { omnixApiClient } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import type { ProductionGenerationStyle, ReviewPolicy } from '../conversation-production/types';
import { mockPodcastRelationships, mockPodcastSpeakerProfiles } from '../conversation-production/speakers';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';
import type { PodcastFormat } from './types';
import { buildReviewPolicy, generationStyleOptions, reviewStopOptions } from './reviewPolicy';
import './PodcastWorkspace.css';

const formatOptions: Array<{ id: PodcastFormat; label: string; icon: string; description: string }> = [
  { id: 'debate', label: 'Debate', icon: '👥', description: 'Two or more opposing sides' },
  { id: 'interview', label: 'Interview', icon: '🎙', description: 'Host interviews guests' },
  { id: 'speech', label: 'Speech', icon: '♜', description: 'Solo host presentation' },
];

const constraintRows = [
  ['Max duration', '20:00'],
  ['Citation required', 'On'],
  ['Family friendly', 'On'],
  ['Reading level', 'Grade 8'],
  ['Max turn', '45 sec'],
  ['Avoid topics', 'Politics'],
];

const productionAssets = [
  ['Research', 'Generated', 'View', 'purple'],
  ['Producer Plan', 'Approved', 'Open', 'green'],
  ['Canonical Script', 'Approved', 'Edit', 'cyan'],
  ['Performance Script', 'Editable', 'Edit', 'orange'],
  ['Voice Takes', 'Generated', 'Review', 'blue'],
  ['Transcript', 'Generated', 'Edit', 'green'],
  ['Show Notes', 'Editable', 'Edit', 'purple'],
  ['Citations', 'Generated', 'View', 'blue'],
];

const downloadAssets = [
  ['MP3', 'Audio file', '♫'],
  ['WAV', 'High quality', '▥'],
  ['Transcript', 'TXT file', '▤'],
  ['Show Notes', 'Markdown', '▣'],
  ['Citations', 'BibTeX', '⌁'],
  ['Chapters', 'JSON', '§'],
];

export function PodcastWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const jobsQuery = useQuery({
    queryKey: ['platform', 'jobs'],
    queryFn: () => omnixApiClient.listJobs(),
  });
  const [title, setTitle] = useState('The Future of AI in Everyday Life');
  const [brief, setBrief] = useState(
    'Explore how artificial intelligence is shaping our daily lives, transforming work and productivity, inspiring creativity, influencing relationships, and augmenting decision-making. We’ll discuss opportunities, risks, and what comes next.'
  );
  const [format, setFormat] = useState<PodcastFormat>('debate');
  const [generationStyle, setGenerationStyle] = useState<ProductionGenerationStyle>('automatic');
  const [manualReviewStops, setManualReviewStops] = useState<Array<keyof ReviewPolicy>>([]);
  const reviewPolicy = buildReviewPolicy(generationStyle, generationStyle === 'guided' ? manualReviewStops : []);
  const podcastJobs = jobsQuery.data?.jobs.filter((job) => job.module === 'podcast') ?? [];

  const createJobMutation = useMutation({
    mutationFn: () =>
      omnixApiClient.createJob({
        module: 'podcast',
        type: 'podcast.generate',
        resource_class: 'gpu:llm',
        priority: 0,
        input_payload: {
          title,
          brief,
          format,
          audience: 'Software Engineers',
          duration_minutes: 20,
          tone: 'Professional',
          language: 'English (US)',
          generation_style: generationStyle,
          review_policy: reviewPolicy,
          renderer: 'podcast',
          speakers: mockPodcastSpeakerProfiles,
          relationships: mockPodcastRelationships,
          constraints: {
            maxDurationSeconds: 1200,
            targetDurationSeconds: 1200,
            maxSpeakerTurnSeconds: 45,
            citationRequired: true,
            familyFriendly: true,
            readingLevel: 'Grade 8',
            avoidTopics: ['Politics'],
            requiredTopics: ['practical examples', 'risks', 'future outlook'],
            disallowedClaims: [],
            tone: 'Professional',
            audience: 'Software Engineers',
            language: 'English (US)',
          },
          prompt_template_id: 'conversation.production.podcast.v1',
        },
        stages: [
          { id: 'research', label: 'Research', resource_class: 'gpu:llm', status: 'queued' },
          { id: 'producer_plan', label: 'Producer Plan', resource_class: 'gpu:llm', status: 'queued' },
          { id: 'canonical_script', label: 'Canonical Script', resource_class: 'gpu:llm', status: 'queued' },
          { id: 'performance_script', label: 'Performance Script', resource_class: 'gpu:llm', status: 'queued' },
          { id: 'voice_takes', label: 'Voice Takes', resource_class: 'gpu:tts', status: 'queued' },
          { id: 'mix', label: 'Mix', resource_class: 'cpu', status: 'queued' },
          { id: 'podcast_renderer', label: 'Podcast Renderer', resource_class: 'cpu', status: 'queued' },
        ],
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] });
    },
  });

  const submitStatus = createJobMutation.isPending ? 'queueing' : createJobMutation.isError ? 'error' : createJobMutation.data?.status ?? 'ready';
  const showBriefError = brief.trim().length === 0 && createJobMutation.isIdle === false;

  function toggleReviewStop(stopId: keyof ReviewPolicy) {
    setManualReviewStops((current) => (current.includes(stopId) ? current.filter((id) => id !== stopId) : [...current, stopId]));
  }

  return (
    <WorkspacePanel>
      <div className="podcast-studio-shell">
        <header className="podcast-studio-header">
          <div>
            <p className="eyebrow">Conversation engine</p>
            <h2 id="module-title">{module.label}</h2>
            <p>Create a podcast by generating a conversation. Research, plan, write, perform, and render automatically — with full studio control when you want it.</p>
          </div>
          <code>/podcast-renderer</code>
        </header>

        <div className="podcast-studio-grid">
          <section className="podcast-studio-stack">
            <article className="podcast-card episode-setup-card">
              <h3>▣ 1. Episode setup</h3>
              <div className="episode-setup-grid">
                <div className="podcast-field-stack">
                  <label>
                    Topic / Episode title
                    <input value={title} onChange={(event) => setTitle(event.target.value)} />
                  </label>
                  <label>
                    Episode brief
                    <textarea rows={5} value={brief} onChange={(event) => setBrief(event.target.value)} />
                    <small>{brief.length}/2000</small>
                  </label>
                  <label>
                    Audience
                    <select defaultValue="Software Engineers">
                      <option>Software Engineers</option>
                      <option>General Public</option>
                      <option>Executives</option>
                      <option>Students</option>
                      <option>Experts</option>
                    </select>
                  </label>
                </div>

                <div className="podcast-config-stack">
                  <span className="podcast-label">Podcast format</span>
                  <div className="format-card-grid">
                    {formatOptions.map((option) => (
                      <button
                        key={option.id}
                        type="button"
                        className={option.id === format ? 'selected' : undefined}
                        onClick={() => setFormat(option.id)}
                      >
                        <span>{option.icon}</span>
                        <strong>{option.label}</strong>
                        <small>{option.description}</small>
                      </button>
                    ))}
                  </div>
                  <div className="podcast-select-grid">
                    <label>
                      Duration
                      <select defaultValue="20 min">
                        <option>20 min</option>
                        <option>45 min</option>
                        <option>60 min</option>
                      </select>
                    </label>
                    <label>
                      Tone
                      <select defaultValue="Professional">
                        <option>Professional</option>
                        <option>Conversational</option>
                        <option>Humorous</option>
                      </select>
                    </label>
                    <label>
                      Language
                      <select defaultValue="English (US)">
                        <option>English (US)</option>
                        <option>English (UK)</option>
                      </select>
                    </label>
                  </div>

                  <div className="generation-style-panel">
                    <span className="podcast-label">Generation Style ⓘ</span>
                    {generationStyleOptions.map((option) => (
                      <label key={option.id} className={generationStyle === option.id ? 'generation-style selected' : 'generation-style'}>
                        <input
                          type="radio"
                          checked={generationStyle === option.id}
                          onChange={() => setGenerationStyle(option.id)}
                        />
                        <span>
                          <strong>{option.label}</strong>
                          <small>{option.description}</small>
                        </span>
                      </label>
                    ))}
                    <div className="review-stop-row" aria-label="Guided review stops">
                      {reviewStopOptions.map((option) => (
                        <label key={option.id} title={option.description}>
                          <input
                            type="checkbox"
                            disabled={generationStyle !== 'guided'}
                            checked={manualReviewStops.includes(option.id)}
                            onChange={() => toggleReviewStop(option.id)}
                          />
                          {option.label}
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </article>

            <article className="podcast-card">
              <h3>⚭ 2. Participants & voice casting</h3>
              <div className="speaker-table" role="table" aria-label="Podcast participants and voice casting">
                <div className="speaker-row speaker-header" role="row">
                  <span>Speaker</span>
                  <span>Identity</span>
                  <span>Beliefs</span>
                  <span>Personality</span>
                  <span>Speaking style</span>
                  <span>Goal this episode</span>
                  <span>Cloned voice</span>
                  <span>Preview</span>
                </div>
                {mockPodcastSpeakerProfiles.map((speaker) => (
                  <div className="speaker-row" role="row" key={speaker.id}>
                    <span className="speaker-cell-main">
                      <b className={`speaker-avatar ${speaker.id}`}>{speaker.avatar}</b>
                      <span>
                        <strong>{speaker.name}</strong>
                        <small>{speaker.role}</small>
                      </span>
                    </span>
                    <span>{speaker.identity}</span>
                    <span className="tag-stack">{speaker.beliefs.map((belief) => <b key={belief}>{belief}</b>)}</span>
                    <span className="tag-stack green">{speaker.personality.map((trait) => <b key={trait}>{trait}</b>)}</span>
                    <span className="tag-stack blue">{speaker.speakingStyle.map((style) => <b key={style}>{style}</b>)}</span>
                    <span className="tag-stack purple"><b>{speaker.segmentGoals.map(({ goal }) => goal).join(' → ') || speaker.defaultGoal}</b></span>
                    <span>
                      <select defaultValue={speaker.voiceMapping.voiceDisplayName}>
                        <option>{speaker.voiceMapping.voiceDisplayName}</option>
                      </select>
                    </span>
                    <span className="speaker-preview">▥ ⋮</span>
                  </div>
                ))}
              </div>
              <button className="ghost-button" type="button">+ Add participant</button>
            </article>

            <article className="podcast-card relationship-card">
              <h3>⌁ 3. Relationships & constraints</h3>
              <div className="relationship-layout">
                <div className="relationship-map" aria-label="Guest relationship map">
                  <b className="node host">H<span>Host</span></b>
                  <b className="node guest-a">GA<span>Guest A</span></b>
                  <b className="node guest-b">GB<span>Guest B</span></b>
                  <span className="line mod">moderates</span>
                  <span className="line respect">respects</span>
                  <span className="line disagree">disagrees with</span>
                </div>
                <div className="constraint-grid">
                  {constraintRows.map(([label, value]) => (
                    <div key={label}>
                      <small>{label}</small>
                      <strong>{value}</strong>
                    </div>
                  ))}
                </div>
              </div>
            </article>

            <form onSubmit={(event) => { event.preventDefault(); if (brief.trim()) createJobMutation.mutate(); }}>
              <button className="podcast-generate-button" type="submit" disabled={createJobMutation.isPending}>
                ✧ {createJobMutation.isPending ? 'Generating live podcast…' : 'Generate live podcast'}
              </button>
            </form>
            <FeatureValidationMessage show={showBriefError} message="Enter an episode brief before generating a podcast." />
            <FeatureSubmitFeedback
              error={createJobMutation.error}
              errorPrefix="Podcast request"
              isError={createJobMutation.isError}
              isPending={createJobMutation.isPending}
              jobId={createJobMutation.data?.id}
              pendingMessage="Starting conversation production…"
              successPrefix="Podcast production queued"
            />
          </section>

          <section className="podcast-live-column">
            <article className="podcast-card live-production-card">
              <div className="card-heading-row">
                <h3>◌ Live production</h3>
                <span className="auto-badge">Auto-approved</span>
              </div>
              <div className="stage-rail">
                {['Research', 'Producer Plan', 'Canonical Script', 'Performance Script', 'Voice Takes', 'Mix', 'Podcast Renderer'].map((stage, index) => (
                  <span key={stage} className={index < 3 ? 'done' : index === 3 ? 'active' : undefined}>{index < 3 ? '✓' : index + 1}<small>{stage}</small></span>
                ))}
              </div>
              <div className="director-note"><b>Director</b><span>Approved producer plan. Rebalancing Guest B speaking time and validating citation coverage.</span><button type="button">⌄</button></div>
              <div className="waveform" aria-hidden="true">{Array.from({ length: 64 }, (_, index) => <i key={index} style={{ height: `${18 + ((index * 17) % 42)}px` }} />)}</div>
              <div className="live-transcript">
                <p><time>06:12</time><b>Host</b><span>Welcome everyone to today’s discussion on the future of AI in everyday life.</span></p>
                <p><time>06:25</time><b>Guest A</b><span>AI is already woven into the fabric of our daily routines — from assistants and recommendations to copilots that amplify productivity.</span></p>
                <p><time>06:38</time><b>Guest B</b><span>That’s true, but we also need to be cautious. These systems can reinforce biases, reduce human agency, and create risky dependencies.</span></p>
                <p><time>06:55</time><b>Host</b><span>Great points from both sides. Let’s dig into where the biggest opportunities and risks are heading.</span></p>
              </div>
              <div className="playback-row"><button type="button">Ⅱ</button><span>▁▁▁▁▁▁</span><strong>06:42 / 20:00</strong><select defaultValue="1.0x"><option>1.0x</option></select><small>LIVE ▥</small></div>
              <label className="live-command"><input placeholder="Make Guest B more skeptical…" /><button type="button">▷</button></label>
            </article>
          </section>

          <aside className="podcast-sidebar">
            <article className="podcast-card quality-card">
              <h3>🛡 Quality gates</h3>
              {[
                ['Repetition', 'Pass'],
                ['Speaker balance', 'Warning'],
                ['Citation coverage', 'Pass'],
                ['Duration estimate', 'Pass'],
                ['Audience fit', 'Pass'],
                ['Contradictions', 'Pass'],
              ].map(([label, status]) => <p key={label} className={status === 'Warning' ? 'warning' : undefined}><span>{label}</span><b>{status}</b></p>)}
            </article>
            <article className="podcast-card health-card">
              <h3>♡ Session health</h3>
              {[
                ['Speaker balance', '72%'],
                ['Avg turn', '23s'],
                ['Interruption rate', '12%'],
                ['Pacing score', '82%'],
                ['Repetition score', '18%'],
                ['Duration drift', '+0:54'],
              ].map(([label, value]) => <div key={label}><small>{label}</small><strong>{value}</strong></div>)}
            </article>
            <article className="podcast-card recent-card">
              <div className="card-heading-row"><h3>◴ Recent jobs</h3><a>View all</a></div>
              {(podcastJobs.length ? podcastJobs.slice(0, 3).map((job) => [job.type, job.status, '20 min']) : [
                ['The Future of AI in Everyday Life', 'LIVE', '20 min'],
                ['AI and the Future of Work', 'Completed', '42 min'],
                ['Creativity in the Age of AI', 'Completed', '37 min'],
              ]).map(([name, status, duration]) => <p key={`${name}-${status}`}><span>{name}</span><OmnixStatusPill>{status}</OmnixStatusPill><small>{duration}</small><button type="button">▶</button></p>)}
            </article>
          </aside>
        </div>

        <section className="podcast-bottom-grid">
          <article className="podcast-card production-assets-panel">
            <h3>▣ Production assets ⓘ</h3>
            <div>
              {productionAssets.map(([label, status, action, color]) => (
                <section className={`asset-tile ${color}`} key={label}>
                  <b>{label}</b>
                  <small>{status}</small>
                  <button type="button">{action}</button>
                </section>
              ))}
            </div>
          </article>

          <article className="podcast-card podcast-output-panel">
            <h3>⚙ Podcast outputs ⓘ</h3>
            <div className="output-layout">
              <div className="cover-art">AI<br />EVERYDAY<br />LIFE</div>
              <div className="output-copy">
                <h4>The Future of AI in Everyday Life <span>LIVE</span></h4>
                <small>Debate • 3 voices • 20 min</small>
                <p>A deep dive into how AI is transforming daily life, work, creativity, relationships, and decision-making — plus the opportunities and risks we should watch.</p>
                <b>AI</b><b>Future</b><b>Technology</b>
              </div>
              <div className="download-grid">
                {downloadAssets.map(([label, metadata, icon]) => <button key={label} type="button"><span>{icon}</span><strong>{label}</strong><small>{metadata}</small></button>)}
                <button type="button" className="download-all">Download all ⇩</button>
                <button type="button">Copy link</button>
                <button type="button">Regenerate</button>
              </div>
            </div>
          </article>
        </section>
      </div>
    </WorkspacePanel>
  );
}
