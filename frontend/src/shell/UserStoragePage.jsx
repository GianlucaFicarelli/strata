/**
 * UserStoragePage — /settings/storage
 * Lets users enable/disable storage instances and fill in their personal
 * user-editable fields (e.g. SMB username + password).
 */

import { CheckCircleOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { Card, Form, message, Switch, Typography } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import SchemaForm from '../admin/SchemaForm';
import { listUserInstances, updateUserInstanceConfig } from '../core-plugins/api';

const { Title, Text } = Typography;

function initUserValues(schema, existingConfig) {
  const props = schema?.properties ?? {};
  return Object.fromEntries(
    Object.entries(props)
      .filter(([, prop]) => prop.user_editable)
      .map(([k, prop]) => [k, existingConfig[k] ?? prop.default ?? '']),
  );
}

/** Fields that are NOT user-editable — hidden entirely in the user form. */
function nonUserEditableFields(schema) {
  return new Set(
    Object.entries(schema?.properties ?? {})
      .filter(([, prop]) => !prop.user_editable)
      .map(([k]) => k),
  );
}

function InstanceCard({ inst, onUpdate }) {
  const [values, setValues] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    // initialise from the server-side masked config
    setValues(initUserValues(inst.config_schema ?? {}, inst.config));
  }, [inst]);

  async function handleToggle(enabled) {
    setSaving(true);
    try {
      await updateUserInstanceConfig(inst.instance_id, { is_enabled: enabled });
      onUpdate();
    } catch (e) {
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleFieldChange(name, value) {
    const next = { ...values, [name]: value };
    setValues(next);
    try {
      await updateUserInstanceConfig(inst.instance_id, { config: next });
      onUpdate();
    } catch (e) {
      message.error(e.message);
    }
  }

  const hasUserFields =
    inst.config_schema &&
    Object.values(inst.config_schema.properties ?? {}).some((p) => p.user_editable);

  const statusIcon = inst.is_ready ? (
    <CheckCircleOutlined style={{ color: '#52c41a' }} />
  ) : (
    <ExclamationCircleOutlined style={{ color: '#faad14' }} />
  );

  return (
    <Card
      size="small"
      style={{ marginBottom: 16, background: '#1a1a1a', border: '1px solid #2a2a2a' }}
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Switch size="small" checked={inst.is_enabled} onChange={handleToggle} loading={saving} />
          <span style={{ fontWeight: 600 }}>{inst.instance_name}</span>
          <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
            {inst.plugin_display_name}
          </Text>
          <span style={{ marginLeft: 'auto' }}>{statusIcon}</span>
        </div>
      }
    >
      {inst.is_enabled && hasUserFields && (
        <Form layout="vertical" size="small">
          <SchemaForm
            schema={inst.config_schema}
            values={values}
            onChange={handleFieldChange}
            hideFields={nonUserEditableFields(inst.config_schema)}
          />
        </Form>
      )}
      {inst.is_enabled && !inst.is_ready && (
        <Text type="warning" style={{ fontSize: 12 }}>
          {hasUserFields
            ? 'Fill in all required fields above to activate this backend.'
            : 'This backend is not ready. Contact your administrator.'}
        </Text>
      )}
    </Card>
  );
}

export default function UserStoragePage() {
  const [instances, setInstances] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listUserInstances();
      setInstances(data);
    } catch (e) {
      message.error(`Failed to load storage instances: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const enabled = instances.filter((i) => i.is_enabled);
  const disabled = instances.filter((i) => !i.is_enabled);

  return (
    <div style={{ padding: 24, maxWidth: 700 }}>
      <Title level={4} style={{ marginBottom: 4 }}>
        My Storage
      </Title>
      <Text type="secondary" style={{ display: 'block', marginBottom: 24 }}>
        Enable storage instances and fill in your personal credentials. Only enabled and
        fully-configured instances appear in the file browser.
      </Text>

      {loading && <Text type="secondary">Loading…</Text>}

      {enabled.length > 0 && (
        <>
          <Text strong style={{ display: 'block', marginBottom: 8 }}>
            Active
          </Text>
          {enabled.map((inst) => (
            <InstanceCard key={inst.instance_id} inst={inst} onUpdate={load} />
          ))}
        </>
      )}

      {disabled.length > 0 && (
        <>
          <Text strong style={{ display: 'block', marginTop: 16, marginBottom: 8 }}>
            Available (not enabled)
          </Text>
          {disabled.map((inst) => (
            <InstanceCard key={inst.instance_id} inst={inst} onUpdate={load} />
          ))}
        </>
      )}

      {!loading && instances.length === 0 && (
        <Text type="secondary">No storage instances have been configured by an admin yet.</Text>
      )}
    </div>
  );
}
