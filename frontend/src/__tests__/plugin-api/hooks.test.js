/**
 * Unit tests for src/plugin-api/hooks.js
 *
 * Uses renderHook from @testing-library/react so React's useMemo
 * is exercised properly.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';

import registry from '../../plugin-api/registry';
import {
  usePreviewer,
  useFileActions,
  useSidebarItems,
  usePluginRoutes,
} from '../../plugin-api/hooks';

const PNG_FILE = { name: 'photo.png', mime: 'image/png', is_dir: false };
const PDF_FILE = { name: 'doc.pdf', mime: 'application/pdf', is_dir: false };

describe('usePreviewer', () => {
  beforeEach(() => {
    registry.previewers.length = 0;
  });

  it('returns null when no file is provided', () => {
    const { result } = renderHook(() => usePreviewer(null));
    expect(result.current).toBeNull();
  });

  it('returns null when no previewer can handle the file', () => {
    registry.previewers.push({ id: 'img', canHandle: (f) => f.mime?.startsWith('image/') });
    const { result } = renderHook(() => usePreviewer(PDF_FILE));
    expect(result.current).toBeNull();
  });

  it('returns the first matching previewer', () => {
    const imgPreviewer = { id: 'img', canHandle: (f) => f.mime?.startsWith('image/') };
    const pdfPreviewer = { id: 'pdf', canHandle: (f) => f.mime === 'application/pdf' };
    registry.previewers.push(imgPreviewer, pdfPreviewer);

    const { result } = renderHook(() => usePreviewer(PNG_FILE));
    expect(result.current).toBe(imgPreviewer);
  });

  it('returns the correct previewer for a pdf', () => {
    const pdfPreviewer = { id: 'pdf', canHandle: (f) => f.mime === 'application/pdf' };
    registry.previewers.push(pdfPreviewer);

    const { result } = renderHook(() => usePreviewer(PDF_FILE));
    expect(result.current).toBe(pdfPreviewer);
  });
});

describe('useFileActions', () => {
  beforeEach(() => {
    registry.fileActions.length = 0;
  });

  it('returns empty array when no file is provided', () => {
    const { result } = renderHook(() => useFileActions(null));
    expect(result.current).toEqual([]);
  });

  it('returns only actions that can handle the file', () => {
    const downloadAction = {
      id: 'download',
      label: 'Download',
      canHandle: (f) => !f.is_dir,
    };
    const folderAction = {
      id: 'open',
      label: 'Open',
      canHandle: (f) => f.is_dir,
    };
    registry.fileActions.push(downloadAction, folderAction);

    const { result } = renderHook(() => useFileActions(PNG_FILE));
    expect(result.current).toEqual([downloadAction]);
  });

  it('returns all applicable actions', () => {
    const a1 = { id: '1', canHandle: () => true };
    const a2 = { id: '2', canHandle: () => true };
    registry.fileActions.push(a1, a2);

    const { result } = renderHook(() => useFileActions(PNG_FILE));
    expect(result.current).toHaveLength(2);
  });
});

describe('useSidebarItems', () => {
  beforeEach(() => {
    registry.sidebarItems.length = 0;
  });

  it('returns current sidebar items', () => {
    const item = { id: 'bookmarks', label: 'Bookmarks' };
    registry.sidebarItems.push(item);
    const { result } = renderHook(() => useSidebarItems());
    expect(result.current).toContain(item);
  });
});

describe('usePluginRoutes', () => {
  beforeEach(() => {
    registry.routes.length = 0;
  });

  it('returns current plugin routes', () => {
    const route = { id: 'gallery', path: '/gallery', component: () => null };
    registry.routes.push(route);
    const { result } = renderHook(() => usePluginRoutes());
    expect(result.current).toContain(route);
  });
});
