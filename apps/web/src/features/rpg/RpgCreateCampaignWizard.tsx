import { useMemo, useState } from 'react';
import {
  BASE_STAT,
  MAX_STAT,
  STAT_POOL,
  backgrounds,
  buildTemplates,
  capabilityLabels,
  creationStages,
  initialStats,
  locations,
  powerSources,
  primaryCapabilities,
  statDefinitions,
  type BuildKey,
  type Capability,
  type CreationStageState,
} from './rpgCreateCampaignState';
import './RpgCreateCampaignWizard.css';

interface RpgCreateCampaignWizardProps {
  onSelectCommand?: (command: string) => void;
}

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
      return nextSpent > STAT_POOL ? current : next;
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

    [8, 18, 31, 44, 56, 68, 78, 88, 96, 100].forEach((value, index) => {
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
            <OptionSelect label="Background" value={background} onChange={setBackground} options={backgrounds} detail={selectedBackground.detail} />
            <OptionSelect label="Power source" value={powerSource} onChange={setPowerSource} options={powerSources} detail={selectedPower.detail} />
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
            <OptionSelect label="Primary capability" value={primaryCapability} onChange={setPrimaryCapability} options={primaryCapabilities} detail={selectedPrimary.detail} />
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
            <OptionSelect label="Starting location" value={startingLocation} onChange={setStartingLocation} options={locations} detail={selectedLocation.detail} />
            <BasicSelect label="Difficulty" value={difficulty} onChange={setDifficulty} options={['story', 'normal', 'hard']} />
            <BasicSelect label="World activity" value={worldActivity} onChange={setWorldActivity} options={['quiet', 'standard', 'busy']} />
            <BasicSelect label="Economy pressure" value={economyPressure} onChange={setEconomyPressure} options={['low', 'normal', 'tight']} />
            <BasicSelect label="Combat lethality" value={combatLethality} onChange={setCombatLethality} options={['forgiving', 'normal', 'deadly']} />
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
            <SummaryRow label="Location" value={selectedLocation.label} />
            <SummaryRow label="Focus" value={`${selectedPrimary.label} + ${activeCapabilities.join(' + ') || 'None selected'}`} />
            <SummaryRow label="Rules" value={`${difficulty} · ${worldActivity} · ${economyPressure} economy · ${combatLethality} combat`} />
            <SummaryRow label="Seed" value={seed || 'Random visible seed'} />
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
        <ProgressModal
          activeCapabilities={activeCapabilities}
          activeStageIndex={activeStageIndex}
          characterName={characterName}
          closeProgress={closeProgress}
          enterWorld={enterWorld}
          isCreated={isCreated}
          progressPercent={progressPercent}
          seed={seed}
          selectedBackground={selectedBackground.label}
          selectedBuild={selectedBuild.label}
          selectedLocation={selectedLocation.label}
          selectedPrimary={selectedPrimary.label}
          stageState={stageState}
        />
      ) : null}
    </section>
  );
}

interface OptionSelectProps {
  detail?: string;
  label: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
  value: string;
}

function OptionSelect({ detail, label, onChange, options, value }: OptionSelectProps) {
  return (
    <label>
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {detail ? <small>{detail}</small> : null}
    </label>
  );
}

function BasicSelect({ label, onChange, options, value }: Omit<OptionSelectProps, 'detail' | 'options'> & { options: string[] }) {
  return (
    <label>
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option} value={option}>
            {option.replace('-', ' ')}
          </option>
        ))}
      </select>
    </label>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

interface ProgressModalProps {
  activeCapabilities: string[];
  activeStageIndex: number;
  characterName: string;
  closeProgress: () => void;
  enterWorld: () => void;
  isCreated: boolean;
  progressPercent: number;
  seed: string;
  selectedBackground: string;
  selectedBuild: string;
  selectedLocation: string;
  selectedPrimary: string;
  stageState: (index: number) => CreationStageState;
}

function ProgressModal({
  activeCapabilities,
  activeStageIndex,
  characterName,
  closeProgress,
  enterWorld,
  isCreated,
  progressPercent,
  seed,
  selectedBackground,
  selectedBuild,
  selectedLocation,
  selectedPrimary,
  stageState,
}: ProgressModalProps) {
  return (
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
          <span>{selectedBackground}</span>
          <span>{selectedLocation}</span>
          <span>{selectedBuild}</span>
          <span>{selectedPrimary}</span>
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
  );
}
