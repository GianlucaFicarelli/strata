import { useEffect, useState } from 'react';
import { Layout, ConfigProvider, theme, Spin } from 'antd';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { loadPlugins } from './plugin-api/registry';
import { usePluginRoutes } from './plugin-api/hooks';
import { AuthProvider } from './auth/AuthContext';
import LoginGate from './auth/LoginGate';
import Sidebar from './shell/Sidebar';
import FileBrowser from './shell/FileBrowser';
import './App.css';

const { Content, Sider } = Layout;

function AppRoutes() {
  const pluginRoutes = usePluginRoutes();
  return (
    <Routes>
      <Route path="*" element={<FileBrowser />} />
      {pluginRoutes.map((r) => (
        <Route key={r.id} path={r.path} element={<r.component />} />
      ))}
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
              <Spin size="large" description="Loading plugins…" />
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
        {/*
          AuthProvider must wrap LoginGate so LoginGate can read loading state.
          LoginGate must wrap AppShell so the shell only renders when authed.
        */}
        <AuthProvider>
          <LoginGate>
            <AppShell />
          </LoginGate>
        </AuthProvider>
      </BrowserRouter>
    </ConfigProvider>
  );
}
