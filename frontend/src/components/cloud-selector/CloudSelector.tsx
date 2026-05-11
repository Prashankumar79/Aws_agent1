import { useWorkflowStore } from '../../store/workflowStore';
import { CloudCard } from './CloudCard';
import { CloudProvider } from '../../types/schema';

const DEFAULT_PROVIDERS: CloudProvider[] = [
  { id: 'aws', name: 'AWS', fullName: 'Amazon Web Services', services: ['EC2', 'S3', 'RDS', 'VPC'], selected: false },
  { id: 'azure', name: 'Azure', fullName: 'Microsoft Azure', services: ['VM', 'Storage', 'SQL', 'VNet'], selected: false },
];

export const CloudSelector = () => {
  const { selectedProvider, setSelectedProvider } = useWorkflowStore();

  return (
    <div style={{ marginBottom: '16px' }}>
      <div style={{ fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.07em', color: '#9b9b9b', marginBottom: '12px' }}>
        GENERATE DESIGN DOC FOR
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
        {DEFAULT_PROVIDERS.map((provider: CloudProvider) => (
          <CloudCard
            key={provider.id}
            provider={provider}
            isSelected={selectedProvider === provider.id}
            onSelect={setSelectedProvider}
          />
        ))}
      </div>
    </div>
  );
};
