/**
 * Image Preview Plugin — Frontend Module
 *
 * This file is served as a static ES module by FastAPI.
 * It is dynamically imported by the frontend shell at runtime.
 *
 * NOTE: Since this file is loaded outside of Vite's build pipeline,
 * it must be plain JS (no JSX) and use React via a CDN-compatible
 * approach, or be a pre-compiled bundle.
 *
 * For a real project you'd compile this with Vite in library mode.
 * This stub shows the registration contract.
 */

export function register(registry) {
  const IMAGE_RE = /\.(png|jpg|jpeg|gif|webp|svg|bmp)$/i;

  // Register a previewer
  registry.previewers.push({
    id: 'image-preview',
    canHandle: (file) => IMAGE_RE.test(file.name),
    // component must be a React component function
    // In a real plugin this would be a compiled React component
    component: ({ file }) => {
      const url = `/api/files/download?path=${encodeURIComponent(file.path)}`;
      // Return a plain DOM description — in a real plugin use React.createElement
      return { type: 'img', props: { src: url, style: { maxWidth: '100%' } } };
    },
  });

  // Register a file action
  registry.fileActions.push({
    id: 'image-open-new-tab',
    label: 'Open in new tab',
    canHandle: (file) => IMAGE_RE.test(file.name),
    handler: (file) => {
      window.open(`/api/files/download?path=${encodeURIComponent(file.path)}`);
    },
  });

  console.log('[image_preview] Plugin registered.');
}
