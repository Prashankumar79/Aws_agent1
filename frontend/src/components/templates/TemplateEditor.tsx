/**
 * TemplateEditor — Modal for creating/editing instruction templates
 *
 * PURPOSE:
 *   Modal dialog for creating new instruction templates or editing existing ones.
 *   Templates are automatically scoped to the current company.
 *
 * CONNECTIONS:
 *   • workflowStore.ts → reads companyId and templates
 *   • api.ts → createTemplate() and updateTemplate()
 *   • TemplateSelector.tsx → triggers this modal
 */
import { useState, useEffect } from 'react';
import { useWorkflowStore } from '../../store/workflowStore';
import { api } from '../../services/api';

interface TemplateEditorProps {
  isOpen: boolean;
  onClose: () => void;
  template?: any;
  onSave: () => void;
}

export const TemplateEditor = ({ isOpen, onClose, template, onSave }: TemplateEditorProps) => {
  const { companyId } = useWorkflowStore();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [content, setContent] = useState('');
  const [isCompanyDefault, setIsCompanyDefault] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Sync form fields whenever the modal opens or the template changes
  useEffect(() => {
    if (isOpen) {
      setName(template?.name || '');
      setDescription(template?.description || '');
      setContent(template?.content || '');
      setIsCompanyDefault(template?.is_company_default || false);
      setError('');
    }
  }, [isOpen, template]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!companyId) {
      setError('Please select a company first');
      return;
    }

    if (!name.trim() || !content.trim()) {
      setError('Name and content are required');
      return;
    }

    setLoading(true);
    setError('');

    try {
      if (template?.id) {
        // Update existing template
        await api.updateTemplate(template.id, companyId, {
          name,
          description,
          content,
          is_company_default: isCompanyDefault,
        });
      } else {
        // Create new template
        await api.createTemplate(companyId, {
          company_id: companyId,
          name,
          description,
          content,
          is_default: false,
          is_company_default: isCompanyDefault,
        });
      }
      
      onSave(); // Refresh template list
      onClose();
      // Reset form
      setName('');
      setDescription('');
      setContent('');
      setIsCompanyDefault(false);
    } catch (err: any) {
      setError(err.message || 'Failed to save template');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(0,0,0,0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
    }}>
      <div style={{
        backgroundColor: 'white',
        borderRadius: '12px',
        padding: '24px',
        width: '90%',
        maxWidth: '800px',
        maxHeight: '90vh',
        overflow: 'auto',
      }}>
        <h2 style={{ fontSize: '18px', fontWeight: 600, color: '#1a1a1a', marginBottom: '16px' }}>
          {template?.id ? 'Edit Template' : 'Create New Template'}
        </h2>

        {error && (
          <div style={{
            padding: '12px',
            backgroundColor: '#fee',
            border: '1px solid #fcc',
            borderRadius: '8px',
            color: '#c33',
            marginBottom: '16px',
          }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: 500, color: '#1a1a1a', marginBottom: '8px' }}>
              Template Name *
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Enterprise Standard, Cost-Optimized, Security-First"
              style={{
                width: '100%',
                padding: '12px',
                borderRadius: '8px',
                border: '1px solid rgba(0,0,0,0.12)',
                fontSize: '14px',
                fontFamily: 'inherit',
              }}
              required
            />
          </div>

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: 500, color: '#1a1a1a', marginBottom: '8px' }}>
              Description
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description of this template's purpose"
              style={{
                width: '100%',
                padding: '12px',
                borderRadius: '8px',
                border: '1px solid rgba(0,0,0,0.12)',
                fontSize: '14px',
                fontFamily: 'inherit',
              }}
            />
          </div>

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: 500, color: '#1a1a1a', marginBottom: '8px' }}>
              Template Content *
            </label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Enter your enterprise governance rules, naming conventions, security policies, etc."
              style={{
                width: '100%',
                padding: '12px',
                borderRadius: '8px',
                border: '1px solid rgba(0,0,0,0.12)',
                fontSize: '14px',
                fontFamily: 'inherit',
                minHeight: '400px',
                resize: 'vertical',
              }}
              required
            />
          </div>

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={isCompanyDefault}
                onChange={(e) => setIsCompanyDefault(e.target.checked)}
                style={{ marginRight: '8px' }}
              />
              <span style={{ fontSize: '14px', color: '#1a1a1a' }}>
                Set as company default template
              </span>
            </label>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: '12px 24px',
                borderRadius: '8px',
                border: '1px solid rgba(0,0,0,0.12)',
                backgroundColor: 'white',
                color: '#1a1a1a',
                fontSize: '14px',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              style={{
                padding: '12px 24px',
                borderRadius: '8px',
                border: 'none',
                backgroundColor: loading ? '#ccc' : '#1a1a1a',
                color: 'white',
                fontSize: '14px',
                fontWeight: 500,
                cursor: loading ? 'not-allowed' : 'pointer',
              }}
            >
              {loading ? 'Saving...' : (template?.id ? 'Update Template' : 'Create Template')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
