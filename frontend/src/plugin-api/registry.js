/**
 * Plugin Registry
 * ---------------
 * Holds all registered extension points.
 * Plugins call register(registry) to add themselves.
 */

const registry = {
  /** { id, canHandle(file) => bool, component: ReactComponent } */
  previewers: [],

  /** { id, label, icon?, canHandle(file) => bool, handler(file, api) } */
  fileActions: [],

  /** { id, label, icon?, component: ReactComponent } */
  sidebarItems: [],

  /** { id, label, icon?, path, component: ReactComponent } */
  routes: [],

  /** { id, label, icon?, connect() => Promise<storageBackend> } */
  storageBackends: [],
};

/**
 * Fetch the plugin list from the backend, then dynamically import each
 * plugin's JS module and call its register() export.
 */
export async function loadPlugins() {
  let plugins = [];
  try {
    const res = await fetch('/api/plugins');
    plugins = await res.json();
  } catch (e) {
    console.warn('[plugin-loader] Could not reach backend — running without plugins.', e);
    return;
  }

  for (const plugin of plugins) {
    const moduleUrl = plugin.assets?.module;
    if (!moduleUrl) continue;
    try {
      const mod = await import(/* @vite-ignore */ moduleUrl);
      if (typeof mod.register === 'function') {
        mod.register(registry);
        console.log(`[plugin-loader] Registered: ${plugin.id}`);
      }
    } catch (e) {
      console.warn(`[plugin-loader] Failed to load plugin ${plugin.id}:`, e);
    }
  }
}

export default registry;
