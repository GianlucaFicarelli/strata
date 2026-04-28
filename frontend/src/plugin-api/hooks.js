import { useMemo } from 'react';
import registry from './registry';

/** Returns the first previewer that can handle `file`, or null. */
export function usePreviewer(file) {
  return useMemo(() => {
    if (!file) return null;
    return registry.previewers.find(p => p.canHandle(file)) ?? null;
  }, [file]);
}

/** Returns all file actions applicable to `file`. */
export function useFileActions(file) {
  return useMemo(() => {
    if (!file) return [];
    return registry.fileActions.filter(a => a.canHandle(file));
  }, [file]);
}

/** Returns all sidebar items registered by plugins. */
export function useSidebarItems() {
  return registry.sidebarItems;
}

/** Returns all plugin-registered routes. */
export function usePluginRoutes() {
  return registry.routes;
}
