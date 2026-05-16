import { DownloadOutlined } from '@ant-design/icons';
import { Button, Modal, Space, Typography } from 'antd';
import { downloadUrl } from '../core-plugins/api';
import { usePreviewer } from '../plugin-api/hooks';

const { Text } = Typography;

const IMAGE_EXTS = /\.(png|jpg|jpeg|gif|webp|svg|bmp)$/i;

function DefaultPreviewer({ file, backend }) {
  if (IMAGE_EXTS.test(file.name)) {
    return (
      <div style={{ textAlign: 'center' }}>
        <img
          src={downloadUrl(file.path, backend)}
          alt={file.name}
          style={{ maxWidth: '100%', maxHeight: '60vh', objectFit: 'contain' }}
        />
      </div>
    );
  }
  return (
    <div style={{ padding: 24, textAlign: 'center', color: '#595959' }}>
      <p>No preview available for this file type.</p>
      <Button
        type="primary"
        icon={<DownloadOutlined />}
        onClick={() => window.open(downloadUrl(file.path, backend))}
      >
        Download
      </Button>
    </div>
  );
}

export default function FilePreview({ file, backend = 'storage_local', onClose }) {
  const pluginPreviewer = usePreviewer(file);
  if (!file) return null;

  const PreviewComponent = pluginPreviewer ? pluginPreviewer.component : DefaultPreviewer;

  return (
    <Modal
      title={
        <Space>
          <Text strong>{file.name}</Text>
          <Button
            size="small"
            icon={<DownloadOutlined />}
            onClick={() => window.open(downloadUrl(file.path, backend))}
          >
            Download
          </Button>
        </Space>
      }
      open={!!file}
      onCancel={onClose}
      footer={null}
      width={800}
      centered
    >
      <PreviewComponent file={file} backend={backend} />
    </Modal>
  );
}
