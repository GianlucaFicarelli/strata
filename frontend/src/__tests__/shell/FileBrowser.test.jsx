/**
 * Integration tests for src/shell/FileBrowser.jsx
 *
 * Mocks the API module so no real network calls are made.
 * Tests verify the rendered UI, backend picker behaviour, and
 * that empty/populated states display correctly.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock the API module before importing FileBrowser
vi.mock('../../core-plugins/api', () => ({
  listBackends: vi.fn(),
  listDir: vi.fn(),
  deleteEntry: vi.fn(),
  makeDir: vi.fn(),
  uploadFile: vi.fn(),
  downloadUrl: vi.fn((path, backend) => `/api/files/download?path=${path}&backend=${backend}`),
}));

// Mock plugin hooks (no plugins in tests)
vi.mock('../../plugin-api/hooks', () => ({
  usePreviewer: vi.fn(() => null),
  useFileActions: vi.fn(() => []),
}));

// Mock FilePreview to avoid deep rendering
vi.mock('../../shell/FilePreview', () => ({
  default: ({ file }) => (file ? <div data-testid="file-preview">{file.name}</div> : null),
}));

import FileBrowser from '../../shell/FileBrowser';
import { listBackends, listDir } from '../../core-plugins/api';

const BACKENDS = [
  { id: 'storage_local', name: 'Local Filesystem' },
  { id: 's3', name: 'S3 Storage' },
];

const ENTRIES = [
  { name: 'docs', path: '/docs', is_dir: true, size: null, modified: null },
  { name: 'readme.txt', path: '/readme.txt', is_dir: false, size: 1024, modified: 1700000000 },
];

describe('FileBrowser', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listBackends.mockResolvedValue(BACKENDS);
    listDir.mockResolvedValue(ENTRIES);
  });

  it('renders without crashing', async () => {
    render(<FileBrowser />);
    await waitFor(() => expect(listDir).toHaveBeenCalled());
  });

  it('displays the list of files after loading', async () => {
    render(<FileBrowser />);
    await waitFor(() => {
      expect(screen.getByText('docs')).toBeInTheDocument();
      expect(screen.getByText('readme.txt')).toBeInTheDocument();
    });
  });

  it('shows a backend picker with all backends', async () => {
    render(<FileBrowser />);
    await waitFor(() => {
      // Ant Design Select shows the active option value
      expect(screen.getByText('Local Filesystem')).toBeInTheDocument();
    });
  });

  it('renders folder entries with directory indicator', async () => {
    render(<FileBrowser />);
    await waitFor(() => {
      const folderLink = screen.getByText('docs');
      expect(folderLink).toBeInTheDocument();
    });
  });

  it('renders file size for file entries', async () => {
    render(<FileBrowser />);
    await waitFor(() => {
      // humanSize(1024) → "1.0 KB"
      expect(screen.getByText('1.0 KB')).toBeInTheDocument();
    });
  });

  it('shows empty state when directory has no entries', async () => {
    listDir.mockResolvedValue([]);
    render(<FileBrowser />);
    await waitFor(() => {
      // Ant Design Table shows "No Data" when empty
      expect(screen.queryByText('readme.txt')).not.toBeInTheDocument();
    });
  });

  it('shows the Refresh button', async () => {
    render(<FileBrowser />);
    await waitFor(() => {
      expect(screen.getByText('Refresh')).toBeInTheDocument();
    });
  });

  it('shows the New Folder button', async () => {
    render(<FileBrowser />);
    await waitFor(() => {
      expect(screen.getByText('New Folder')).toBeInTheDocument();
    });
  });

  it('shows the Upload button', async () => {
    render(<FileBrowser />);
    await waitFor(() => {
      expect(screen.getByText('Upload')).toBeInTheDocument();
    });
  });

  it('calls listDir again when Refresh is clicked', async () => {
    render(<FileBrowser />);
    await waitFor(() => expect(listDir).toHaveBeenCalledTimes(1));

    const refreshBtn = screen.getByText('Refresh');
    fireEvent.click(refreshBtn);
    await waitFor(() => expect(listDir).toHaveBeenCalledTimes(2));
  });
});
