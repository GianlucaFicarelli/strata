import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Ant Design's `message` API (message.success / .error / .warning / .info) creates a
// persistent React root attached to document.body the first time it is called. That root
// survives component unmount and cleanup(). When jsdom tears down `window` after the last
// test in a file, React's scheduler still has queued setImmediate callbacks that try to
// flush updates into the now-dead container, producing:
//   ReferenceError: window is not defined
//     ❯ react-dom-client.development.js …
//     ❯ scheduler.development.js performWorkUntilDeadline
// Replacing message with no-op spies prevents the root from ever being created, eliminates
// the race, and is correct: unit tests should not assert on antd's notification system.
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    message: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
      info: vi.fn(),
      loading: vi.fn(),
      open: vi.fn(),
      destroy: vi.fn(),
    },
  };
});

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
