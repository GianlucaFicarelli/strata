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
  config_schema: {
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
  config_schema: {
    properties: {
      username: { type: 'string', title: 'Username', user_editable: true },
      password: { type: 'string', title: 'Password', secret: true, user_editable: true },
    },
    required: ['username', 'password'],
  },
};

// Enabled but not yet ready (fields empty)
const ENABLED_NOT_READY = { ...PENDING_INSTANCE, is_enabled: true };

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

describe('UserStoragePage — Save / Discard / dirty tracking', () => {
  beforeEach(() => {
    updateUserInstanceConfig.mockResolvedValue(ENABLED_NOT_READY);
    listUserInstances.mockResolvedValue([ENABLED_NOT_READY]);
  });

  it('Save button is initially disabled (form is not dirty)', async () => {
    render(<UserStoragePage />);
    await waitFor(() => screen.getByText('SMB Share'));
    const saveBtn = screen.getByRole('button', { name: /save/i });
    expect(saveBtn).toBeDisabled();
  });

  it('Save button becomes enabled after a field is changed', async () => {
    render(<UserStoragePage />);
    await waitFor(() => screen.getByText('Username'));

    const input = screen.getByPlaceholderText('');
    await userEvent.type(input, 'alice');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save/i })).not.toBeDisabled();
    });
  });

  it('calls updateUserInstanceConfig with config (not is_enabled) when Save is clicked', async () => {
    render(<UserStoragePage />);
    await waitFor(() => screen.getByText('Username'));

    const inputs = screen.getAllByRole('textbox');
    await userEvent.type(inputs[0], 'alice');

    await userEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(updateUserInstanceConfig).toHaveBeenCalledWith(
        ENABLED_NOT_READY.instance_id,
        expect.objectContaining({ config: expect.any(Object) }),
      );
    });
  });

  it('does not include masked sentinel in save payload', async () => {
    const withMasked = {
      ...ENABLED_NOT_READY,
      config: { username: 'alice', password: '********' },
    };
    listUserInstances.mockResolvedValue([withMasked]);
    render(<UserStoragePage />);
    await waitFor(() => screen.getByText('Username'));

    // Change a non-secret field to make form dirty
    const usernameInput = screen.getByDisplayValue('alice');
    await userEvent.clear(usernameInput);
    await userEvent.type(usernameInput, 'bob');

    await userEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      const [, payload] = updateUserInstanceConfig.mock.calls.at(-1);
      // password was not changed — must be absent from payload, not "********"
      expect(payload.config).not.toHaveProperty('password');
      expect(payload.config.username).toBe('bob');
    });
  });

  it('Discard resets form to saved values and disables Save', async () => {
    render(<UserStoragePage />);
    await waitFor(() => screen.getByText('Username'));

    const inputs = screen.getAllByRole('textbox');
    await userEvent.type(inputs[0], 'alice');
    expect(screen.getByRole('button', { name: /save/i })).not.toBeDisabled();

    await userEvent.click(screen.getByRole('button', { name: /discard/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save/i })).toBeDisabled();
    });
  });

  it('shows unsaved changes alert when form is dirty', async () => {
    render(<UserStoragePage />);
    await waitFor(() => screen.getByText('Username'));

    const inputs = screen.getAllByRole('textbox');
    await userEvent.type(inputs[0], 'x');

    await waitFor(() => {
      expect(screen.getByText(/unsaved changes/i)).toBeInTheDocument();
    });
  });
});

describe('UserStoragePage — warning for incomplete fields', () => {
  it('shows a warning when instance is enabled but not ready and form is clean', async () => {
    listUserInstances.mockResolvedValue([ENABLED_NOT_READY]);
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
