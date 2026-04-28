import { Menu } from 'antd';
import { FolderOutlined, CloudOutlined, SettingOutlined } from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import { useSidebarItems } from '../plugin-api/hooks';

const LOGO = (
  <div style={{
    padding: '20px 16px 12px',
    fontFamily: '"DM Mono", monospace',
    fontWeight: 700,
    fontSize: 16,
    letterSpacing: '0.05em',
    color: '#e8e8e8',
    borderBottom: '1px solid #1f1f1f',
    marginBottom: 8,
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  }}>
    <FolderOutlined style={{ color: '#4096ff' }} />
    strata
  </div>
);

export default function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const pluginItems = useSidebarItems();

  const coreItems = [
    { key: '/', label: 'Files', icon: <FolderOutlined /> },
    { key: '/cloud', label: 'Cloud', icon: <CloudOutlined />, disabled: true },
    { key: '/settings', label: 'Settings', icon: <SettingOutlined />, disabled: true },
  ];

  const pluginMenuItems = pluginItems.map(p => ({
    key: p.path || `/_plugin/${p.id}`,
    label: p.label,
    icon: p.icon ?? <FolderOutlined />,
  }));

  const allItems = [...coreItems, ...(pluginMenuItems.length > 0 ? [{ type: 'divider' }, ...pluginMenuItems] : [])];

  return (
    <>
      {LOGO}
      <Menu
        theme="dark"
        mode="inline"
        selectedKeys={[location.pathname]}
        onClick={({ key }) => navigate(key)}
        items={allItems}
        style={{ background: 'transparent', borderRight: 'none' }}
      />
    </>
  );
}
