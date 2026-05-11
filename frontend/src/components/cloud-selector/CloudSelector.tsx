/**
 * CloudSelector — lets the user pick which cloud provider to target.
 *
 * PURPOSE:
 *   Renders a grid of cloud provider cards (AWS, Azure). The selected
 *   provider ID is written to the global workflow store and read by
 *   AnalyseButton when starting the pipeline.
 *
 * WHY IT EXISTS:
 *   Provider selection is a prerequisite step before analysis.
 *   Extracting it into its own component keeps UploadPage.tsx clean
 *   and allows the grid layout to evolve independently.
 *
 * CONNECTIONS:
 *   • workflowStore.ts   → selectedProvider / setSelectedProvider
 *   • CloudCard.tsx      → renders each provider card
 *   • AnalyseButton.tsx  → reads selectedProvider to start pipeline
 */

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
