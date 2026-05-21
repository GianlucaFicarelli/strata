/**
 * AdminLayout — wraps all /admin/* pages.
 * Shows a sub-nav and guards against non-admin access.
 */

import { SettingOutlined } from '@ant-design/icons';
import { Menu, Typography } from 'antd';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

const { Title } = Typography;

export default function AdminLayout({ children }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  if (!user?.is_admin) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Title level={3} type="danger">
          Access Denied
        </Title>
        <p>This area is restricted to administrators.</p>
      </div>
    );
  }

  const navItems = [{ key: '/admin/storage', label: 'Storage', icon: <SettingOutlined /> }];

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      <div
        style={{
          width: 180,
          borderRight: '1px solid #1f1f1f',
          paddingTop: 16,
          background: '#0d0d0d',
          flexShrink: 0,
        }}
      >
        <div
          style={{
            padding: '8px 16px 16px',
            color: '#8c8c8c',
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
          }}
        >
          Admin
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          onClick={({ key }) => navigate(key)}
          items={navItems}
          style={{ background: 'transparent', borderRight: 'none' }}
        />
      </div>
      <div style={{ flex: 1, overflow: 'auto' }}>{children}</div>
    </div>
  );
}
