/**
 * TemplateManager — Modal for listing, editing, and deleting instruction templates
 *
 * PURPOSE:
 *   Shows all company templates in a list with Edit and Delete actions.
 *   Also provides a "Create New" button that opens TemplateEditor.
 *
 * CONNECTIONS:
 *   • workflowStore.ts → reads companyId and templates
 *   • api.ts → listTemplates(), deleteTemplate()
 *   • TemplateEditor.tsx → create/edit individual templates
 *   • TemplateSelector.tsx → triggered by "Manage" button
 */
import { useState, useEffect } from 'react';
import { useWorkflowStore } from '../../store/workflowStore';
import { api } from '../../services/api';
import { TemplateEditor } from './TemplateEditor';

interface TemplateManagerProps {
  isOpen: boolean;
  onClose: () => void;
}

export const TemplateManager = ({ isOpen, onClose }: TemplateManagerProps) => {
  const { companyId, templates, setTemplates } = useWorkflowStore();
  const [loading, setLoading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<any>(null);

  const refreshTemplates = async () => {
    if (!companyId) return;
    setLoading(true);
    try {
      const list = await api.listTemplates(companyId);
      setTemplates(list);
    } catch (error) {
      console.error('Failed to refresh templates:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      refreshTemplates();
    }
  }, [isOpen]);

  const handleDelete = async (templateId: string) => {
    if (!companyId) return;
    if (!confirm('Are you sure you want to delete this template?')) return;

    setDeletingId(templateId);
    try {
      await api.deleteTemplate(templateId, companyId);
      await refreshTemplates();
    } catch (error) {
      console.error('Failed to delete template:', error);
      alert('Failed to delete template');
    } finally {
      setDeletingId(null);
    }
  };

  const handleEdit = (template: any) => {
    setEditingTemplate(template);
    setIsEditorOpen(true);
  };

  const handleCreate = () => {
    setEditingTemplate(null);
    setIsEditorOpen(true);
  };

  const handleEditorSaved = () => {
    setIsEditorOpen(false);
    setEditingTemplate(null);
    refreshTemplates();
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
        maxWidth: '700px',
        maxHeight: '90vh',
        overflow: 'auto',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h2 style={{ fontSize: '18px', fontWeight: 600, color: '#1a1a1a', margin: 0 }}>
            Manage Templates
          </h2>
          <button
            onClick={handleCreate}
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: '#1a1a1a',
              color: 'white',
              fontSize: '13px',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            + Create New
          </button>
        </div>

        {loading && templates.length === 0 && (
          <div style={{ padding: '24px', textAlign: 'center', color: '#6b6b6b' }}>
            Loading templates...
          </div>
        )}

        {!loading && templates.length === 0 && (
          <div style={{ padding: '24px', textAlign: 'center', color: '#6b6b6b' }}>
            No templates found. Click "Create New" to add one.
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {templates.map((template) => (
            <div
              key={template.id}
              style={{
                padding: '12px 16px',
                borderRadius: '8px',
                border: '1px solid rgba(0,0,0,0.08)',
                backgroundColor: '#fafafa',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: '14px', fontWeight: 600, color: '#1a1a1a', marginBottom: '4px' }}>
                  {template.name}
                  {template.is_default && <span style={{ fontSize: '11px', color: '#6b7280', marginLeft: '6px' }}>(Global)</span>}
                  {template.is_company_default && <span style={{ fontSize: '11px', color: '#6b7280', marginLeft: '6px' }}>(Default)</span>}
                </div>
                <div style={{ fontSize: '12px', color: '#6b6b6b', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {template.description || template.content?.slice(0, 80) + '...'}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '6px', marginLeft: '12px' }}>
                <button
                  onClick={() => handleEdit(template)}
                  disabled={template.is_default}
                  title={template.is_default ? 'Global templates cannot be edited' : 'Edit template'}
                  style={{
                    padding: '6px 12px',
                    borderRadius: '6px',
                    border: '1px solid rgba(0,0,0,0.12)',
                    backgroundColor: template.is_default ? '#f5f5f5' : 'white',
                    color: template.is_default ? '#9e9e9e' : '#1a1a1a',
                    fontSize: '12px',
                    cursor: template.is_default ? 'not-allowed' : 'pointer',
                  }}
                >
                  Edit
                </button>
                <button
                  onClick={() => handleDelete(template.id)}
                  disabled={template.is_default || deletingId === template.id}
                  title={template.is_default ? 'Global templates cannot be deleted' : 'Delete template'}
                  style={{
                    padding: '6px 12px',
                    borderRadius: '6px',
                    border: '1px solid rgba(0,0,0,0.12)',
                    backgroundColor: template.is_default ? '#f5f5f5' : '#fee',
                    color: template.is_default ? '#9e9e9e' : '#c33',
                    fontSize: '12px',
                    cursor: template.is_default ? 'not-allowed' : 'pointer',
                  }}
                >
                  {deletingId === template.id ? 'Deleting...' : 'Delete'}
                </button>
              </div>
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '16px' }}>
          <button
            onClick={onClose}
            style={{
              padding: '10px 20px',
              borderRadius: '8px',
              border: '1px solid rgba(0,0,0,0.12)',
              backgroundColor: 'white',
              color: '#1a1a1a',
              fontSize: '14px',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Close
          </button>
        </div>
      </div>

      {/* Nested TemplateEditor for create/edit inside manager */}
      <TemplateEditor
        isOpen={isEditorOpen}
        onClose={() => { setIsEditorOpen(false); setEditingTemplate(null); }}
        template={editingTemplate}
        onSave={handleEditorSaved}
      />
    </div>
  );
};
