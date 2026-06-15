import {
  Link,
  Navigate,
  Outlet,
  RouterProvider,
  createRootRoute,
  createRoute,
  createRouter,
  useRouterState,
} from '@tanstack/react-router';
import { OmnixBrand, OmnixNavItem, OmnixShellLayout, OmnixSidebar, OmnixTopBar } from '../design/primitives';
import { ModuleWorkspace } from '../features/ModuleWorkspace';
import { omnixModules, type OmnixModuleDefinition, type OmnixModuleId } from './modules';

const moduleById = Object.fromEntries(omnixModules.map((module) => [module.id, module])) as Record<
  OmnixModuleId,
  OmnixModuleDefinition
>;

function moduleFromPath(pathname: string): OmnixModuleDefinition {
  return (
    [...omnixModules]
      .sort((left, right) => right.route.length - left.route.length)
      .find((module) => pathname === module.route || pathname.startsWith(`${module.route}/`)) ?? omnixModules[0]
  );
}

function OmnixShell() {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const activeModule = moduleFromPath(pathname);

  return (
    <OmnixShellLayout
      sidebar={
        <OmnixSidebar>
          <OmnixBrand />
        <nav className="omnix-nav">
          {omnixModules.map((module) => (
            <Link key={module.id} to={module.route as never} activeProps={{ className: 'active' }}>
              <OmnixNavItem active={module.id === activeModule.id}>{module.label}</OmnixNavItem>
            </Link>
          ))}
        </nav>
        </OmnixSidebar>
      }
      topbar={<OmnixTopBar title={activeModule.label} />}
    >
        <Outlet />
    </OmnixShellLayout>
  );
}

const rootRoute = createRootRoute({
  component: OmnixShell,
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: () => <Navigate to={omnixModules[0].route as never} replace />,
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
