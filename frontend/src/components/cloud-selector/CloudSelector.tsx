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

// 🟢 BEGINNER: Import the global Zustand store to read/write which provider is selected.
import { useWorkflowStore } from '../../store/workflowStore';
// 🟢 BEGINNER: Import the child CloudCard component that renders each individual provider card.
import { CloudCard } from './CloudCard';
// 🟢 BEGINNER: Import the TypeScript type for a cloud provider object.
import { CloudProvider } from '../../types/schema';

// 🟢 BEGINNER: Hardcoded list of available cloud providers. In the future this could come from an API.
const DEFAULT_PROVIDERS: CloudProvider[] = [
  { id: 'aws', name: 'AWS', fullName: 'Amazon Web Services', services: ['EC2', 'S3', 'RDS', 'VPC'], selected: false },
  { id: 'azure', name: 'Azure', fullName: 'Microsoft Azure', services: ['VM', 'Storage', 'SQL', 'VNet'], selected: false },
  { id: 'gcp', name: 'GCP', fullName: 'Google Cloud Platform', services: ['GCE', 'GCS', 'Cloud SQL', 'VPC'], selected: false },
];

// 🟢 BEGINNER: Parent component that renders a grid of provider cards.
// It knows which provider is selected (from the global store) and passes that state down to each CloudCard.
export const CloudSelector = () => {
  // 🟢 BEGINNER: selectedProvider = the ID string of the currently chosen provider ("aws" or null).
  // setSelectedProvider = a function from the store that updates the selection when a card is clicked.
  const { selectedProvider, setSelectedProvider } = useWorkflowStore();

  return (
    <div style={{ marginBottom: '16px' }}>
      {/* 🟢 BEGINNER: Section label above the cards. */}
      <div style={{ fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.07em', color: '#9b9b9b', marginBottom: '12px' }}>
        GENERATE DESIGN DOC FOR
      </div>
      {/* 🟢 BEGINNER: CSS Grid with 3 equal columns and 12px gap between cards. */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
        {/* 🟢 BEGINNER: Loop over DEFAULT_PROVIDERS and render a CloudCard for each one. */}
        {DEFAULT_PROVIDERS.map((provider: CloudProvider) => (
          <CloudCard
            key={provider.id}                        // 🟢 BEGINNER: React needs a unique key for each item in a list.
            provider={provider}                        // 🟢 BEGINNER: Pass the provider data object down to the card.
            isSelected={selectedProvider === provider.id} // 🟢 BEGINNER: True if this provider matches the global selection.
            onSelect={setSelectedProvider}             // 🟢 BEGINNER: Pass the store setter so the card can update selection.
          />
        ))}
      </div>
    </div>
  );
};
