/**
 * ExtractedServices — displays AI-detected architecture components.
 *
 * PURPOSE:
 *   After vision analysis, shows each detected cloud resource (EC2, S3,
 *   etc.) with its type, provider, confidence score, and any detected labels.
 *   While analysis is running, a skeleton shimmer grid is shown instead.
 *
 * WHY IT EXISTS:
 *   This is the primary feedback UI for the AI vision step. Users can
 *   verify that the diagram was understood correctly before proceeding
 *   to design document generation.
 *
 * CONNECTIONS:
 *   • workflowStore.ts → contextPack (vision result), isAnalyzing flag
 *   • UploadPage.tsx   → conditionally renders this below the file preview
 */

// 🟢 BEGINNER: Import the global store to read the AI vision analysis results.
import { useWorkflowStore } from '../../store/workflowStore';

// 🟢 BEGINNER: Local TypeScript interface describing a detected cloud service.
interface Service {
  name: string;          // 🟢 BEGINNER: Human-readable name, e.g. "Web Server".
  service_type: string;   // 🟢 BEGINNER: Cloud service type, e.g. "EC2", "S3".
  provider: string;       // 🟢 BEGINNER: "aws" or "azure".
  confidence: number;     // 🟢 BEGINNER: AI confidence score from 0.0 to 1.0.
  ports?: string[];      // 🟢 BEGINNER: Optional list of open ports.
  labels?: string[];     // 🟢 BEGINNER: Optional tags/labels detected in the diagram.
}

// 🟢 BEGINNER: A placeholder shimmer card shown while the AI is still analyzing the diagram.
// It uses empty gray divs with animation to create a "loading skeleton" effect.
const SkeletonCard = () => (
  <div className="bg-white border border-gray-100 rounded-xl p-5 animate-shimmer">
    <div className="h-5 bg-gray-200 rounded w-2/3 mb-3" />
    <div className="h-4 bg-gray-200 rounded w-1/2 mb-2" />
    <div className="h-4 bg-gray-200 rounded w-1/3" />
  </div>
);

// 🟢 BEGINNER: Displays the AI-detected cloud services after vision analysis.
// While analysis is running, it shows skeleton placeholders instead.
export const ExtractedServices = () => {
  // 🟢 BEGINNER: Read the vision result (contextPack) and analyzing flag from the global store.
  const { contextPack, isAnalyzing } = useWorkflowStore();

  // 🟢 BEGINNER: If the backend is still analyzing, show 6 skeleton cards as placeholders.
  if (isAnalyzing) {
    return (
      <div className="mb-8 animate-fade-in">
        <div className="flex items-center gap-3 mb-4">
          <div className="h-6 bg-gray-200 rounded w-48 animate-shimmer" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* 🟢 BEGINNER: Array.from({ length: 6 }) creates an array of 6 empty items so we can render 6 skeletons. */}
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </div>
    );
  }

  // 🟢 BEGINNER: If no services were detected, render nothing (return null).
  if (!contextPack || !contextPack.components || contextPack.components.length === 0) {
    return null;
  }

  // 🟢 BEGINNER: Pull out the components array and the primary provider for easier use below.
  const components = contextPack.components;
  const primaryProvider = contextPack.primary_provider || 'aws';

  return (
    <div className="mb-8 animate-slide-up">
      {/* 🟢 BEGINNER: Section header with provider badge. */}
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-2xl font-bold text-gray-800">Extracted Services</h2>
        <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-blue-100 text-blue-800 animate-scale-in">
          {primaryProvider.toUpperCase()}
        </span>
      </div>

      {/* 🟢 BEGINNER: Responsive grid: 1 column on mobile, 2 on tablet, 3 on desktop. */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 animate-stagger">
        {components.map((component: Service, index: number) => (
          <div
            key={index}
            className="group bg-white border border-gray-200 rounded-xl p-5
              hover:border-orange-300 hover:shadow-lg hover:shadow-orange-100 hover:-translate-y-0.5
              transition-all duration-300 ease-out"
          >
            {/* 🟢 BEGINNER: Card header — service name and confidence badge. */}
            <div className="flex items-start justify-between mb-3">
              <h3 className="font-semibold text-gray-900 text-lg group-hover:text-orange-600 transition-colors">
                {component.name}
              </h3>
              {/* 🟢 BEGINNER: Color-coded confidence badge: green >= 85%, yellow >= 65%, red below. */}
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                component.confidence >= 0.85
                  ? 'bg-green-100 text-green-700'
                  : component.confidence >= 0.65
                  ? 'bg-yellow-100 text-yellow-700'
                  : 'bg-red-100 text-red-700'
              }`}>
                {(component.confidence * 100).toFixed(0)}%
              </span>
            </div>

            {/* 🟢 BEGINNER: Card body — service type, provider, ports, labels. */}
            <div className="space-y-2">
              <div className="flex items-center text-sm text-gray-600">
                <span className="font-medium mr-2">Type:</span>
                <span className="px-2 py-0.5 bg-gray-100 rounded-md text-xs font-medium text-gray-700">
                  {component.service_type}
                </span>
              </div>

              <div className="flex items-center text-sm text-gray-600">
                <span className="font-medium mr-2">Provider:</span>
                <span className="px-2 py-0.5 bg-blue-50 rounded-md text-xs font-medium text-blue-700">
                  {component.provider.toUpperCase()}
                </span>
              </div>

              {/* 🟢 BEGINNER: Only show ports row if the AI detected any ports for this service. */}
              {component.ports && component.ports.length > 0 && (
                <div className="flex items-center text-sm text-gray-600">
                  <span className="font-medium mr-2">Ports:</span>
                  <span className="text-xs font-mono bg-gray-50 px-1.5 py-0.5 rounded">
                    {component.ports.join(', ')}
                  </span>
                </div>
              )}

              {/* 🟢 BEGINNER: Only show labels if the AI detected any tags/labels. */}
              {component.labels && component.labels.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2 pt-2 border-t border-gray-100">
                  {component.labels.map((label: string, labelIndex: number) => (
                    <span
                      key={labelIndex}
                      className="px-2 py-0.5 bg-green-50 rounded-md text-xs font-medium text-green-700
                        hover:bg-green-100 transition-colors"
                    >
                      {label}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* 🟢 BEGINNER: Bottom summary bar showing total services and overall confidence with a progress bar. */}
      <div className="mt-5 p-4 bg-gradient-to-r from-gray-50 to-gray-100 rounded-xl border border-gray-200">
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-4">
            <span className="font-medium text-gray-700">
              Total Services: <span className="text-gray-900 font-bold">{components.length}</span>
            </span>
            <span className="text-gray-300">|</span>
            <span className="font-medium text-gray-700">
              Confidence: <span className="text-gray-900 font-bold">{(contextPack.overall_confidence * 100).toFixed(0)}%</span>
            </span>
          </div>
          {/* 🟢 BEGINNER: A simple progress bar whose width matches the overall confidence percentage. */}
          <div className="w-32 h-2 bg-gray-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-orange-400 to-orange-500 rounded-full transition-all duration-700 ease-out"
              style={{ width: `${contextPack.overall_confidence * 100}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
