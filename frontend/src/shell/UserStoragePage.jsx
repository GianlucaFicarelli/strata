/**
 * UserStoragePage — /settings/storage
 * Lets users enable/disable storage instances and fill in their personal
 * user-editable fields (e.g. SMB username + password).
 */

import { CheckCircleOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Form, message, Space, Switch, Typography } from 'antd';
import { useCallback, useEffect, useRef, useState } from 'react';
import SchemaForm from '../admin/SchemaForm';
import { listUserInstances, updateUserInstanceConfig } from '../core-plugins/api';

const { Title, Text } = Typography;

const MASKED = '********';

/**
 * Build initial form values from a server response.
 * Secret fields that arrive masked are stored as MASKED internally — the
 * SchemaForm renders them as empty placeholders so the user types a fresh
 * value, and we omit them from the save payload if they remain untouched.
 */
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

/** True if two flat value objects differ on any key. */
function isDirty(a, b) {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const k of keys) {
    if (a[k] !== b[k]) return true;
  }
  return false;
}

/**
 * Strip MASKED sentinel values from the config payload before saving.
 * The backend preserves the existing encrypted value when a secret field is
 * absent from the payload, so omitting untouched secrets is both correct and
 * necessary to avoid overwriting them with the literal "********" string.
 */
function buildSavePayload(values) {
  return Object.fromEntries(
    Object.entries(values).filter(([, v]) => v !== MASKED),
  );
}

function InstanceCard({ inst, onUpdate }) {
  const [values, setValues] = useState({});
  // savedValues tracks what was last successfully persisted so we can detect dirty state.
  const savedValuesRef = useRef({});
  const [dirty, setDirty] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const initial = initUserValues(inst.config_schema ?? {}, inst.config);
    setValues(initial);
    savedValuesRef.current = initial;
    setDirty(false);
  }, [inst]);

  function handleFieldChange(name, value) {
    setValues((prev) => {
      const next = { ...prev, [name]: value };
      setDirty(isDirty(next, savedValuesRef.current));
      return next;
    });
  }

  async function handleToggle(enabled) {
    setToggling(true);
    try {
      await updateUserInstanceConfig(inst.instance_id, { is_enabled: enabled });
      onUpdate();
    } catch (e) {
      message.error(e.message);
    } finally {
      setToggling(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    try {
      const payload = buildSavePayload(values);
      await updateUserInstanceConfig(inst.instance_id, { config: payload });
      // Update saved baseline — keep MASKED sentinels for any secret fields
      // the user didn't change, so they remain detected as "not dirty".
      savedValuesRef.current = { ...values };
      setDirty(false);
      message.success('Settings saved.');
      onUpdate();
    } catch (e) {
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  }

  function handleDiscard() {
    setValues({ ...savedValuesRef.current });
    setDirty(false);
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
          <Switch
            size="small"
            checked={inst.is_enabled}
            onChange={handleToggle}
            loading={toggling}
          />
          <span style={{ fontWeight: 600 }}>{inst.instance_name}</span>
          <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
            {inst.plugin_display_name}
          </Text>
          <span style={{ marginLeft: 'auto' }}>{statusIcon}</span>
        </div>
      }
    >
      {inst.is_enabled && hasUserFields && (
        <>
          <Form layout="vertical" size="small">
            <SchemaForm
              schema={inst.config_schema}
              values={values}
              onChange={handleFieldChange}
              hideFields={nonUserEditableFields(inst.config_schema)}
            />
          </Form>

          {dirty && (
            <Alert
              message="You have unsaved changes."
              type="warning"
              showIcon
              style={{ marginBottom: 12 }}
            />
          )}

          <Space>
            <Button
              type="primary"
              size="small"
              onClick={handleSave}
              loading={saving}
              disabled={!dirty}
            >
              Save
            </Button>
            <Button size="small" onClick={handleDiscard} disabled={!dirty || saving}>
              Discard
            </Button>
          </Space>
        </>
      )}

      {inst.is_enabled && !inst.is_ready && !dirty && (
        <Text type="warning" style={{ fontSize: 12, display: 'block', marginTop: hasUserFields ? 12 : 0 }}>
          {hasUserFields
            ? 'Fill in all required fields and save to activate this backend.'
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
