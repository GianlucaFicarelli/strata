import { ConfigProvider, Layout, Spin, theme } from 'antd';
import { useEffect, useState } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import AdminLayout from './admin/AdminLayout';
import AdminStoragePage from './admin/AdminStoragePage';
import { AuthProvider } from './auth/AuthContext';
import LoginGate from './auth/LoginGate';
import { usePluginRoutes } from './plugin-api/hooks';
import { loadPlugins } from './plugin-api/registry';
import FileBrowser from './shell/FileBrowser';
import Sidebar from './shell/Sidebar';
import UserStoragePage from './shell/UserStoragePage';
import './App.css';

const { Content, Sider } = Layout;

function AppRoutes() {
  const pluginRoutes = usePluginRoutes();
  return (
    <Routes>
      <Route path="/" element={<FileBrowser />} />
      <Route path="/settings/storage" element={<UserStoragePage />} />
      <Route
        path="/admin/*"
        element={
          <AdminLayout>
            <Routes>
              <Route path="storage" element={<AdminStoragePage />} />
            </Routes>
          </AdminLayout>
        }
      />
      {pluginRoutes.map((r) => (
        <Route key={r.id} path={r.path} element={<r.component />} />
      ))}
      <Route path="*" element={<FileBrowser />} />
    </Routes>
  );
}

function AppShell() {
  const [pluginsReady, setPluginsReady] = useState(false);

  useEffect(() => {
    loadPlugins().finally(() => setPluginsReady(true));
  }, []);

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        width={220}
        breakpoint="lg"
        collapsedWidth="0"
        style={{ background: '#0f0f0f', borderRight: '1px solid #1f1f1f' }}
      >
        <Sidebar />
      </Sider>
      <Layout>
        <Content style={{ background: '#141414' }}>
          {pluginsReady ? (
            <AppRoutes />
          ) : (
            <div
              style={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                height: '100vh',
              }}
            >
              <Spin size="large" />
            </div>
          )}
        </Content>
      </Layout>
    </Layout>
  );
}

export default function App() {
  return (
    <ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>
      <BrowserRouter>
        <AuthProvider>
          <LoginGate>
            <AppShell />
          </LoginGate>
        </AuthProvider>
      </BrowserRouter>
    </ConfigProvider>
  );
}
