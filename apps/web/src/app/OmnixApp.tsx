import { useMemo, useState } from 'react';
import { omnixModules, type OmnixModuleDefinition, type OmnixModuleId } from './modules';
import { ModuleWorkspace } from '../features/ModuleWorkspace';

function moduleFromPath(pathname: string): OmnixModuleDefinition {
  return omnixModules.find((module) => pathname.startsWith(module.route)) ?? omnixModules[0];
}

export function OmnixApp() {
  const [activeModuleId, setActiveModuleId] = useState<OmnixModuleId>(() => moduleFromPath(window.location.pathname).id);

  const activeModule = useMemo(
    () => omnixModules.find((module) => module.id === activeModuleId) ?? omnixModules[0],
    [activeModuleId],
  );

  function activateModule(module: OmnixModuleDefinition) {
    window.history.pushState(null, '', module.route);
    setActiveModuleId(module.id);
  }

  return (
    <div className="omnix-shell">
      <aside className="omnix-sidebar" aria-label="Omnix modules">
        <div className="omnix-brand">
          <span className="omnix-brand-mark">O</span>
          <div>
            <h1>Omnix</h1>
            <p>AI workstation</p>
          </div>
        </div>

        <nav className="omnix-nav">
          {omnixModules.map((module) => (
            <button
              key={module.id}
              className={module.id === activeModule.id ? 'active' : ''}
              type="button"
              onClick={() => activateModule(module)}
            >
              {module.label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="omnix-main">
        <header className="omnix-topbar">
          <div>
            <p className="eyebrow">Shared Omnix platform</p>
            <h2>{activeModule.label}</h2>
          </div>
          <div className="status-pill">Local-first</div>
        </header>

        <ModuleWorkspace module={activeModule} />
      </main>
    </div>
  );
}
