/**
 * Tests for UserStoragePage — the user self-service storage configuration UI.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import UserStoragePage from '../../shell/UserStoragePage';

vi.mock('../../core-plugins/api', () => ({
  listUserInstances: vi.fn(),
  updateUserInstanceConfig: vi.fn(),
}));

import { listUserInstances, updateUserInstanceConfig } from '../../core-plugins/api';

// ── Test data ─────────────────────────────────────────────────────────────────

const READY_INSTANCE = {
  instance_id: 'inst-ready',
  instance_name: 'Home Dirs',
  plugin_id: 'storage_local',
  plugin_display_name: 'Local Filesystem',
  is_enabled: true,
  is_ready: true,
  config: { root: '/home/alice' },
  schema: {
    properties: {
      root: { type: 'string', title: 'Root Path', template: true },
    },
  },
};

const PENDING_INSTANCE = {
  instance_id: 'inst-pending',
  instance_name: 'SMB Share',
  plugin_id: 'storage_smb',
  plugin_display_name: 'SMB / Network Share',
  is_enabled: false,
  is_ready: false,
  config: { username: '', password: '' },
  schema: {
    properties: {
      username: { type: 'string', title: 'Username', user_editable: true },
      password: { type: 'string', title: 'Password', secret: true, user_editable: true },
    },
    required: ['username', 'password'],
  },
};

describe('UserStoragePage — initial load', () => {
  it('shows the page title', async () => {
    listUserInstances.mockResolvedValue([]);
    render(<UserStoragePage />);
    await waitFor(() => {
      expect(screen.getByText('My Storage')).toBeInTheDocument();
    });
  });

  it('shows a message when no instances exist', async () => {
    listUserInstances.mockResolvedValue([]);
    render(<UserStoragePage />);
    await waitFor(() => {
      expect(screen.getByText(/no storage instances/i)).toBeInTheDocument();
    });
  });

  it('shows enabled instances in the Active section', async () => {
    listUserInstances.mockResolvedValue([READY_INSTANCE]);
    render(<UserStoragePage />);
    await waitFor(() => {
      expect(screen.getByText('Home Dirs')).toBeInTheDocument();
      expect(screen.getByText('Active')).toBeInTheDocument();
    });
  });

  it('shows disabled instances in the Available section', async () => {
    listUserInstances.mockResolvedValue([PENDING_INSTANCE]);
    render(<UserStoragePage />);
    await waitFor(() => {
      expect(screen.getByText('SMB Share')).toBeInTheDocument();
      expect(screen.getByText(/available/i)).toBeInTheDocument();
    });
  });

  it('shows both sections when instances exist in each state', async () => {
    listUserInstances.mockResolvedValue([READY_INSTANCE, PENDING_INSTANCE]);
    render(<UserStoragePage />);
    await waitFor(() => {
      expect(screen.getByText('Active')).toBeInTheDocument();
      expect(screen.getByText(/available/i)).toBeInTheDocument();
      expect(screen.getByText('Home Dirs')).toBeInTheDocument();
      expect(screen.getByText('SMB Share')).toBeInTheDocument();
    });
  });
});

describe('UserStoragePage — toggling instances', () => {
  beforeEach(() => {
    updateUserInstanceConfig.mockResolvedValue({ ...PENDING_INSTANCE, is_enabled: true });
    listUserInstances
      .mockResolvedValueOnce([PENDING_INSTANCE])
      .mockResolvedValue([{ ...PENDING_INSTANCE, is_enabled: true }]);
  });

  it('calls updateUserInstanceConfig with is_enabled when toggle is clicked', async () => {
    render(<UserStoragePage />);
    await waitFor(() => screen.getByText('SMB Share'));

    const switches = screen.getAllByRole('switch');
    await userEvent.click(switches[0]);

    await waitFor(() => {
      expect(updateUserInstanceConfig).toHaveBeenCalledWith(
        PENDING_INSTANCE.instance_id,
        expect.objectContaining({ is_enabled: expect.any(Boolean) }),
      );
    });
  });
});

describe('UserStoragePage — warning for incomplete fields', () => {
  it('shows a warning when instance is enabled but not ready', async () => {
    const enabledNotReady = { ...PENDING_INSTANCE, is_enabled: true, is_ready: false };
    listUserInstances.mockResolvedValue([enabledNotReady]);
    render(<UserStoragePage />);
    await waitFor(() => {
      expect(screen.getByText(/fill in all required fields/i)).toBeInTheDocument();
    });
  });

  it('does not show warning when instance is ready', async () => {
    listUserInstances.mockResolvedValue([READY_INSTANCE]);
    render(<UserStoragePage />);
    await waitFor(() => screen.getByText('Home Dirs'));
    expect(screen.queryByText(/fill in all required fields/i)).toBeNull();
  });
});
