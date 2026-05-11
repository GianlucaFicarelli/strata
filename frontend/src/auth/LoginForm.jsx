/**
 * LoginForm
 * ---------
 * A minimal username/password form that works with any auth provider that
 * uses the OAuth2 password flow (application/x-www-form-urlencoded POST).
 *
 * The active provider's login_url is passed in as a prop so this component
 * knows nothing about jwt_auth specifically.  If multiple providers are
 * registered, a picker is shown so the user can choose.
 */

import { useState } from 'react';
import { Button, Card, Form, Input, Select, Typography, Alert } from 'antd';
import { LockOutlined, UserOutlined, FolderOutlined } from '@ant-design/icons';
import { useAuth } from './AuthContext';

const { Title, Text } = Typography;

export default function LoginForm({ providers }) {
  const { login } = useAuth();
  const [selectedProvider, setSelectedProvider] = useState(providers[0]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  const handleFinish = async ({ username, password }) => {
    setError(null);
    setLoading(true);
    try {
      await login(selectedProvider.login_url, username, password);
    } catch (err) {
      setError(err.message ?? 'Login failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      minHeight: '100vh',
      background: '#0f0f0f',
    }}>
      <Card
        style={{ width: 360, background: '#1a1a1a', border: '1px solid #262626' }}
        styles={{ body: { padding: '32px 28px' } }}
      >
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <FolderOutlined style={{ fontSize: 32, color: '#4096ff', marginBottom: 8 }} />
          <Title level={4} style={{ margin: 0, color: '#e8e8e8', fontFamily: '"DM Mono", monospace' }}>
            strata
          </Title>
        </div>

        {/* Provider picker — only shown when more than one provider exists */}
        {providers.length > 1 && (
          <Form.Item label={<Text style={{ color: '#8c8c8c' }}>Sign in with</Text>}>
            <Select
              value={selectedProvider.id}
              onChange={id => setSelectedProvider(providers.find(p => p.id === id))}
              options={providers.map(p => ({ value: p.id, label: p.name }))}
            />
          </Form.Item>
        )}

        {error && (
          <Alert
            message={error}
            type="error"
            showIcon
            style={{ marginBottom: 16 }}
            closable
            onClose={() => setError(null)}
          />
        )}

        <Form layout="vertical" onFinish={handleFinish} requiredMark={false}>
          <Form.Item
            name="username"
            rules={[{ required: true, message: 'Please enter your username' }]}
          >
            <Input
              prefix={<UserOutlined style={{ color: '#595959' }} />}
              placeholder="Username"
              autoComplete="username"
              autoFocus
              size="large"
            />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: 'Please enter your password' }]}
          >
            <Input.Password
              prefix={<LockOutlined style={{ color: '#595959' }} />}
              placeholder="Password"
              autoComplete="current-password"
              size="large"
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0, marginTop: 8 }}>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              size="large"
              block
            >
              Sign in
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
