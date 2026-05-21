/**
 * Tests for AdminStoragePage.
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import AdminStoragePage from '../../admin/AdminStoragePage';

vi.mock('../../core-plugins/api', () => ({
  listStorageTemplates: vi.fn(),
  listAdminInstances: vi.fn(),
  createAdminInstance: vi.fn(),
  updateAdminInstance: vi.fn(),
  deleteAdminInstance: vi.fn(),
}));

import {
  createAdminInstance,
  deleteAdminInstance,
  listAdminInstances,
  listStorageTemplates,
  updateAdminInstance,
} from '../../core-plugins/api';

const TEMPLATE = {
  plugin_id: 'storage_local',
  display_name: 'Local Filesystem',
  description: 'Exposes a local directory',
  config_schema: {
    properties: {
      root: { type: 'string', title: 'Root Path', default: '/home/{username}', template: true },
    },
    required: ['root'],
  },
};

const INSTANCE = {
  id: 'inst-001',
  plugin_id: 'storage_local',
  instance_name: 'Home Dirs',
  config: { root: '/home/{username}' },
  is_enabled: true,
  created_at: '2026-01-01T00:00:00',
  updated_at: '2026-01-01T00:00:00',
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AdminStoragePage — initial load', () => {
  it('shows the instance name and plugin type', async () => {
    listStorageTemplates.mockResolvedValue([TEMPLATE]);
    listAdminInstances.mockResolvedValue([INSTANCE]);
    render(<AdminStoragePage />);
    await waitFor(() => expect(screen.getByText('Home Dirs')).toBeInTheDocument());
    expect(screen.getByText('Local Filesystem')).toBeInTheDocument();
  });

  it('shows New Instance button when templates exist', async () => {
    listStorageTemplates.mockResolvedValue([TEMPLATE]);
    listAdminInstances.mockResolvedValue([]);
    render(<AdminStoragePage />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /new instance/i })).toBeInTheDocument(),
    );
  });

  it('shows message when no templates registered', async () => {
    listStorageTemplates.mockResolvedValue([]);
    listAdminInstances.mockResolvedValue([]);
    render(<AdminStoragePage />);
    await waitFor(() =>
      expect(screen.getByText(/no storage templates are registered/i)).toBeInTheDocument(),
    );
  });

  it('disables New Instance button when no templates', async () => {
    listStorageTemplates.mockResolvedValue([]);
    listAdminInstances.mockResolvedValue([]);
    render(<AdminStoragePage />);
    await waitFor(() => {
      const btn = screen.getByRole('button', { name: /new instance/i });
      expect(btn).toBeDisabled();
    });
  });
});

describe('AdminStoragePage — create instance modal', () => {
  beforeEach(() => {
    listStorageTemplates.mockResolvedValue([TEMPLATE]);
    listAdminInstances.mockResolvedValue([]);
  });

  it('opens modal when New Instance is clicked', async () => {
    render(<AdminStoragePage />);
    await waitFor(() => screen.getByRole('button', { name: /new instance/i }));
    await userEvent.click(screen.getByRole('button', { name: /new instance/i }));
    await waitFor(() => expect(screen.getAllByText('New Instance').length).toBeGreaterThan(0));
    // 'Template' appears in both table header and modal form label
    expect(screen.getAllByText('Template').length).toBeGreaterThan(0);
  });

  it('does not call createAdminInstance when name is empty', async () => {
    createAdminInstance.mockResolvedValue({ ...INSTANCE, id: 'new' });
    render(<AdminStoragePage />);
    await waitFor(() => screen.getByRole('button', { name: /new instance/i }));
    await userEvent.click(screen.getByRole('button', { name: /new instance/i }));
    await waitFor(() => screen.getByRole('dialog'));
    // Click OK without filling in name
    const modal = screen.getByRole('dialog');
    const okBtn = within(modal).getByRole('button', { name: /ok/i });
    await userEvent.click(okBtn);
    // Guard should fire, not createAdminInstance
    expect(createAdminInstance).not.toHaveBeenCalled();
  });

  it('calls createAdminInstance with filled name and schema defaults', async () => {
    createAdminInstance.mockResolvedValue({ ...INSTANCE, id: 'new-inst' });
    listAdminInstances.mockResolvedValue([{ ...INSTANCE, id: 'new-inst' }]);
    render(<AdminStoragePage />);
    await waitFor(() => screen.getByRole('button', { name: /new instance/i }));
    await userEvent.click(screen.getByRole('button', { name: /new instance/i }));
    await waitFor(() => screen.getByPlaceholderText(/team documents/i));
    await userEvent.type(screen.getByPlaceholderText(/team documents/i), 'My Files');
    const modal = screen.getByRole('dialog');
    await userEvent.click(within(modal).getByRole('button', { name: /ok/i }));
    await waitFor(() =>
      expect(createAdminInstance).toHaveBeenCalledWith(
        expect.objectContaining({ plugin_id: 'storage_local', instance_name: 'My Files' }),
      ),
    );
  });
});

describe('AdminStoragePage — enable/disable toggle', () => {
  it('calls updateAdminInstance on switch toggle', async () => {
    listStorageTemplates.mockResolvedValue([TEMPLATE]);
    listAdminInstances.mockResolvedValue([INSTANCE]);
    updateAdminInstance.mockResolvedValue({ ...INSTANCE, is_enabled: false });
    render(<AdminStoragePage />);
    await waitFor(() => screen.getByText('Home Dirs'));
    const switches = screen.getAllByRole('switch');
    await userEvent.click(switches[0]);
    await waitFor(() =>
      expect(updateAdminInstance).toHaveBeenCalledWith(
        INSTANCE.id,
        expect.objectContaining({ is_enabled: expect.any(Boolean) }),
      ),
    );
  });
});

describe('AdminStoragePage — delete instance', () => {
  afterEach(() => { cleanup(); });

  it('calls deleteAdminInstance after popconfirm confirmation', async () => {
    listStorageTemplates.mockResolvedValue([TEMPLATE]);
    listAdminInstances.mockResolvedValueOnce([INSTANCE]).mockResolvedValue([]);
    deleteAdminInstance.mockResolvedValue(undefined);
    render(<AdminStoragePage />);
    await waitFor(() => screen.getByText('Home Dirs'));

    // Find the delete button (danger icon button in the row)
    const deleteBtn = screen
      .getAllByRole('button')
      .find((b) => b.querySelector('.anticon-delete'));
    expect(deleteBtn).toBeDefined();
    await userEvent.click(deleteBtn);

    // Popconfirm appears — confirm
    await waitFor(() => screen.getByRole('tooltip'));
    const tooltip = screen.getByRole('tooltip');
    const confirmBtn = within(tooltip).getByRole('button', { name: /ok/i });
    await userEvent.click(confirmBtn);

    await waitFor(() => expect(deleteAdminInstance).toHaveBeenCalledWith(INSTANCE.id));
  });
});
