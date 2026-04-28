import { useEffect, useState } from 'react';
import { Layout, ConfigProvider, theme, Spin } from 'antd';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { loadPlugins } from './plugin-api/registry';
import { usePluginRoutes } from './plugin-api/hooks';
import Sidebar from './shell/Sidebar';
import FileBrowser from './shell/FileBrowser';
import './App.css';

const { Content, Sider } = Layout;

function AppRoutes() {
  const pluginRoutes = usePluginRoutes();
  return (
    <Routes>
      <Route path="*" element={<FileBrowser />} />
      {pluginRoutes.map(r => (
        <Route key={r.id} path={r.path} element={<r.component />} />
      ))}
    </Routes>
  );
}

export default function App() {
  const [pluginsReady, setPluginsReady] = useState(false);

  useEffect(() => {
    loadPlugins().finally(() => setPluginsReady(true));
  }, []);

  return (
    <ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>
      <BrowserRouter>
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
                <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
                  <Spin size="large" tip="Loading plugins…" />
                </div>
              )}
            </Content>
          </Layout>
        </Layout>
      </BrowserRouter>
    </ConfigProvider>
  );
}
