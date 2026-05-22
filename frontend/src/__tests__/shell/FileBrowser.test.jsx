/**
 * Integration tests for src/shell/FileBrowser.jsx
 *
 * Mocks the API module so no real network calls are made.
 * Tests verify the rendered UI, backend picker behaviour, and
 * that empty/populated states display correctly.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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

import { listBackends, listDir } from '../../core-plugins/api';
import FileBrowser from '../../shell/FileBrowser';

// /api/backends returns only ready instance-backed backends for the current user.
// id == instance_id because backend_to_storage_meta() uses instance.id as the routing key.
const BACKENDS = [
  { id: 'abc-123', name: 'My Local', plugin_id: 'storage_local', instance_id: 'abc-123' },
  { id: 'def-456', name: 'My S3', plugin_id: 'storage_s3', instance_id: 'def-456' },
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

  it('auto-selects the first ready instance backend', async () => {
    render(<FileBrowser />);
    await waitFor(() => {
      // Ant Design Select shows the active option label
      expect(screen.getByText('My Local (storage_local)')).toBeInTheDocument();
    });
  });

  it('calls listDir with the instance_id (UUID), not a plugin id', async () => {
    render(<FileBrowser />);
    await waitFor(() => expect(listDir).toHaveBeenCalled());
    const [, backendArg] = listDir.mock.calls[0];
    expect(backendArg).toBe('abc-123');
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

  it('shows empty state message when /api/backends returns no ready backends', async () => {
    // The backend only returns instances that are fully ready for the user.
    // An empty list means the user has nothing enabled yet.
    listBackends.mockResolvedValue([]);
    render(<FileBrowser />);
    await waitFor(() => {
      expect(screen.getByText(/No storage available/i)).toBeInTheDocument();
    });
    // listDir must never be called when there is no active backend
    expect(listDir).not.toHaveBeenCalled();
  });
});
