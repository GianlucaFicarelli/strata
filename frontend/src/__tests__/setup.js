import '@testing-library/jest-dom';

// Ant Design's responsive grid (Row/Col, useBreakpoint) calls window.matchMedia.
// jsdom does not implement it, so we provide a minimal stub.
// We return matches:true for min-width queries so that useBreakpoint() reports a
// desktop viewport (md/lg/xl all true), which keeps FileBrowser in table mode.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query) => ({
    matches: query.includes('min-width'),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
  }),
});

// Ant Design's Tooltip/Popconfirm/Select use ResizeObserver internally.
// jsdom doesn't implement it so we provide a no-op stub.
if (typeof window.ResizeObserver === 'undefined') {
  window.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
