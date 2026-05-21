/**
 * SchemaForm
 * ----------
 * Renders a form from a JSON Schema object (as returned by the backend for
 * each StorageTemplate's config_schema).
 *
 * Supported field types: string, boolean, integer, number.
 * Recognised json_schema_extra flags (passed through as-is by Pydantic):
 *   secret       → renders as Password input; masked "********" on load
 *   template     → shows a tooltip listing available {username} / {user_id} vars
 *   user_editable → (admin form: renders as disabled grey; user form: normal)
 *
 * Props:
 *   schema        JSON Schema dict (model_json_schema() output)
 *   values        Current field values { [fieldName]: value }
 *   onChange      (fieldName, value) => void
 *   readonlyFields Set<string>  fields rendered read-only (default: empty)
 *   hideFields    Set<string>  fields hidden entirely   (default: empty)
 */

import { InfoCircleOutlined } from '@ant-design/icons';
import { Form, Input, InputNumber, Switch, Tooltip, Typography } from 'antd';

const { Text } = Typography;

const TEMPLATE_VARS_TIP =
  'Supports {username} and {user_id} placeholders — expanded per user at request time.';

function FieldInput({ name, prop, value, onChange, readOnly }) {
  const isSecret = prop.secret === true;
  const isTemplate = prop.template === true;

  const suffix = isTemplate ? (
    <Tooltip title={TEMPLATE_VARS_TIP}>
      <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
    </Tooltip>
  ) : undefined;

  if (prop.type === 'boolean') {
    return <Switch checked={!!value} onChange={(v) => onChange(name, v)} disabled={readOnly} />;
  }

  if (prop.type === 'integer' || prop.type === 'number') {
    return (
      <InputNumber
        value={value ?? ''}
        onChange={(v) => onChange(name, v)}
        disabled={readOnly}
        style={{ width: '100%' }}
      />
    );
  }

  if (isSecret) {
    return (
      <Input.Password
        value={value ?? ''}
        onChange={(e) => onChange(name, e.target.value)}
        disabled={readOnly}
        placeholder={readOnly ? undefined : 'Enter value'}
        suffix={suffix}
        autoComplete="new-password"
      />
    );
  }

  return (
    <Input
      value={value ?? ''}
      onChange={(e) => onChange(name, e.target.value)}
      disabled={readOnly}
      suffix={suffix}
    />
  );
}

export default function SchemaForm({
  schema,
  values,
  onChange,
  readonlyFields = new Set(),
  hideFields = new Set(),
}) {
  const properties = schema?.properties ?? {};
  const required = new Set(schema?.required ?? []);

  return (
    <>
      {Object.entries(properties).map(([name, prop]) => {
        if (hideFields.has(name)) return null;
        const isReadOnly = readonlyFields.has(name);
        const label = (
          <span>
            {prop.title ?? name}
            {prop.user_editable && (
              <Text type="secondary" style={{ fontSize: 11, marginLeft: 6 }}>
                (user-editable)
              </Text>
            )}
          </span>
        );

        return (
          <Form.Item
            key={name}
            label={label}
            required={required.has(name)}
            tooltip={prop.description}
            style={{ marginBottom: 16 }}
          >
            <FieldInput
              name={name}
              prop={prop}
              value={values[name]}
              onChange={onChange}
              readOnly={isReadOnly}
            />
          </Form.Item>
        );
      })}
    </>
  );
}
