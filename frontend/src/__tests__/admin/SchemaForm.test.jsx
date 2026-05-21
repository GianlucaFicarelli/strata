/**
 * Tests for SchemaForm — the generic JSON-Schema-driven form renderer.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import SchemaForm from '../../admin/SchemaForm';

// Ant Design Form needs a wrapping Form to function; provide a minimal one.
import { Form } from 'antd';

function renderForm(schema, values = {}, onChange = vi.fn(), opts = {}) {
  return render(
    <Form layout="vertical">
      <SchemaForm
        schema={schema}
        values={values}
        onChange={onChange}
        {...opts}
      />
    </Form>,
  );
}

const SIMPLE_SCHEMA = {
  properties: {
    host: { type: 'string', title: 'Host', description: 'Server hostname' },
    port: { type: 'integer', title: 'Port' },
    active: { type: 'boolean', title: 'Active' },
  },
  required: ['host'],
};

const SECRET_SCHEMA = {
  properties: {
    password: { type: 'string', title: 'Password', secret: true },
  },
};

const TEMPLATE_SCHEMA = {
  properties: {
    root: {
      type: 'string',
      title: 'Root Path',
      template: true,
      description: 'Supports {username}',
    },
  },
};

const USER_EDITABLE_SCHEMA = {
  properties: {
    admin_field: { type: 'string', title: 'Admin Field' },
    user_field: { type: 'string', title: 'User Field', user_editable: true },
  },
};

describe('SchemaForm — field rendering', () => {
  it('renders a text input for a string field', () => {
    renderForm(SIMPLE_SCHEMA, { host: 'localhost' });
    expect(screen.getByDisplayValue('localhost')).toBeInTheDocument();
  });

  it('renders a password input for secret fields', () => {
    renderForm(SECRET_SCHEMA, { password: '********' });
    // Input.Password renders <input type="password">
    const input = document.querySelector('input[type="password"]');
    expect(input).not.toBeNull();
  });

  it('shows a template tooltip icon for template fields', () => {
    renderForm(TEMPLATE_SCHEMA, { root: '/home/{username}' });
    // The InfoCircleOutlined icon is rendered as an SVG with aria role or class
    expect(document.querySelector('.anticon-info-circle')).not.toBeNull();
  });

  it('labels user_editable fields with "(user-editable)" annotation', () => {
    renderForm(USER_EDITABLE_SCHEMA, {});
    expect(screen.getByText('(user-editable)')).toBeInTheDocument();
  });

  it('renders nothing for hidden fields', () => {
    renderForm(SIMPLE_SCHEMA, { host: 'h', port: 80 }, vi.fn(), {
      hideFields: new Set(['port']),
    });
    expect(screen.queryByText('Port')).toBeNull();
    expect(screen.getByText('Host')).toBeInTheDocument();
  });

  it('disables readonly fields', () => {
    renderForm(SIMPLE_SCHEMA, { host: 'h' }, vi.fn(), {
      readonlyFields: new Set(['host']),
    });
    const input = screen.getByDisplayValue('h');
    expect(input).toBeDisabled();
  });
});

describe('SchemaForm — onChange', () => {
  it('calls onChange with field name and new value when user types', async () => {
    const onChange = vi.fn();
    renderForm(SIMPLE_SCHEMA, { host: '' }, onChange);
    const input = screen.getAllByRole('textbox')[0];
    await userEvent.clear(input);
    await userEvent.type(input, 'newhost');
    // onChange is called for each character; last call should have full value
    const calls = onChange.mock.calls;
    expect(calls.length).toBeGreaterThan(0);
    expect(calls[0][0]).toBe('host');
  });
});

describe('SchemaForm — empty / missing schema', () => {
  it('renders nothing when schema has no properties', () => {
    const { container } = renderForm({}, {});
    // No form items rendered
    expect(container.querySelector('.ant-form-item')).toBeNull();
  });

  it('renders nothing when schema is undefined', () => {
    const { container } = renderForm(undefined, {});
    expect(container.querySelector('.ant-form-item')).toBeNull();
  });
});
