import { useMemo, useState } from 'react';
import './RpgCreateCampaignWizard.css';

interface RpgCreateCampaignWizardProps {
  onSelectCommand?: (command: string) => void;
}

type Capability = 'combat' | 'influence' | 'technical' | 'survival' | 'knowledge' | 'support';
type BuildKey = 'balanced' | 'scout' | 'negotiator' | 'survivor' | 'scholar';
type CreationStageState = 'done' | 'active' | 'pending';

interface StatDefinition {
  key: string;
  label: string;
  detail: string;
}

interface SelectOption {
  value: string;
  label: string;
  detail: string;
}

interface BuildTemplate {
  key: BuildKey;
  label: string;
  detail: string;
  boosts: Record<string, number>;
  starterGear: string[];
}

interface CreationStage {
  label: string;
  detail: string;
}

const BASE_STAT = 8;
const MAX_STAT = 16;
const STAT_POOL = 20;

const statDefinitions: StatDefinition[] = [
  { key: 'strength', label: 'Strength', detail: 'Melee force, carry weight, hard physical checks.' },
  { key: 'agility', label: 'Agility', detail: 'Initiative, stealth, dodge, delicate movement.' },
  { key: 'endurance', label: 'Endurance', detail: 'HP, exhaustion tolerance, long travel safety.' },
  { key: 'intellect', label: 'Intellect', detail: 'Knowledge checks, puzzle handling, crafting logic.' },
  { key: 'charisma', label: 'Charisma', detail: 'Dialogue leverage, prices, morale, recruitment.' },
  { key: 'perception', label: 'Perception', detail: 'Recon, clues, ambush detection, hidden details.' },
  { key: 'archery', label: 'Archery', detail: 'Ranged accuracy, combat opening, hunting shots.' },
  { key: 'survival', label: 'Survival', detail: 'Foraging, weather, resting, wilderness travel.' },
];

const buildTemplates: BuildTemplate[] = [
  {
    key: 'balanced',
    label: 'Balanced Adventurer',
    detail: 'Even stats and flexible starter gear.',
    boosts: { strength: 1, agility: 1, endurance: 1, intellect: 1, charisma: 1, perception: 1, archery: 1, survival: 1 },
    starterGear: ['Travel cloak', 'Iron dagger', 'Trail rations x3', 'Torch x2', '10 silver'],
  },
  {
    key: 'scout',
    label: 'Road Scout',
    detail: 'Recon, archery, ambush detection, and travel safety.',
    boosts: { agility: 2, perception: 3, archery: 3, survival: 2 },
    starterGear: ['Shortbow', 'Arrow bundle', 'Bedroll', 'Trail rations x4', '6 silver'],
  },
  {
    key: 'negotiator',
    label: 'Silver-Tongued Agent',
    detail: 'Dialogue, merchant pressure, recruitment, and rumor work.',
    boosts: { charisma: 4, intellect: 2, perception: 2, agility: 1 },
    starterGear: ['Fine cloak', 'Ledger note', 'Rations x2', '15 silver'],
  },
  {
    key: 'survivor',
    label: 'Hardy Survivor',
    detail: 'HP, wilderness resilience, rests, and dangerous roads.',
    boosts: { endurance: 4, survival: 4, strength: 2 },
    starterGear: ['Hand axe', 'Field kit', 'Rope coil', 'Rations x5', '5 silver'],
  },
  {
    key: 'scholar',
    label: 'Practical Scholar',
    detail: 'Knowledge, crafting recipes, clues, and ancient records.',
    boosts: { intellect: 4, perception: 3, charisma: 1, survival: 1 },
    starterGear: ['Field journal', 'Ink kit', 'Old map', 'Torch x2', '8 silver'],
  },
];

const backgrounds: SelectOption[] = [
  { value: 'wanderer', label: 'Wanderer', detail: 'Road-wise, socially flexible, and easy to seed into tavern hooks.' },
  { value: 'local', label: 'Local Regular', detail: 'Starts with stronger local rumors and familiar NPC names.' },
  { value: 'guild', label: 'Guild Apprentice', detail: 'Better crafting, trade, and service affordances.' },
  { value: 'ex-guard', label: 'Former Guard', detail: 'More combat discipline and watch authority context.' },
];

const locations: SelectOption[] = [
  { value: 'rusty-flagons', label: 'Rusty Flagon Tavern', detail: 'Best for inn, merchant, rumor, companion, and opening-hook coverage.' },
  { value: 'market-road', label: 'Market Road', detail: 'Starts near travel, trading, guards, and roadside encounters.' },
  { value: 'old-quarry', label: 'Old Quarry Edge', detail: 'Investigation-forward start with riskier exploration.' },
  { value: 'watch-post', label: 'Northern Watch Post', detail: 'Combat, guard intervention, patrols, and faction pressure.' },
];

const powerSources: SelectOption[] = [
  { value: 'mundane', label: 'Mundane', detail: 'Low-magic physical/social fantasy; strongest deterministic baseline.' },
  { value: 'divine', label: 'Divine Oath', detail: 'Support, healing hooks, vow pressure, and social expectations.' },
  { value: 'arcane', label: 'Arcane Talent', detail: 'Knowledge and utility-magic flavor while mechanics stay simulation-owned.' },
  { value: 'technique', label: 'Martial Technique', detail: 'Combat stance and skill flavor without supernatural assumptions.' },
];

const primaryCapabilities: SelectOption[] = [
  { value: 'recon', label: 'Recon', detail: 'Clues, scouting, perception, travel safety.' },
  { value: 'combat', label: 'Combat', detail: 'Initiative, damage, target choice, survival under threat.' },
  { value: 'influence', label: 'Influence', detail: 'Negotiation, recruitment, rumors, prices.' },
  { value: 'support', label: 'Support', detail: 'Party care, rest safety, service interactions.' },
  { value: 'craft', label: 'Craft / Technical', detail: 'Item use, crafting, salvage, repair, and knowledge items.' },
];

const creationStages: CreationStage[] = [
  { label: 'Validated setup', detail: 'Required fields, toggles, and point-buy totals checked.' },
  { label: 'Resolved seed', detail: 'Visible or random seed converted into deterministic campaign entropy.' },
  { label: 'Created player profile', detail: 'Identity, pronouns, background, power source, and capability tags prepared.' },
  { label: 'Applied stat allocation', detail: 'Point-buy stats and build boosts converted into initial profile metadata.' },
  { label: 'Assigned starter gear', detail: 'Starter kit, currency, and capability gear staged for session creation.' },
  { label: 'Prepared starting location', detail: 'Location, available services, and initial NPC roster resolved.' },
  { label: 'Seeding NPCs and services', detail: 'Innkeeper, merchants, rumors, party eligibility, and local events staged.' },
  { label: 'Creating opening hook', detail: 'First objective, suggested actions, and opening scene context generated.' },
  { label: 'Saving campaign session', detail: 'Autosave/checkpoint payload prepared for replay-preserving launch.' },
  { label: 'Preparing first turn context', detail: 'Turn composer, narration, TTS/STT, and optional image hooks made ready.' },
];

const capabilityLabels: Record<Capability, string> = {
  combat: 'Combat',
  influence: 'Influence',
  technical: 'Technical',
  survival: 'Survival',
  knowledge: 'Knowledge',
  support: 'Support',
};

const initialStats = Object.fromEntries(statDefinitions.map((stat) => [stat.key, BASE_STAT])) as Record<string, number>;

export function RpgCreateCampaignWizard({ onSelectCommand }: RpgCreateCampaignWizardProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [characterName, setCharacterName] = useState('Elara');
  const [pronouns, setPronouns] = useState('she/her');
  const [background, setBackground] = useState('wanderer');
  const [buildKey, setBuildKey] = useState<BuildKey>('balanced');
  const [primaryCapability, setPrimaryCapability] = useState('recon');
  const [powerSource, setPowerSource] = useState('mundane');
  const [startingLocation, setStartingLocation] = useState('rusty-flagons');
  const [difficulty, setDifficulty] = useState('normal');
  const [worldActivity, setWorldActivity] = useState('standard');
  const [economyPressure, setEconomyPressure] = useState('normal');
  const [combatLethality, setCombatLethality] = useState('normal');
  const [seed, setSeed] = useState('482193');
  const [stats, setStats] = useState<Record<string, number>>(initialStats);
  const [capabilities, setCapabilities] = useState<Record<Capability, boolean>>({
    combat: true,
    influence: false,
    technical: false,
    survival: true,
    knowledge: false,
    support: false,
  });
  const [systems, setSystems] = useState({
    autosave: true,
    companions: true,
    permadeath: false,
    grounding: true,
    softAudit: true,
    narration: true,
    images: false,
    tts: true,
    stt: true,
  });
  const [progress, setProgress] = useState(0);
  const [isCreating, setIsCreating] = useState(false);
  const [isCreated, setIsCreated] = useState(false);

  const selectedBuild = buildTemplates.find((template) => template.key === buildKey) ?? buildTemplates[0];
  const spentPoints = Object.values(stats).reduce((total, value) => total + Math.max(0, value - BASE_STAT), 0);
  const remainingPoints = STAT_POOL - spentPoints;
  const activeCapabilities = (Object.entries(capabilities) as Array<[Capability, boolean]>)
    .filter(([, enabled]) => enabled)
    .map(([capability]) => capabilityLabels[capability]);
  const activeStageIndex = Math.min(creationStages.length - 1, Math.floor((progress / 100) * creationStages.length));
  const progressPercent = Math.max(0, Math.min(100, progress));
  const selectedBackground = backgrounds.find((option) => option.value === background) ?? backgrounds[0];
  const selectedLocation = locations.find((option) => option.value === startingLocation) ?? locations[0];
  const selectedPower = powerSources.find((option) => option.value === powerSource) ?? powerSources[0];
  const selectedPrimary = primaryCapabilities.find((option) => option.value === primaryCapability) ?? primaryCapabilities[0];

  const derivedStats = useMemo(() => {
    const merged = { ...stats };
    Object.entries(selectedBuild.boosts).forEach(([key, boost]) => {
      merged[key] = Math.min(MAX_STAT + 2, (merged[key] ?? BASE_STAT) + boost);
    });
    return merged;
  }, [selectedBuild, stats]);

  const canCreate = remainingPoints >= 0 && characterName.trim().length > 0 && activeCapabilities.length > 0;

  const adjustStat = (key: string, delta: number) => {
    setStats((current) => {
      const nextValue = Math.max(BASE_STAT, Math.min(MAX_STAT, (current[key] ?? BASE_STAT) + delta));
      const next = { ...current, [key]: nextValue };
      const nextSpent = Object.values(next).reduce((total, value) => total + Math.max(0, value - BASE_STAT), 0);
      if (nextSpent > STAT_POOL) {
        return current;
      }
      return next;
    });
  };

  const toggleCapability = (capability: Capability) => {
    setCapabilities((current) => ({ ...current, [capability]: !current[capability] }));
  };

  const toggleSystem = (key: keyof typeof systems) => {
    setSystems((current) => ({ ...current, [key]: !current[key] }));
  };

  const startCreation = () => {
    if (!canCreate) {
      return;
    }
    setIsCreating(true);
    setIsCreated(false);
    setProgress(0);

    const ticks = [8, 18, 31, 44, 56, 68, 78, 88, 96, 100];
    ticks.forEach((value, index) => {
      window.setTimeout(() => {
        setProgress(value);
        if (value === 100) {
          setIsCreated(true);
        }
      }, 260 + index * 360);
    });
  };

  const closeProgress = () => {
    setIsCreating(false);
  };

  const enterWorld = () => {
    onSelectCommand?.(
      `Begin a new ${selectedBuild.label} campaign for ${characterName.trim()} at ${selectedLocation.label} with ${activeCapabilities.join(', ')} focus.`,
    );
    setIsCreating(false);
    setIsExpanded(false);
  };

  const stageState = (index: number): CreationStageState => {
    if (progressPercent >= 100 || index < activeStageIndex) {
      return 'done';
    }
    return index === activeStageIndex ? 'active' : 'pending';
  };

  if (!isExpanded) {
    return (
      <section className="rpg-create-campaign-card rpg-create-campaign-card-collapsed" aria-label="Create Campaign">
        <div>
          <p className="eyebrow">Campaign setup</p>
          <h3>Create Campaign</h3>
          <p>Open the deeper RPG setup flow with point-buy stats, starter gear, world rules, and creation progress.</p>
        </div>
        <button className="rpg-primary-button" type="button" onClick={() => setIsExpanded(true)}>
          New Campaign
        </button>
      </section>
    );
  }

  return (
    <section className="rpg-create-campaign-card" aria-label="Create Campaign">
      <header className="rpg-create-campaign-header">
        <div>
          <p className="eyebrow">New RPG campaign</p>
          <h3>Create Campaign</h3>
          <p>Build a deterministic starting state from supported RPG systems before entering the first turn.</p>
        </div>
        <div className="rpg-create-campaign-actions">
          <button className="rpg-secondary-button" type="button" onClick={() => setIsExpanded(false)}>
            Collapse setup
          </button>
          <button className="rpg-primary-button" type="button" onClick={startCreation} disabled={!canCreate}>
            Create Campaign
          </button>
        </div>
      </header>

      <div className="rpg-create-campaign-grid">
        <div className="rpg-create-section rpg-create-section-identity">
          <h4>Identity</h4>
          <div className="rpg-create-field-grid">
            <label>
              <span>Name</span>
              <input value={characterName} onChange={(event) => setCharacterName(event.target.value)} />
            </label>
            <label>
              <span>Pronouns</span>
              <input value={pronouns} onChange={(event) => setPronouns(event.target.value)} />
            </label>
            <label>
              <span>Background</span>
              <select value={background} onChange={(event) => setBackground(event.target.value)}>
                {backgrounds.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <small>{selectedBackground.detail}</small>
            </label>
            <label>
              <span>Power source</span>
              <select value={powerSource} onChange={(event) => setPowerSource(event.target.value)}>
                {powerSources.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <small>{selectedPower.detail}</small>
            </label>
          </div>
        </div>

        <div className="rpg-create-section rpg-create-section-build">
          <h4>Build and capabilities</h4>
          <div className="rpg-create-field-grid">
            <label>
              <span>Starting build</span>
              <select value={buildKey} onChange={(event) => setBuildKey(event.target.value as BuildKey)}>
                {buildTemplates.map((template) => (
                  <option key={template.key} value={template.key}>
                    {template.label}
                  </option>
                ))}
              </select>
              <small>{selectedBuild.detail}</small>
            </label>
            <label>
              <span>Primary capability</span>
              <select value={primaryCapability} onChange={(event) => setPrimaryCapability(event.target.value)}>
                {primaryCapabilities.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <small>{selectedPrimary.detail}</small>
            </label>
          </div>
          <div className="rpg-capability-grid" aria-label="Secondary capabilities">
            {(Object.keys(capabilityLabels) as Capability[]).map((capability) => (
              <label key={capability} className="rpg-create-check-row">
                <input type="checkbox" checked={capabilities[capability]} onChange={() => toggleCapability(capability)} />
                <span>{capabilityLabels[capability]}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="rpg-create-section rpg-create-section-stats">
          <div className="rpg-create-section-title-row">
            <h4>Initial stat points</h4>
            <span className={remainingPoints < 0 ? 'rpg-create-bad-count' : undefined}>{remainingPoints} points left</span>
          </div>
          <div className="rpg-stat-allocation-grid">
            {statDefinitions.map((stat) => (
              <div className="rpg-stat-allocation-row" key={stat.key}>
                <div>
                  <strong>{stat.label}</strong>
                  <small>{stat.detail}</small>
                </div>
                <div className="rpg-stat-stepper">
                  <button type="button" aria-label={`Decrease ${stat.label}`} onClick={() => adjustStat(stat.key, -1)} disabled={stats[stat.key] <= BASE_STAT}>
                    −
                  </button>
                  <span>{stats[stat.key]}</span>
                  <button type="button" aria-label={`Increase ${stat.label}`} onClick={() => adjustStat(stat.key, 1)} disabled={stats[stat.key] >= MAX_STAT || remainingPoints <= 0}>
                    +
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rpg-create-section rpg-create-section-world">
          <h4>World and rules</h4>
          <div className="rpg-create-field-grid">
            <label>
              <span>Starting location</span>
              <select value={startingLocation} onChange={(event) => setStartingLocation(event.target.value)}>
                {locations.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <small>{selectedLocation.detail}</small>
            </label>
            <label>
              <span>Difficulty</span>
              <select value={difficulty} onChange={(event) => setDifficulty(event.target.value)}>
                <option value="story">Story</option>
                <option value="normal">Normal</option>
                <option value="hard">Hard</option>
              </select>
            </label>
            <label>
              <span>World activity</span>
              <select value={worldActivity} onChange={(event) => setWorldActivity(event.target.value)}>
                <option value="quiet">Quiet</option>
                <option value="standard">Standard</option>
                <option value="busy">Busy living world</option>
              </select>
            </label>
            <label>
              <span>Economy pressure</span>
              <select value={economyPressure} onChange={(event) => setEconomyPressure(event.target.value)}>
                <option value="low">Low</option>
                <option value="normal">Normal</option>
                <option value="tight">Tight</option>
              </select>
            </label>
            <label>
              <span>Combat lethality</span>
              <select value={combatLethality} onChange={(event) => setCombatLethality(event.target.value)}>
                <option value="forgiving">Forgiving</option>
                <option value="normal">Normal</option>
                <option value="deadly">Deadly</option>
              </select>
            </label>
            <label>
              <span>Seed</span>
              <input value={seed} onChange={(event) => setSeed(event.target.value)} placeholder="Random visible seed" />
            </label>
          </div>
        </div>

        <div className="rpg-create-section rpg-create-section-systems">
          <h4>Supported systems</h4>
          <div className="rpg-system-toggle-grid">
            {(
              [
                ['autosave', 'Autosave'],
                ['companions', 'Companions enabled'],
                ['permadeath', 'Permadeath'],
                ['grounding', 'Grounding validator'],
                ['softAudit', 'Background soft audit'],
                ['narration', 'LLM narration'],
                ['images', 'Image generation'],
                ['tts', 'TTS'],
                ['stt', 'STT'],
              ] as Array<[keyof typeof systems, string]>
            ).map(([key, label]) => (
              <label key={key} className="rpg-create-check-row rpg-create-system-row">
                <input type="checkbox" checked={systems[key]} onChange={() => toggleSystem(key)} />
                <span>{label}</span>
              </label>
            ))}
          </div>
        </div>

        <aside className="rpg-create-summary" aria-label="Campaign setup summary">
          <div>
            <p className="eyebrow">Launch preview</p>
            <h4>{characterName || 'Unnamed'} · {selectedBuild.label}</h4>
            <p>{pronouns} · {selectedBackground.label} · {selectedPower.label}</p>
          </div>
          <dl>
            <div>
              <dt>Location</dt>
              <dd>{selectedLocation.label}</dd>
            </div>
            <div>
              <dt>Focus</dt>
              <dd>{selectedPrimary.label} + {activeCapabilities.join(' + ') || 'None selected'}</dd>
            </div>
            <div>
              <dt>Rules</dt>
              <dd>{difficulty} · {worldActivity} · {economyPressure} economy · {combatLethality} combat</dd>
            </div>
            <div>
              <dt>Seed</dt>
              <dd>{seed || 'Random visible seed'}</dd>
            </div>
          </dl>
          <div className="rpg-starter-kit">
            <strong>Starter gear</strong>
            <ul>
              {selectedBuild.starterGear.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          <div className="rpg-derived-stats" aria-label="Derived stat preview">
            {statDefinitions.slice(0, 6).map((stat) => (
              <span key={stat.key}>{stat.label}: {derivedStats[stat.key]}</span>
            ))}
          </div>
        </aside>
      </div>

      {!canCreate ? <p className="rpg-create-warning">Name, at least one capability, and a legal point-buy allocation are required.</p> : null}

      {isCreating ? (
        <div className="rpg-create-progress-overlay" role="dialog" aria-modal="true" aria-labelledby="rpg-create-progress-title">
          <div className="rpg-create-progress-modal">
            <header>
              <div>
                <p className="eyebrow">Campaign creation</p>
                <h3 id="rpg-create-progress-title">Creating Campaign</h3>
                <p>Building a deterministic world from your setup.</p>
              </div>
              <strong>{progressPercent}%</strong>
            </header>
            <div className="rpg-create-progress-track" aria-label="Campaign creation progress" aria-valuenow={progressPercent} aria-valuemin={0} aria-valuemax={100} role="progressbar">
              <span style={{ width: `${progressPercent}%` }} />
            </div>
            <p className="rpg-create-current-stage">{creationStages[activeStageIndex].label}: {creationStages[activeStageIndex].detail}</p>
            <div className="rpg-create-stage-list">
              {creationStages.map((stage, index) => (
                <div className={`rpg-create-stage-row rpg-create-stage-${stageState(index)}`} key={stage.label}>
                  <span aria-hidden="true">{stageState(index) === 'done' ? '✓' : stageState(index) === 'active' ? '•' : '○'}</span>
                  <div>
                    <strong>{stage.label}</strong>
                    <small>{stage.detail}</small>
                  </div>
                </div>
              ))}
            </div>
            <div className="rpg-create-modal-summary">
              <span>{characterName}</span>
              <span>{selectedBackground.label}</span>
              <span>{selectedLocation.label}</span>
              <span>{selectedBuild.label}</span>
              <span>{selectedPrimary.label}</span>
              <span>{activeCapabilities.join(' + ')}</span>
              <span>Seed {seed || 'random'}</span>
            </div>
            <p className="rpg-create-modal-note">Optional opening narration, TTS, STT, or image generation can continue after the campaign is ready.</p>
            <footer>
              <button className="rpg-secondary-button" type="button" onClick={closeProgress}>
                Cancel
              </button>
              <button className="rpg-primary-button" type="button" disabled={!isCreated} onClick={enterWorld}>
                Enter World
              </button>
            </footer>
          </div>
        </div>
      ) : null}
    </section>
  );
}
