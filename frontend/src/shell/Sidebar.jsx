import { Avatar, Menu, Typography } from 'antd';
import {
  FolderOutlined,
  CloudOutlined,
  SettingOutlined,
  UserOutlined,
  LogoutOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import { useSidebarItems } from '../plugin-api/hooks';
import { useAuth } from '../auth/AuthContext';

const { Text } = Typography;

const LOGO = (
  <div
    style={{
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
    }}
  >
    <FolderOutlined style={{ color: '#4096ff' }} />
    strata
  </div>
);

function UserFooter({ user, onLogout }) {
  return (
    <div
      style={{
        position: 'absolute',
        bottom: 0,
        left: 0,
        right: 0,
        padding: '12px 16px',
        borderTop: '1px solid #1f1f1f',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}
    >
      <Avatar size={28} icon={<UserOutlined />} style={{ background: '#4096ff', flexShrink: 0 }} />
      <Text ellipsis style={{ flex: 1, color: '#d9d9d9', fontSize: 13 }} title={user.username}>
        {user.username}
      </Text>
      <LogoutOutlined
        onClick={onLogout}
        style={{ color: '#595959', cursor: 'pointer', fontSize: 14 }}
        title="Sign out"
      />
    </div>
  );
}

export default function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const pluginItems = useSidebarItems();
  const { user, logout } = useAuth();

  const coreItems = [
    { key: '/', label: 'Files', icon: <FolderOutlined /> },
    { key: '/cloud', label: 'Cloud', icon: <CloudOutlined />, disabled: true },
    { key: '/settings', label: 'Settings', icon: <SettingOutlined />, disabled: true },
  ];

  const pluginMenuItems = pluginItems.map((p) => ({
    key: p.path || `/_plugin/${p.id}`,
    label: p.label,
    icon: p.icon ?? <FolderOutlined />,
  }));

  const allItems = [
    ...coreItems,
    ...(pluginMenuItems.length > 0 ? [{ type: 'divider' }, ...pluginMenuItems] : []),
  ];

  return (
    <div style={{ position: 'relative', height: '100%' }}>
      {LOGO}
      <Menu
        theme="dark"
        mode="inline"
        selectedKeys={[location.pathname]}
        onClick={({ key }) => navigate(key)}
        items={allItems}
        style={{ background: 'transparent', borderRight: 'none' }}
      />
      {/* Only render the user footer when authenticated */}
      {user && <UserFooter user={user} onLogout={logout} />}
    </div>
  );
}
