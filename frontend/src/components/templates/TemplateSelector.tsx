/**
 * TemplateSelector — Instruction template selection dropdown
 *
 * PURPOSE:
 *   Allows users to select from available instruction templates for their company.
 *   Templates are scoped to the current company (multi-tenant).
 *
 * CONNECTIONS:
 *   • workflowStore.ts → reads/writes selectedTemplateId and templates
 *   • api.ts → listTemplates() to fetch templates for current company
 *   • UploadPage.tsx → auto-fills textarea when template is selected
 */
import { useState, useEffect } from 'react';
import { useWorkflowStore } from '../../store/workflowStore';
import { api } from '../../services/api';
import { TemplateEditor } from './TemplateEditor';
import { TemplateManager } from './TemplateManager';

export const TemplateSelector = ({ onTemplateSelect }: { onTemplateSelect: (content: string) => void }) => {
  const { companyId, selectedTemplateId, setSelectedTemplateId, setTemplates, templates, userPrompt } = useWorkflowStore();
  const [loading, setLoading] = useState(false);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editorTemplate, setEditorTemplate] = useState<any>(null);
  const [isManagerOpen, setIsManagerOpen] = useState(false);
  const [viewingTemplate, setViewingTemplate] = useState<any>(null);

  // Load templates — auto-select first company if none selected
  useEffect(() => {
    const loadTemplates = async () => {
      setLoading(true);
      try {
        // If no company selected, auto-select the first one
        let activeCompanyId = companyId;
        if (!activeCompanyId) {
          const companies = await api.listCompanies();
          if (companies.length > 0) {
            activeCompanyId = companies[0].id;
            // Set it in the store so the backend gets it
            useWorkflowStore.getState().setCompanyId(activeCompanyId);
            useWorkflowStore.getState().setCompany(companies[0]);
          }
        }
        if (activeCompanyId) {
          const templateList = await api.listTemplates(activeCompanyId);
          setTemplates(templateList);
        }
      } catch (error) {
        console.error('Failed to load templates:', error);
      } finally {
        setLoading(false);
      }
    };

    loadTemplates();
  }, [companyId, setTemplates]);

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const selectedId = e.target.value;
    setSelectedTemplateId(selectedId);
    
    // Notify parent that a template was selected (for any UI updates)
    const selectedTemplate = templates.find(t => t.id === selectedId);
    if (selectedTemplate && selectedTemplate.content) {
      onTemplateSelect(selectedTemplate.content);
    }
  };

  const handleViewTemplate = () => {
    const selectedTemplate = templates.find(t => t.id === selectedTemplateId);
    if (selectedTemplate) {
      setViewingTemplate(selectedTemplate);
    }
  };

  const handleSaveAsTemplate = () => {
    setEditorTemplate(userPrompt ? { content: userPrompt, name: '', description: '' } : null);
    setIsEditorOpen(true);
  };

  const handleManageTemplates = () => {
    setIsManagerOpen(true);
  };

  const handleEditorSaved = async () => {
    setIsEditorOpen(false);
    setEditorTemplate(null);
    // Refresh template list
    if (companyId) {
      try {
        const list = await api.listTemplates(companyId);
        setTemplates(list);
      } catch (error) {
        console.error('Failed to refresh templates:', error);
      }
    }
  };

  return (
    <div style={{ marginBottom: '0', padding: '16px 20px', border: '0.5px solid rgba(0,0,0,0.12)', borderRadius: '12px', backgroundColor: 'white', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
        <h2 style={{ fontSize: '14px', fontWeight: 600, color: '#1a1a1a', margin: 0 }}>
          Governance Template
        </h2>
        <div style={{ display: 'flex', gap: '6px' }}>
          <button
            onClick={handleViewTemplate}
            disabled={!selectedTemplateId}
            style={{
              padding: '5px 10px',
              borderRadius: '6px',
              border: '0.5px solid rgba(0,0,0,0.15)',
              backgroundColor: selectedTemplateId ? 'white' : '#f9f9f9',
              color: selectedTemplateId ? '#1a1a1a' : '#b0b0b0',
              fontSize: '12px',
              cursor: selectedTemplateId ? 'pointer' : 'not-allowed',
            }}
          >
            View
          </button>
          <button
            onClick={handleSaveAsTemplate}
            style={{
              padding: '5px 10px',
              borderRadius: '6px',
              border: '0.5px solid rgba(0,0,0,0.15)',
              backgroundColor: 'white',
              color: '#1a1a1a',
              fontSize: '12px',
              cursor: 'pointer',
            }}
          >
            Save as Template
          </button>
          <button
            onClick={handleManageTemplates}
            style={{
              padding: '5px 10px',
              borderRadius: '6px',
              border: '0.5px solid rgba(0,0,0,0.15)',
              backgroundColor: 'white',
              color: '#1a1a1a',
              fontSize: '12px',
              cursor: 'pointer',
            }}
          >
            Manage
          </button>
        </div>
      </div>
      <p style={{ fontSize: '12.5px', color: '#6b6b6b', marginBottom: '10px' }}>
        Apply client-specific naming conventions, governance rules, and security policies to all generated outputs.
      </p>
      {loading ? (
        <div style={{ padding: '12px', textAlign: 'center', color: '#6b6b6b' }}>
          Loading templates...
        </div>
      ) : (
        <>
          <select
            value={selectedTemplateId || ''}
            onChange={handleChange}
            style={{
              width: '100%',
              padding: '10px 12px',
              borderRadius: '8px',
              border: '0.5px solid rgba(0,0,0,0.15)',
              fontSize: '13.5px',
              fontFamily: 'inherit',
              color: '#374151',
              backgroundColor: 'white',
              outline: 'none',
            }}
          >
            <option value="">No template (use requirements only)</option>
            {templates.map(template => (
              <option key={template.id} value={template.id}>
                {template.name} {template.is_default ? '(Default)' : ''} {template.is_company_default ? '(Company Default)' : ''}
              </option>
            ))}
          </select>
          {selectedTemplateId && (() => {
            const t = templates.find(x => x.id === selectedTemplateId);
            if (!t) return null;
            return (
              <div style={{ marginTop: '10px', padding: '10px 12px', borderRadius: '8px', backgroundColor: '#F0EFFF', border: '1px solid #D9D6FE', fontSize: '12px', color: '#4338CA' }}>
                <strong>✓ Template active:</strong> {t.name}
                {t.description && <span style={{ color: '#6366F1' }}> — {t.description}</span>}
                <div style={{ marginTop: '4px', color: '#6b6b6b', fontSize: '11px' }}>
                  Governance rules, naming conventions, and security policies will be applied to all generated outputs.
                </div>
              </div>
            );
          })()}
        </>
      )}

      {/* Save as Template modal */}
      <TemplateEditor
        isOpen={isEditorOpen}
        onClose={() => { setIsEditorOpen(false); setEditorTemplate(null); }}
        template={editorTemplate}
        onSave={handleEditorSaved}
      />

      {/* Manage Templates modal */}
      <TemplateManager
        isOpen={isManagerOpen}
        onClose={() => setIsManagerOpen(false)}
      />

      {/* View Template modal */}
      {viewingTemplate && (
        <div
          style={{
            position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100,
          }}
          onClick={() => setViewingTemplate(null)}
        >
          <div
            style={{
              backgroundColor: 'white', borderRadius: '12px', padding: '24px',
              width: '90%', maxWidth: '720px', maxHeight: '80vh',
              display: 'flex', flexDirection: 'column',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <h2 style={{ fontSize: '16px', fontWeight: 600, color: '#1a1a1a', margin: 0 }}>
                  {viewingTemplate.name}
                </h2>
                {viewingTemplate.description && (
                  <p style={{ fontSize: '12.5px', color: '#6b6b6b', marginTop: '4px' }}>
                    {viewingTemplate.description}
                  </p>
                )}
              </div>
              <button
                onClick={() => setViewingTemplate(null)}
                style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer', color: '#9b9b9b', padding: '4px' }}
              >
                ×
              </button>
            </div>
            <pre style={{
              flex: 1, overflowY: 'auto', padding: '16px',
              backgroundColor: '#F9FAFB', borderRadius: '8px',
              border: '0.5px solid rgba(0,0,0,0.1)',
              fontSize: '12.5px', lineHeight: 1.6, color: '#374151',
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              fontFamily: 'inherit', margin: 0,
            }}>
              {viewingTemplate.content}
            </pre>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '16px' }}>
              <button
                onClick={() => setViewingTemplate(null)}
                style={{
                  padding: '8px 20px', borderRadius: '8px',
                  border: '0.5px solid rgba(0,0,0,0.15)',
                  backgroundColor: 'white', color: '#1a1a1a',
                  fontSize: '13px', fontWeight: 500, cursor: 'pointer',
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
