import { installViewApiFirewall } from './viewApiScope';

// Import this before side-effect fetch interceptors so they capture the
// guarded fetch rather than the unscoped browser implementation.
installViewApiFirewall();
