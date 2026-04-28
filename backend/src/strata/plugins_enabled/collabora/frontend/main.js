/**
 * Collabora Online Plugin — Frontend Module
 *
 * Registers a previewer for Office-compatible file formats that renders
 * the Collabora editor inside a full-screen <iframe>.
 *
 * The backend supplies the exact Collabora URL (including the WOPI token)
 * via GET /api/plugins/collabora/editor-url?path=...&backend=...
 * so the frontend never needs to know about WOPI internals.
 *
 * @module collabora/main
 */

const HANDLED = new Set([
  ".docx", ".doc", ".odt", ".rtf",
  ".xlsx", ".xls", ".ods", ".csv",
  ".pptx", ".ppt", ".odp",
]);

/**
 * Fetch the Collabora editor URL for a given file from the backend.
 *
 * @param {string} path - Backend-relative file path.
 * @param {string} backend - Storage backend ID.
 * @returns {Promise<string>} The fully-formed Collabora launch URL.
 */
async function fetchEditorUrl(path, backend) {
  const qs = new URLSearchParams({ path, backend }).toString();
  const res = await fetch(`/api/plugins/collabora/editor-url?${qs}`);
  if (!res.ok) throw new Error(`Failed to get editor URL: ${res.statusText}`);
  const { url } = await res.json();
  return url;
}

/**
 * React component that renders the Collabora editor in an iframe.
 *
 * NOTE: This is plain JS (no JSX) because the module is served as a
 * static file outside Vite's build pipeline.  In a real project, compile
 * this with `vite build --mode lib` and serve the output bundle.
 *
 * @param {{ file: FileEntry, backend: string }} props
 * @returns {React.ReactElement}
 */
function CollaboraEditor({ file, backend = "local" }) {
  const [url, setUrl] = React.useState(null);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    fetchEditorUrl(file.path, backend)
      .then(setUrl)
      .catch((err) => setError(err.message));
  }, [file.path, backend]);

  if (error) {
    return React.createElement(
      "div",
      { style: { padding: 24, color: "#ff4d4f" } },
      `Collabora error: ${error}`,
    );
  }

  if (!url) {
    return React.createElement(
      "div",
      { style: { padding: 24, color: "#8c8c8c" } },
      "Loading editor…",
    );
  }

  return React.createElement("iframe", {
    src: url,
    style: { width: "100%", height: "80vh", border: "none" },
    allow: "fullscreen",
  });
}

/**
 * Register this plugin's extension points with the Strata frontend registry.
 *
 * Called automatically by the shell's plugin loader after dynamic import.
 *
 * @param {import('../plugin-api/registry').Registry} registry
 */
export function register(registry) {
  registry.previewers.push({
    id: "collabora",
    canHandle: (file) => {
      const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      return HANDLED.has(ext);
    },
    component: CollaboraEditor,
  });

  console.log("[collabora] Plugin registered.");
}
