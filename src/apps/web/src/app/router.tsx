import { useMantineColorScheme } from '@mantine/core';
import {
  Link,
  Navigate,
  Outlet,
  RouterProvider,
  createRootRoute,
  createRoute,
  createRouter,
  useNavigate,
  useRouterState,
} from '@tanstack/react-router';
import { useEffect, useState } from 'react';
import { OmnixBrand, OmnixNavItem, OmnixShellLayout, OmnixSidebar, OmnixTopBar } from '../design/primitives';
import { DEFAULT_OMNIX_THEME, type OmnixThemeId } from '../design/appearanceThemes';
import {
  commitAppearanceSettings,
  loadStoredAppearancePreferences,
  OMNIX_APPEARANCE_CHANGE_EVENT,
  resolveAppearanceMode,
  type OmnixAppearanceChangeDetail,
  type OmnixAppearanceMode,
} from '../features/settings/appearanceEffects';
import { ModuleWorkspace } from '../features/ModuleWorkspace';
import { omnixModules, type OmnixModuleDefinition, type OmnixModuleId } from './modules';

const moduleById = Object.fromEntries(omnixModules.map((module) => [module.id, module])) as Record<
  OmnixModuleId,
  OmnixModuleDefinition
>;
const defaultModule = moduleById.chatbot;
const modeModuleIds: OmnixModuleId[] = ['chatbot', 'rpg', 'storyteller', 'podcast', 'voice', 'image-generation'];

// Keep lower-level platform workspaces routable without crowding the primary
// workstation navigation. These pages remain available by direct route and can
// be linked contextually from settings/diagnostics when needed.
const sidebarHiddenModuleIds = new Set<OmnixModuleId>([
  'voice-cloning',
  'providers',
  'models',
  'jobs',
]);
const sidebarModules = omnixModules.filter((module) => !sidebarHiddenModuleIds.has(module.id));

function moduleFromPath(pathname: string): OmnixModuleDefinition {
  return (
    [...omnixModules]
      .sort((left, right) => right.route.length - left.route.length)
      .find((module) => pathname === module.route || pathname.startsWith(`${module.route}/`)) ?? defaultModule
  );
}

function initialAppearanceMode(): OmnixAppearanceMode {
  return loadStoredAppearancePreferences().mode ?? 'dark';
}

function initialThemeId(): OmnixThemeId {
  return loadStoredAppearancePreferences().theme ?? DEFAULT_OMNIX_THEME;
}

function OmnixShell() {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const navigate = useNavigate();
  const { setColorScheme } = useMantineColorScheme();
  const [isSidebarVisible, setIsSidebarVisible] = useState(false);
  const [appearanceMode, setAppearanceMode] = useState<OmnixAppearanceMode>(initialAppearanceMode);
  const [themeId, setThemeId] = useState<OmnixThemeId>(initialThemeId);
  const activeModule = moduleFromPath(pathname);
  const modeModules = modeModuleIds.map((moduleId) => moduleById[moduleId]);
  const resolvedAppearanceMode = resolveAppearanceMode(appearanceMode);

  useEffect(() => {
    const root = document.documentElement;
    const detail = commitAppearanceSettings({
      mode: appearanceMode,
      theme: themeId,
      density: root.dataset.omnixDensity ?? 'comfortable',
      reduceMotion: root.classList.contains('omnix-reduce-motion'),
    });
    setColorScheme(detail.resolvedMode);
  }, [appearanceMode, setColorScheme, themeId]);

  useEffect(() => {
    const syncAppearance = (event: Event) => {
      const detail = (event as CustomEvent<OmnixAppearanceChangeDetail>).detail;
      if (!detail) return;
      setAppearanceMode(detail.mode);
      setThemeId(detail.theme);
      setColorScheme(detail.resolvedMode);
    };
    window.addEventListener(OMNIX_APPEARANCE_CHANGE_EVENT, syncAppearance);
    return () => window.removeEventListener(OMNIX_APPEARANCE_CHANGE_EVENT, syncAppearance);
  }, [setColorScheme]);

  return (
    <OmnixShellLayout
      isSidebarVisible={isSidebarVisible}
      sidebar={
        <OmnixSidebar hidden={!isSidebarVisible}>
          <OmnixBrand />
          <nav className="omnix-nav">
            {sidebarModules.map((module) => (
              <Link key={module.id} to={module.route as never} title={module.label} activeProps={{ className: 'active' }}>
                <OmnixNavItem active={module.id === activeModule.id} moduleId={module.id}>
                  {module.label}
                </OmnixNavItem>
              </Link>
            ))}
          </nav>
        </OmnixSidebar>
      }
      topbar={
        <OmnixTopBar
          isSidebarVisible={isSidebarVisible}
          onToggleSidebar={() => setIsSidebarVisible((value) => !value)}
          onToggleTheme={() => setAppearanceMode(resolvedAppearanceMode === 'light' ? 'dark' : 'light')}
          onThemeChange={setThemeId}
          themeId={themeId}
          themeMode={resolvedAppearanceMode}
          title={activeModule.label}
        >
          {modeModules.map((module) => (
            <button
              key={module.id}
              type="button"
              className={module.id === activeModule.id ? 'active' : undefined}
              aria-label={`Open ${module.label} mode`}
              onClick={() => void navigate({ to: module.route as never })}
            >
              {module.label === 'Chatbot' ? 'Chat' : module.label}
            </button>
          ))}
        </OmnixTopBar>
      }
    >
      <Outlet />
    </OmnixShellLayout>
  );
}

const rootRoute = createRootRoute({ component: OmnixShell });
const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: () => <Navigate to={defaultModule.route as never} replace />,
});

function moduleRoute<const TPath extends string>(moduleId: OmnixModuleId, path: TPath) {
  const module = moduleById[moduleId];
  return createRoute({
    getParentRoute: () => rootRoute,
    path,
    component: () => <ModuleWorkspace module={module} />,
  });
}

const rpgRoute = moduleRoute('rpg', 'rpg');
const chatbotRoute = moduleRoute('chatbot', 'chatbot');
const storytellerRoute = moduleRoute('storyteller', 'storyteller');
const podcastRoute = moduleRoute('podcast', 'podcast');
const voiceRoute = moduleRoute('voice', 'voice');
const voiceCloningRoute = moduleRoute('voice-cloning', 'voice-cloning');
const sttRoute = moduleRoute('stt', 'stt');
const imageGenerationRoute = moduleRoute('image-generation', 'image-generation');
const tradingRoute = moduleRoute('trading', 'trading');
const providersRoute = moduleRoute('providers', 'providers');
const modelsRoute = moduleRoute('models', 'models');
const jobsRoute = moduleRoute('jobs', 'jobs');
const assetsRoute = moduleRoute('assets', 'assets');
const reportsRoute = moduleRoute('reports', 'reports');
const settingsRoute = moduleRoute('settings', 'settings');
const diagnosticsRoute = moduleRoute('diagnostics', 'diagnostics');

export const moduleRoutePaths = omnixModules.map((module) => module.route);

const routeTree = rootRoute.addChildren([
  indexRoute,
  rpgRoute,
  chatbotRoute,
  storytellerRoute,
  podcastRoute,
  voiceRoute,
  voiceCloningRoute,
  sttRoute,
  imageGenerationRoute,
  tradingRoute,
  providersRoute,
  modelsRoute,
  jobsRoute,
  assetsRoute,
  reportsRoute,
  settingsRoute,
  diagnosticsRoute,
]);

export const router = createRouter({ routeTree });

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}

export function OmnixRouterProvider() {
  return <RouterProvider router={router} />;
}
