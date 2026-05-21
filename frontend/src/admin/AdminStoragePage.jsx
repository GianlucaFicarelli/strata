/**
 * AdminStoragePage — /admin/storage
 * Lists all storage instances; allows create, edit, toggle, delete.
 */

import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import {
  Button,
  Form,
  Input,
  Modal,
  message,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd';
import { useCallback, useEffect, useState } from 'react';
import {
  createAdminInstance,
  deleteAdminInstance,
  listAdminInstances,
  listStorageTemplates,
  updateAdminInstance,
} from '../core-plugins/api';
import SchemaForm from './SchemaForm';

const { Title, Text } = Typography;

function initValues(schema, existing = {}) {
  const props = schema?.properties ?? {};
  return Object.fromEntries(
    Object.entries(props).map(([k, prop]) => [
      k,
      existing[k] ?? prop.default ?? (prop.type === 'boolean' ? false : ''),
    ]),
  );
}

export default function AdminStoragePage() {
  const [templates, setTemplates] = useState([]);
  const [instances, setInstances] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [selectedPluginId, setSelectedPluginId] = useState(null);
  const [instanceName, setInstanceName] = useState('');
  const [fieldValues, setFieldValues] = useState({});
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [tmpls, insts] = await Promise.all([listStorageTemplates(), listAdminInstances()]);
      setTemplates(tmpls);
      setInstances(insts);
    } catch (e) {
      message.error(`Failed to load: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const activeTemplate = templates.find((t) => t.plugin_id === selectedPluginId) ?? null;

  function openCreate() {
    const first = templates[0] ?? null;
    setEditTarget(null);
    setSelectedPluginId(first?.plugin_id ?? null);
    setInstanceName('');
    setFieldValues(first ? initValues(first.config_schema) : {});
    setModalOpen(true);
  }

  function openEdit(inst) {
    const tmpl = templates.find((t) => t.plugin_id === inst.plugin_id);
    setEditTarget(inst);
    setSelectedPluginId(inst.plugin_id);
    setInstanceName(inst.instance_name);
    setFieldValues(initValues(tmpl?.config_schema ?? {}, inst.config));
    setModalOpen(true);
  }

  function handleTemplateChange(pid) {
    setSelectedPluginId(pid);
    const tmpl = templates.find((t) => t.plugin_id === pid);
    setFieldValues(initValues(tmpl?.config_schema ?? {}));
  }

  function handleFieldChange(name, value) {
    setFieldValues((prev) => ({ ...prev, [name]: value }));
  }

  async function handleSave() {
    if (!instanceName.trim()) {
      message.warning('Instance name is required');
      return;
    }
    setSaving(true);
    try {
      if (editTarget) {
        await updateAdminInstance(editTarget.id, {
          instance_name: instanceName,
          config: fieldValues,
        });
        message.success('Instance updated');
      } else {
        await createAdminInstance({
          plugin_id: selectedPluginId,
          instance_name: instanceName,
          config: fieldValues,
        });
        message.success('Instance created');
      }
      setModalOpen(false);
      load();
    } catch (e) {
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(inst, enabled) {
    try {
      await updateAdminInstance(inst.id, { is_enabled: enabled });
      load();
    } catch (e) {
      message.error(e.message);
    }
  }

  async function handleDelete(id) {
    try {
      await deleteAdminInstance(id);
      message.success('Deleted');
      load();
    } catch (e) {
      message.error(e.message);
    }
  }

  const columns = [
    {
      title: 'Name',
      key: 'name',
      render: (_, inst) => {
        const tmpl = templates.find((t) => t.plugin_id === inst.plugin_id);
        return (
          <Space direction="vertical" size={0}>
            <Text strong>{inst.instance_name}</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {tmpl?.display_name ?? inst.plugin_id}
            </Text>
          </Space>
        );
      },
    },
    {
      title: 'Template',
      dataIndex: 'plugin_id',
      key: 'plugin_id',
      width: 160,
      render: (pid) => <Tag>{pid}</Tag>,
    },
    {
      title: 'Enabled',
      dataIndex: 'is_enabled',
      key: 'is_enabled',
      width: 80,
      render: (val, inst) => (
        <Switch size="small" checked={val} onChange={(v) => handleToggle(inst, v)} />
      ),
    },
    {
      title: '',
      key: 'actions',
      width: 80,
      render: (_, inst) => (
        <Space>
          <Button type="text" icon={<EditOutlined />} size="small" onClick={() => openEdit(inst)} />
          <Popconfirm
            title="Delete this instance?"
            description="All user configs will also be deleted."
            onConfirm={() => handleDelete(inst.id)}
            okType="danger"
          >
            <Button type="text" icon={<DeleteOutlined />} size="small" danger />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 20,
        }}
      >
        <Title level={4} style={{ margin: 0 }}>
          Storage Instances
        </Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={openCreate}
          disabled={templates.length === 0}
        >
          New Instance
        </Button>
      </div>

      {templates.length === 0 && !loading && (
        <Text type="secondary">No storage templates are registered by any plugin.</Text>
      )}

      <Table
        dataSource={instances}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={false}
        size="small"
      />

      <Modal
        title={editTarget ? 'Edit Instance' : 'New Instance'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        confirmLoading={saving}
        width={560}
        destroyOnClose
      >
        <Form layout="vertical" style={{ marginTop: 16 }}>
          {!editTarget && (
            <Form.Item label="Template" required>
              <Select
                value={selectedPluginId}
                onChange={handleTemplateChange}
                options={templates.map((t) => ({
                  value: t.plugin_id,
                  label: (
                    <Space direction="vertical" size={0}>
                      <span>{t.display_name}</span>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {t.description}
                      </Text>
                    </Space>
                  ),
                }))}
              />
            </Form.Item>
          )}

          <Form.Item label="Instance Name" required>
            <Input
              value={instanceName}
              onChange={(e) => setInstanceName(e.target.value)}
              placeholder="e.g. Team Documents"
            />
          </Form.Item>

          {activeTemplate && (
            <SchemaForm
              schema={activeTemplate.config_schema}
              values={fieldValues}
              onChange={handleFieldChange}
            />
          )}
        </Form>
      </Modal>
    </div>
  );
}
