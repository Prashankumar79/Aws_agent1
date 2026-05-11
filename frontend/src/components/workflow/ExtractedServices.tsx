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

import { useWorkflowStore } from '../../store/workflowStore';

interface Service {
  name: string;
  service_type: string;
  provider: string;
  confidence: number;
  ports?: string[];
  labels?: string[];
}

const SkeletonCard = () => (
  <div className="bg-white border border-gray-100 rounded-xl p-5 animate-shimmer">
    <div className="h-5 bg-gray-200 rounded w-2/3 mb-3" />
    <div className="h-4 bg-gray-200 rounded w-1/2 mb-2" />
    <div className="h-4 bg-gray-200 rounded w-1/3" />
  </div>
);

export const ExtractedServices = () => {
  const { contextPack, isAnalyzing } = useWorkflowStore();

  // Show skeleton while analyzing
  if (isAnalyzing) {
    return (
      <div className="mb-8 animate-fade-in">
        <div className="flex items-center gap-3 mb-4">
          <div className="h-6 bg-gray-200 rounded w-48 animate-shimmer" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (!contextPack || !contextPack.components || contextPack.components.length === 0) {
    return null;
  }

  const components = contextPack.components;
  const primaryProvider = contextPack.primary_provider || 'aws';

  return (
    <div className="mb-8 animate-slide-up">
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-2xl font-bold text-gray-800">Extracted Services</h2>
        <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-blue-100 text-blue-800 animate-scale-in">
          {primaryProvider.toUpperCase()}
        </span>
      </div>

      {/* Services Grid with stagger */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 animate-stagger">
        {components.map((component: Service, index: number) => (
          <div
            key={index}
            className="group bg-white border border-gray-200 rounded-xl p-5
              hover:border-orange-300 hover:shadow-lg hover:shadow-orange-100 hover:-translate-y-0.5
              transition-all duration-300 ease-out"
          >
            <div className="flex items-start justify-between mb-3">
              <h3 className="font-semibold text-gray-900 text-lg group-hover:text-orange-600 transition-colors">
                {component.name}
              </h3>
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

              {component.ports && component.ports.length > 0 && (
                <div className="flex items-center text-sm text-gray-600">
                  <span className="font-medium mr-2">Ports:</span>
                  <span className="text-xs font-mono bg-gray-50 px-1.5 py-0.5 rounded">
                    {component.ports.join(', ')}
                  </span>
                </div>
              )}

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

      {/* Summary bar */}
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
