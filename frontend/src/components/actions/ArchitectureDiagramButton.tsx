/**
 * ArchitectureDiagramButton — opens a diagram type selector popup,
 * then generates the selected architecture diagram.
 */

import { useState } from 'react';
import { useWorkflowStore } from '../../store/workflowStore';
import { api } from '../../services/api';

// ── Diagram type definitions ──────────────────────────────────────────────────
interface DiagramOption {
  id: string;
  label: string;
  description: string;
  icon: string;
  color: string;       // accent color
  bgColor: string;     // card background
  borderColor: string; // card border
  category: 'core' | 'infrastructure' | 'migration' | 'modern';
  autoDetectKeywords: string[]; // keywords in document that suggest this type
}

const DIAGRAM_OPTIONS: DiagramOption[] = [
  // ── Core ──────────────────────────────────────────────────────────────────
  {
    id: 'hld',
    label: 'High-Level Design',
    description: 'Architecture overview — components, integrations, security zones, HA/DR',
    icon: 'ti-layout-dashboard',
    color: '#5B4EE8', bgColor: '#F5F3FF', borderColor: '#C7C3F9',
    category: 'core',
    autoDetectKeywords: ['architecture', 'overview', 'hld', 'high level', 'components'],
  },
  {
    id: 'lld',
    label: 'Low-Level Design',
    description: 'Implementation details — CIDRs, IAM roles, port mappings, storage config',
    icon: 'ti-code',
    color: '#0369A1', bgColor: '#E0F2FE', borderColor: '#7DD3FC',
    category: 'core',
    autoDetectKeywords: ['subnet', 'cidr', 'iam', 'port', 'lld', 'low level', 'terraform'],
  },
  {
    id: 'as_is',
    label: 'Current State (As-Is)',
    description: 'Existing on-prem infrastructure — servers, apps, databases, dependencies',
    icon: 'ti-building',
    color: '#92400E', bgColor: '#FEF3C7', borderColor: '#FCD34D',
    category: 'core',
    autoDetectKeywords: ['on-prem', 'current', 'existing', 'as-is', 'legacy', 'data center'],
  },
  // ── Infrastructure ────────────────────────────────────────────────────────
  {
    id: 'network',
    label: 'Network Architecture',
    description: 'VPC/VNet, peering, Transit Gateway, firewall rules, DNS, VPN',
    icon: 'ti-network',
    color: '#7C3AED', bgColor: '#EDE9FE', borderColor: '#C4B5FD',
    category: 'infrastructure',
    autoDetectKeywords: ['vpc', 'vnet', 'subnet', 'network', 'firewall', 'dns', 'vpn', 'peering'],
  },
  {
    id: 'security',
    label: 'Security Architecture',
    description: 'IAM, RBAC, encryption, secrets, WAF, SIEM, compliance controls',
    icon: 'ti-shield-lock',
    color: '#B91C1C', bgColor: '#FEF2F2', borderColor: '#FCA5A5',
    category: 'infrastructure',
    autoDetectKeywords: ['iam', 'security', 'encryption', 'kms', 'waf', 'compliance', 'pci', 'hipaa'],
  },
  {
    id: 'dr',
    label: 'Disaster Recovery',
    description: 'Multi-region failover, RTO/RPO, backup retention, replication',
    icon: 'ti-refresh-alert',
    color: '#C2410C', bgColor: '#FFF7ED', borderColor: '#FDBA74',
    category: 'infrastructure',
    autoDetectKeywords: ['dr', 'disaster', 'recovery', 'rto', 'rpo', 'failover', 'backup', 'replication'],
  },
  {
    id: 'landing_zone',
    label: 'Landing Zone',
    description: 'Multi-account strategy, SCPs, guardrails, identity federation, logging',
    icon: 'ti-building-skyscraper',
    color: '#0F766E', bgColor: '#F0FDFA', borderColor: '#5EEAD4',
    category: 'infrastructure',
    autoDetectKeywords: ['landing zone', 'multi-account', 'scp', 'guardrail', 'organization', 'ou'],
  },
  // ── Migration ─────────────────────────────────────────────────────────────
  {
    id: 'migration_wave',
    label: 'Migration Wave Plan',
    description: 'App grouping, migration batches, dependencies, timelines',
    icon: 'ti-wave-sine',
    color: '#1D4ED8', bgColor: '#EFF6FF', borderColor: '#93C5FD',
    category: 'migration',
    autoDetectKeywords: ['wave', 'migration', 'batch', 'phase', 'cutover', 'timeline'],
  },
  {
    id: 'data_flow',
    label: 'Data Flow Design',
    description: 'ETL pipelines, replication paths, streaming architecture, CDC',
    icon: 'ti-arrows-right-left',
    color: '#047857', bgColor: '#ECFDF5', borderColor: '#6EE7B7',
    category: 'migration',
    autoDetectKeywords: ['data flow', 'etl', 'pipeline', 'streaming', 'kafka', 'kinesis', 'cdc'],
  },
  // ── Modern ────────────────────────────────────────────────────────────────
  {
    id: 'cicd',
    label: 'CI/CD Architecture',
    description: 'Pipelines, GitOps, artifact registry, deployment strategy, rollback',
    icon: 'ti-git-branch',
    color: '#6D28D9', bgColor: '#F5F3FF', borderColor: '#DDD6FE',
    category: 'modern',
    autoDetectKeywords: ['cicd', 'ci/cd', 'pipeline', 'jenkins', 'github actions', 'argocd', 'gitops'],
  },
  {
    id: 'kubernetes',
    label: 'Kubernetes / Container',
    description: 'Cluster design, node pools, ingress, autoscaling, service mesh',
    icon: 'ti-brand-docker',
    color: '#0369A1', bgColor: '#F0F9FF', borderColor: '#BAE6FD',
    category: 'modern',
    autoDetectKeywords: ['kubernetes', 'k8s', 'eks', 'aks', 'gke', 'container', 'docker', 'helm'],
  },
  {
    id: 'observability',
    label: 'Observability',
    description: 'Monitoring, tracing, logging, alerting, dashboards (Grafana, Prometheus)',
    icon: 'ti-chart-line',
    color: '#0F766E', bgColor: '#F0FDFA', borderColor: '#5EEAD4',
    category: 'modern',
    autoDetectKeywords: ['monitoring', 'observability', 'cloudwatch', 'grafana', 'prometheus', 'logging', 'tracing'],
  },
];

const CATEGORY_LABELS: Record<string, string> = {
  core: 'Core Documents',
  infrastructure: 'Infrastructure',
  migration: 'Migration-Specific',
  modern: 'Modern / DevOps',
};

// ── Auto-detect which types are relevant from document text ──────────────────
function autoDetectTypes(filename: string): Set<string> {
  const text = filename.toLowerCase();
  const detected = new Set<string>();
  for (const opt of DIAGRAM_OPTIONS) {
    if (opt.autoDetectKeywords.some(kw => text.includes(kw))) {
      detected.add(opt.id);
    }
  }
  // Always suggest HLD as default
  detected.add('hld');
  return detected;
}

// ── Component ─────────────────────────────────────────────────────────────────
export const ArchitectureDiagramButton = () => {
  const { uploadedFileObject, selectedProvider, setArchitectureJobId, setArchitectureGraph, setArchitectureXml } = useWorkflowStore();

  const [showPopup, setShowPopup] = useState(false);
  const [selectedType, setSelectedType] = useState<string>('hld');
  const [isGenerating, setIsGenerating] = useState(false);
  const [progressLabel, setProgressLabel] = useState('');
  const [progressValue, setProgressValue] = useState(0);

  // Custom instruction state
  const [showCustomBox, setShowCustomBox] = useState(false);
  const [customInstruction, setCustomInstruction] = useState('');

  // To-Be state
  const [toBeCloud, setToBeCloud] = useState<string>('aws');

  const handleOpenPopup = () => {
    if (!uploadedFileObject || !selectedProvider) {
      alert('Please upload a file and select a cloud provider first.');
      return;
    }
    const detected = autoDetectTypes(uploadedFileObject.name);
    const first = Array.from(detected)[0] || 'hld';
    setSelectedType(first);
    setShowCustomBox(false);
    setCustomInstruction('');
    setShowPopup(true);
  };

  const handleTypeSelect = (id: string) => {
    setSelectedType(id);
    setShowCustomBox(id === 'custom');
  };

  const handleGenerate = async () => {
    if (!uploadedFileObject || !selectedProvider) return;
    if (selectedType === 'custom' && !customInstruction.trim()) {
      alert('Please enter your custom instruction.');
      return;
    }

    // Debug: log what's being sent
    console.info('[Architecture Diagram] Generating:', {
      selectedType,
      toBeCloud: selectedType === 'to_be' ? toBeCloud : '(n/a)',
      customInstruction: selectedType === 'custom' ? customInstruction.slice(0, 50) : '(n/a)',
      provider: selectedProvider,
    });

    setShowPopup(false);
    setIsGenerating(true);
    setProgressValue(0);

    const typeLabel = selectedType === 'custom'
      ? 'Custom Diagram'
      : selectedType === 'to_be'
      ? `To-Be (${toBeCloud.toUpperCase()})`
      : DIAGRAM_OPTIONS.find(o => o.id === selectedType)?.label || selectedType;
    setProgressLabel(`Generating ${typeLabel}...`);

    try {
      const result = await api.generateArchitectureDiagram(
        uploadedFileObject,
        selectedProvider,
        (job) => {
          setProgressValue(job.progress || 0);
          setProgressLabel(job.pipeline_stage || 'Working...');
        },
        selectedType,
        selectedType === 'custom' ? customInstruction : '',
        selectedType === 'to_be' ? toBeCloud : '',
      );

      setArchitectureJobId(result.job_id);
      setArchitectureGraph(result.graph);
      setArchitectureXml(result.drawio_xml);
      sessionStorage.setItem('architectureJobId', result.job_id);
      window.history.pushState({}, '', `/architecture-studio?job_id=${encodeURIComponent(result.job_id)}`);
      window.dispatchEvent(new PopStateEvent('popstate'));
    } catch (error) {
      alert('Architecture diagram generation failed: ' + (error instanceof Error ? error.message : 'Unknown error'));
    } finally {
      setIsGenerating(false);
      setProgressLabel('');
      setProgressValue(0);
    }
  };

  const categories = ['core', 'infrastructure', 'migration', 'modern'] as const;

  const CLOUD_OPTIONS = [
    { id: 'aws', label: 'AWS', color: '#E8A020', bg: '#FAEEDA' },
    { id: 'azure', label: 'Azure', color: '#0078D4', bg: '#E8F4FD' },
    { id: 'gcp', label: 'GCP', color: '#34A853', bg: '#E8F5E9' },
  ];

  return (
    <>
      {/* ── Trigger button ── */}
      <button
        onClick={handleOpenPopup}
        disabled={isGenerating}
        style={{
          backgroundColor: 'transparent',
          border: '0.5px solid rgba(0,0,0,0.28)',
          borderRadius: '8px',
          fontSize: '13px',
          padding: '13px 16px',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          transition: 'background-color 0.2s ease',
          width: '100%',
          justifyContent: 'center',
          opacity: isGenerating ? 0.4 : 1,
          pointerEvents: isGenerating ? 'none' : 'auto',
        }}
        onMouseEnter={(e) => { if (!isGenerating) e.currentTarget.style.backgroundColor = '#F5F3EE'; }}
        onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
      >
        <svg style={{ width: '14px', height: '14px' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
        </svg>
        {isGenerating ? 'Generating Diagram...' : 'Generate Architecture Diagram'}
      </button>
      <div style={{ textAlign: 'center', marginTop: '8px' }}>
        <span style={{ fontSize: '12px', color: '#9b9b9b' }}>
          {isGenerating ? `${progressValue}% · ${progressLabel}` : 'Creates an editable diagram from your uploaded document'}
        </span>
      </div>

      {/* ── Generating overlay ── */}
      {isGenerating && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 1500,
          backgroundColor: 'rgba(255,255,255,0.88)',
          backdropFilter: 'blur(4px)',
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
        }}>
          {/* Spinner */}
          <div style={{
            width: '56px', height: '56px', borderRadius: '50%',
            border: '3px solid #EEEDFE', borderTopColor: '#5B4EE8',
            animation: 'spin 0.8s linear infinite',
            marginBottom: '24px',
          }} />

          <div style={{ fontSize: '18px', fontWeight: 600, color: '#1a1a1a', marginBottom: '6px' }}>
            Generating Architecture Diagram
          </div>
          <div style={{ fontSize: '13px', color: '#6b6b6b', marginBottom: '24px', maxWidth: '400px', textAlign: 'center' }}>
            {progressLabel || 'Starting pipeline…'}
          </div>

          {/* Progress bar */}
          <div style={{ width: '320px', height: '6px', backgroundColor: '#E5E7EB', borderRadius: '3px', overflow: 'hidden', marginBottom: '16px' }}>
            <div style={{
              height: '100%', borderRadius: '3px',
              backgroundColor: '#5B4EE8',
              width: `${progressValue}%`,
              transition: 'width 0.8s ease',
            }} />
          </div>
          <div style={{ fontSize: '12px', color: '#9b9b9b' }}>{progressValue}% complete</div>

          {/* Stage pills */}
          <div style={{ display: 'flex', gap: '8px', marginTop: '20px', flexWrap: 'wrap', justifyContent: 'center', maxWidth: '500px' }}>
            {[
              { label: 'Parse Document', threshold: 25 },
              { label: 'Analyse Content', threshold: 45 },
              { label: 'Generate Diagram', threshold: 83 },
              { label: 'Validate XML', threshold: 90 },
              { label: 'Ready', threshold: 100 },
            ].map(({ label, threshold }) => {
              const done = progressValue >= threshold;
              const active = progressValue >= threshold - 20 && progressValue < threshold;
              return (
                <span key={label} style={{
                  padding: '4px 12px', borderRadius: '20px', fontSize: '11.5px', fontWeight: 500,
                  backgroundColor: done ? '#EEEDFE' : active ? '#F5F3FF' : '#F3F4F6',
                  color: done ? '#5B4EE8' : active ? '#7C6FF0' : '#9CA3AF',
                  border: `1px solid ${done ? '#C7C3F9' : active ? '#DDD6FE' : '#E5E7EB'}`,
                  transition: 'all 0.3s ease',
                }}>
                  {done ? '✓ ' : ''}{label}
                </span>
              );
            })}
          </div>

          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      )}

      {/* ── Diagram Type Selector Popup ── */}
      {showPopup && (
        <div
          style={{
            position: 'fixed', inset: 0, zIndex: 2000,
            backgroundColor: 'rgba(0,0,0,0.55)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '16px',
          }}
          onClick={() => setShowPopup(false)}
        >
          <div
            style={{
              backgroundColor: 'white',
              borderRadius: '16px',
              width: '100%',
              maxWidth: '860px',
              maxHeight: '88vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '0 24px 64px rgba(0,0,0,0.2)',
              overflow: 'hidden',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div style={{
              padding: '20px 24px 16px',
              borderBottom: '0.5px solid rgba(0,0,0,0.08)',
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              flexShrink: 0,
            }}>
              <div>
                <h2 style={{ fontSize: '18px', fontWeight: 600, color: '#1a1a1a', margin: 0 }}>
                  Select Diagram Type
                </h2>
                <p style={{ fontSize: '13px', color: '#6b6b6b', marginTop: '4px' }}>
                  Choose which architecture diagram to generate from your document.
                  {uploadedFileObject && (
                    <span style={{ color: '#5B4EE8', fontWeight: 500 }}>
                      {' '}Auto-detected from: {uploadedFileObject.name}
                    </span>
                  )}
                </p>
              </div>
              <button
                onClick={() => setShowPopup(false)}
                style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer', color: '#9b9b9b', padding: '4px', lineHeight: 1 }}
              >
                ×
              </button>
            </div>

            {/* Scrollable content */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '16px 24px' }}>

              {/* ── Special: Custom Instruction ── */}
              <div style={{ marginBottom: '20px' }}>
                <div style={{ fontSize: '11px', fontWeight: 600, color: '#9b9b9b', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: '10px' }}>
                  Custom
                </div>
                <div
                  onClick={() => handleTypeSelect('custom')}
                  style={{
                    padding: '14px 16px',
                    borderRadius: '10px',
                    border: selectedType === 'custom' ? '2px solid #5B4EE8' : '1.5px solid rgba(0,0,0,0.08)',
                    backgroundColor: selectedType === 'custom' ? '#F5F3FF' : 'white',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                    display: 'flex', alignItems: 'flex-start', gap: '12px',
                  }}
                >
                  <div style={{
                    width: '36px', height: '36px', borderRadius: '8px', flexShrink: 0,
                    backgroundColor: selectedType === 'custom' ? '#5B4EE8' : '#F3F4F6',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <i className="ti ti-pencil" style={{ fontSize: '18px', color: selectedType === 'custom' ? 'white' : '#6B7280' }} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '13.5px', fontWeight: 600, color: selectedType === 'custom' ? '#5B4EE8' : '#1a1a1a', marginBottom: '2px' }}>
                      Custom Instruction
                    </div>
                    <div style={{ fontSize: '12px', color: '#6b6b6b' }}>
                      Describe exactly what diagram you want — any architecture, any style
                    </div>
                    {selectedType === 'custom' && (
                      <textarea
                        value={customInstruction}
                        onChange={(e) => { e.stopPropagation(); setCustomInstruction(e.target.value); }}
                        onClick={(e) => e.stopPropagation()}
                        placeholder="e.g. Create a 3-tier banking app on Azure with Application Gateway, VMSS in private subnets, Azure SQL with read replicas, Key Vault, and Azure Monitor. Include PCI-DSS compliance zones."
                        style={{
                          marginTop: '10px', width: '100%', minHeight: '80px',
                          padding: '10px 12px', borderRadius: '8px',
                          border: '1px solid #C7C3F9', fontSize: '13px',
                          fontFamily: 'inherit', resize: 'vertical', outline: 'none',
                          backgroundColor: 'white', color: '#374151', lineHeight: 1.5,
                        }}
                      />
                    )}
                  </div>
                </div>
              </div>

              {/* ── Special: To-Be Migration ── */}
              <div style={{ marginBottom: '20px' }}>
                <div style={{ fontSize: '11px', fontWeight: 600, color: '#9b9b9b', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: '10px' }}>
                  Migration
                </div>
                <div
                  onClick={() => handleTypeSelect('to_be')}
                  style={{
                    padding: '14px 16px',
                    borderRadius: '10px',
                    border: selectedType === 'to_be' ? '2px solid #047857' : '1.5px solid rgba(0,0,0,0.08)',
                    backgroundColor: selectedType === 'to_be' ? '#ECFDF5' : 'white',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                    display: 'flex', alignItems: 'flex-start', gap: '12px',
                  }}
                >
                  <div style={{
                    width: '36px', height: '36px', borderRadius: '8px', flexShrink: 0,
                    backgroundColor: selectedType === 'to_be' ? '#047857' : '#F3F4F6',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <i className="ti ti-arrows-exchange" style={{ fontSize: '18px', color: selectedType === 'to_be' ? 'white' : '#6B7280' }} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
                      <span style={{ fontSize: '13.5px', fontWeight: 600, color: selectedType === 'to_be' ? '#047857' : '#1a1a1a' }}>
                        Future State (To-Be)
                      </span>
                      <span style={{ padding: '1px 8px', borderRadius: '10px', backgroundColor: '#D1FAE5', color: '#065F46', fontSize: '10px', fontWeight: 600 }}>
                        Migration
                      </span>
                    </div>
                    <div style={{ fontSize: '12px', color: '#6b6b6b' }}>
                      Convert your current architecture to a target cloud — shows migration mapping
                    </div>
                    {selectedType === 'to_be' && (
                      <div style={{ marginTop: '12px' }} onClick={(e) => e.stopPropagation()}>
                        <div style={{ fontSize: '12px', fontWeight: 500, color: '#374151', marginBottom: '8px' }}>
                          Target Cloud Platform:
                        </div>
                        <div style={{ display: 'flex', gap: '8px' }}>
                          {CLOUD_OPTIONS.map(cloud => (
                            <button
                              key={cloud.id}
                              onClick={(e) => { e.stopPropagation(); setToBeCloud(cloud.id); }}
                              style={{
                                padding: '8px 16px', borderRadius: '8px', cursor: 'pointer',
                                border: toBeCloud === cloud.id ? `2px solid ${cloud.color}` : '1.5px solid rgba(0,0,0,0.12)',
                                backgroundColor: toBeCloud === cloud.id ? cloud.bg : 'white',
                                color: toBeCloud === cloud.id ? cloud.color : '#374151',
                                fontSize: '13px', fontWeight: 600,
                                transition: 'all 0.15s ease',
                              }}
                            >
                              {cloud.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* ── Standard diagram types ── */}
              <div style={{
                opacity: (selectedType === 'custom' || selectedType === 'to_be') ? 0.5 : 1,
                transition: 'opacity 0.2s ease',
              }}>
              {categories.map(cat => {
                const opts = DIAGRAM_OPTIONS.filter(o => o.category === cat);
                return (
                  <div key={cat} style={{ marginBottom: '20px' }}>
                    <div style={{
                      fontSize: '11px', fontWeight: 600, color: '#9b9b9b',
                      textTransform: 'uppercase', letterSpacing: '0.07em',
                      marginBottom: '10px',
                    }}>
                      {CATEGORY_LABELS[cat]}
                    </div>
                    <div style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
                      gap: '8px',
                    }}>
                      {opts.map(opt => {
                        const isSelected = selectedType === opt.id;
                        return (
                          <div
                            key={opt.id}
                            onClick={() => handleTypeSelect(opt.id)}
                            style={{
                              padding: '12px 14px',
                              borderRadius: '10px',
                              border: isSelected
                                ? `2px solid ${opt.borderColor}`
                                : '1.5px solid rgba(0,0,0,0.08)',
                              backgroundColor: isSelected ? opt.bgColor : 'white',
                              cursor: 'pointer',
                              transition: 'all 0.15s ease',
                              display: 'flex',
                              alignItems: 'flex-start',
                              gap: '10px',
                              position: 'relative',
                            }}
                            onMouseEnter={(e) => {
                              if (!isSelected) e.currentTarget.style.borderColor = opt.borderColor;
                            }}
                            onMouseLeave={(e) => {
                              if (!isSelected) e.currentTarget.style.borderColor = 'rgba(0,0,0,0.08)';
                            }}
                          >
                            <div style={{
                              width: '32px', height: '32px', borderRadius: '8px',
                              backgroundColor: isSelected ? opt.color : '#F3F4F6',
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              flexShrink: 0, transition: 'background-color 0.15s ease',
                            }}>
                              <i className={`ti ${opt.icon}`} style={{ fontSize: '16px', color: isSelected ? 'white' : '#6B7280' }} />
                            </div>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ fontSize: '13px', fontWeight: 600, color: isSelected ? opt.color : '#1a1a1a', marginBottom: '2px' }}>
                                {opt.label}
                              </div>
                              <div style={{ fontSize: '11.5px', color: '#6b6b6b', lineHeight: 1.4 }}>
                                {opt.description}
                              </div>
                            </div>
                            {isSelected && (
                              <div style={{
                                position: 'absolute', top: '8px', right: '8px',
                                width: '18px', height: '18px', borderRadius: '50%',
                                backgroundColor: opt.color,
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                              }}>
                                <svg style={{ width: '10px', height: '10px' }} fill="none" viewBox="0 0 24 24" stroke="white">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                                </svg>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
              </div>
            </div>

            {/* Footer */}
            <div style={{
              padding: '14px 24px',
              borderTop: '0.5px solid rgba(0,0,0,0.08)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexShrink: 0,
              backgroundColor: '#FAFAFA',
            }}>
              <div style={{ fontSize: '13px', color: '#6b6b6b' }}>
                {(() => {
                  if (selectedType === 'custom') return <span>Custom instruction diagram</span>;
                  if (selectedType === 'to_be') return <span>To-Be → <strong style={{ color: CLOUD_OPTIONS.find(c => c.id === toBeCloud)?.color }}>{toBeCloud.toUpperCase()}</strong></span>;
                  const opt = DIAGRAM_OPTIONS.find(o => o.id === selectedType);
                  return opt ? <span>Selected: <span style={{ fontWeight: 500, color: opt.color }}>{opt.label}</span></span> : null;
                })()}
              </div>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  onClick={() => setShowPopup(false)}
                  style={{
                    padding: '9px 18px', borderRadius: '8px',
                    border: '0.5px solid rgba(0,0,0,0.15)',
                    backgroundColor: 'white', color: '#374151',
                    fontSize: '13px', fontWeight: 500, cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  onClick={handleGenerate}
                  style={{
                    padding: '9px 22px', borderRadius: '8px',
                    border: 'none',
                    backgroundColor: '#5B4EE8',
                    color: 'white',
                    fontSize: '13px', fontWeight: 500,
                    cursor: 'pointer',
                    display: 'flex', alignItems: 'center', gap: '6px',
                  }}
                >
                  <svg style={{ width: '14px', height: '14px' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  Generate {selectedType === 'custom' ? 'Custom Diagram' : selectedType === 'to_be' ? `To-Be (${toBeCloud.toUpperCase()})` : DIAGRAM_OPTIONS.find(o => o.id === selectedType)?.label || selectedType}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
