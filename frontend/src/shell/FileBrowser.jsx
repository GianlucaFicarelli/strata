import { useEffect, useState, useCallback } from 'react';
import {
  Table, Breadcrumb, Button, Space, Tooltip, Upload, Modal,
  Input, message, Dropdown, Grid, Card, Row, Col, Tag, Select, Typography,
} from 'antd';
import {
  FolderOutlined, FileOutlined, UploadOutlined, FolderAddOutlined,
  DeleteOutlined, DownloadOutlined, MoreOutlined, ReloadOutlined,
  HomeOutlined, DatabaseOutlined,
} from '@ant-design/icons';
import { listDir, listBackends, deleteEntry, makeDir, uploadFile, downloadUrl } from '../core-plugins/api';
import { usePreviewer, useFileActions } from '../plugin-api/hooks';
import FilePreview from './FilePreview';

const { useBreakpoint } = Grid;
const { Text } = Typography;

function humanSize(bytes) {
  if (bytes == null) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function pathParts(path) {
  const parts = path.split('/').filter(Boolean);
  return [
    { label: <HomeOutlined />, path: '/' },
    ...parts.map((p, i) => ({ label: p, path: '/' + parts.slice(0, i + 1).join('/') })),
  ];
}

export default function FileBrowser() {
  const [backends, setBackends] = useState([]);
  const [activeBackend, setActiveBackend] = useState('local_storage');
  const [cwd, setCwd] = useState('/');
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [previewFile, setPreviewFile] = useState(null);
  const [selected, setSelected] = useState(null);
  const [mkdirVisible, setMkdirVisible] = useState(false);
  const [newDirName, setNewDirName] = useState('');
  const screens = useBreakpoint();
  const isMobile = !screens.md;

  // Load available backends once on mount
  useEffect(() => {
    listBackends()
      .then(setBackends)
      .catch(() => setBackends([{ id: 'local_storage', name: 'Local Filesystem' }]));
  }, []);

  // Reset path when switching backends
  const handleBackendChange = (id) => {
    setActiveBackend(id);
    setCwd('/');
    setSelected(null);
  };

  const refresh = useCallback(async (path = cwd, backend = activeBackend) => {
    setLoading(true);
    try {
      const data = await listDir(path, backend);
      setEntries(data);
    } catch (e) {
      message.error('Failed to list directory: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [cwd, activeBackend]);

  useEffect(() => { refresh(cwd, activeBackend); }, [cwd, activeBackend]);

  const navigate = (path) => { setSelected(null); setCwd(path); };

  const handleDelete = (entry) => {
    Modal.confirm({
      title: `Delete "${entry.name}"?`,
      content: entry.is_dir ? 'This will delete the folder and all its contents.' : undefined,
      okType: 'danger',
      onOk: async () => {
        try {
          await deleteEntry(entry.path, activeBackend);
          message.success('Deleted');
          refresh();
        } catch (e) { message.error(e.message); }
      },
    });
  };

  const handleMkdir = async () => {
    if (!newDirName.trim()) return;
    try {
      await makeDir(cwd.replace(/\/$/, '') + '/' + newDirName.trim(), activeBackend);
      message.success('Folder created');
      setMkdirVisible(false);
      setNewDirName('');
      refresh();
    } catch (e) { message.error(e.message); }
  };

  const handleUpload = async ({ file }) => {
    try {
      await uploadFile(cwd, file, activeBackend);
      message.success(`Uploaded ${file.name}`);
      refresh();
    } catch (e) { message.error(e.message); }
    return false;
  };

  const EntryIcon = ({ entry }) =>
    entry.is_dir
      ? <FolderOutlined style={{ color: '#4096ff', fontSize: 16 }} />
      : <FileOutlined style={{ color: '#8c8c8c', fontSize: 16 }} />;

  const columns = [
    {
      title: 'Name', dataIndex: 'name', key: 'name',
      render: (name, entry) => (
        <Space>
          <EntryIcon entry={entry} />
          <a
            style={{ color: entry.is_dir ? '#4096ff' : '#d9d9d9' }}
            onClick={() => entry.is_dir ? navigate(entry.path) : setPreviewFile(entry)}
          >
            {name}
          </a>
        </Space>
      ),
    },
    !isMobile && {
      title: 'Size', dataIndex: 'size', key: 'size', width: 100,
      render: humanSize,
    },
    !isMobile && {
      title: 'Modified', dataIndex: 'modified', key: 'modified', width: 180,
      render: ts => ts ? new Date(ts * 1000).toLocaleString() : '—',
    },
    {
      title: '', key: 'actions', width: 48,
      render: (_, entry) => (
        <Dropdown menu={{
          items: [
            !entry.is_dir && {
              key: 'download', label: 'Download', icon: <DownloadOutlined />,
              onClick: () => window.open(downloadUrl(entry.path, activeBackend)),
            },
            {
              key: 'delete', label: 'Delete', icon: <DeleteOutlined />, danger: true,
              onClick: () => handleDelete(entry),
            },
          ].filter(Boolean),
        }}>
          <Button type="text" icon={<MoreOutlined />} size="small" />
        </Dropdown>
      ),
    },
  ].filter(Boolean);

  return (
    <div style={{ padding: isMobile ? 12 : 24 }}>

      {/* Backend picker */}
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
        <DatabaseOutlined style={{ color: '#8c8c8c' }} />
        <Text type="secondary" style={{ fontSize: 12 }}>Backend:</Text>
        <Select
          value={activeBackend}
          onChange={handleBackendChange}
          size="small"
          style={{ minWidth: 180 }}
          options={backends.map(b => ({ value: b.id, label: b.name }))}
        />
      </div>

      {/* Toolbar */}
      <Space style={{ marginBottom: 16, flexWrap: 'wrap' }}>
        <Button icon={<ReloadOutlined />} onClick={() => refresh()}>Refresh</Button>
        <Button icon={<FolderAddOutlined />} onClick={() => setMkdirVisible(true)}>New Folder</Button>
        <Upload customRequest={handleUpload} showUploadList={false}>
          <Button icon={<UploadOutlined />}>Upload</Button>
        </Upload>
      </Space>

      {/* Breadcrumb */}
      <Breadcrumb
        style={{ marginBottom: 16 }}
        items={pathParts(cwd).map(p => ({
          title: <a onClick={() => navigate(p.path)}>{p.label}</a>,
        }))}
      />

      {/* File list */}
      {isMobile ? (
        <Row gutter={[12, 12]}>
          {entries.map(entry => (
            <Col xs={12} key={entry.path}>
              <Card
                size="small"
                hoverable
                onClick={() => entry.is_dir ? navigate(entry.path) : setPreviewFile(entry)}
                style={{ background: '#1a1a1a', border: '1px solid #262626' }}
              >
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <EntryIcon entry={entry} />
                  <div style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {entry.name}
                  </div>
                  {entry.mime && <Tag style={{ fontSize: 10 }}>{entry.mime.split('/')[1]}</Tag>}
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      ) : (
        <Table
          dataSource={entries}
          columns={columns}
          rowKey="path"
          loading={loading}
          pagination={false}
          size="small"
          style={{ background: '#1a1a1a' }}
          rowSelection={{
            selectedRowKeys: selected ? [selected] : [],
            onChange: keys => setSelected(keys[0] ?? null),
          }}
        />
      )}

      {/* File preview modal */}
      <FilePreview
        file={previewFile}
        backend={activeBackend}
        onClose={() => setPreviewFile(null)}
      />

      {/* New folder modal */}
      <Modal
        title="New Folder"
        open={mkdirVisible}
        onOk={handleMkdir}
        onCancel={() => { setMkdirVisible(false); setNewDirName(''); }}
      >
        <Input
          placeholder="Folder name"
          value={newDirName}
          onChange={e => setNewDirName(e.target.value)}
          onPressEnter={handleMkdir}
          autoFocus
        />
      </Modal>
    </div>
  );
}
