/**
 * PromptRefinerModal — Modal for refining Terraform prompts using Haiku.
 *
 * PURPOSE:
 *   Provides a UI where users can type a rough prompt idea and get 3-5 refined
 *   suggestions from Haiku that include context from the diagram.
 *
 * CONNECTIONS:
 *   • api.ts → calls suggestTerraformPrompt()
 *   • TerraformChatPage.tsx → uses this modal for prompt refinement
 */

import { useState } from 'react';
import { api } from '../../services/api';

interface PromptRefinerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (suggestion: string) => void;
  cloudProvider: string;
  detectedResources: string[];
}

export const PromptRefinerModal = ({
  isOpen,
  onClose,
  onSelect,
  cloudProvider,
  detectedResources,
}: PromptRefinerModalProps) => {
  const [roughPrompt, setRoughPrompt] = useState('');
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  if (!isOpen) return null;

  const handleSuggest = async () => {
    if (!roughPrompt.trim()) return;

    setIsLoading(true);
    setSuggestions([]);
    try {
      const result = await api.suggestTerraformPrompt(
        roughPrompt,
        cloudProvider,
        detectedResources
      );
      setSuggestions(result);
    } catch (error) {
      console.error('[PromptRefinerModal] Failed to get suggestions:', error);
      alert('Failed to generate suggestions. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelect = (suggestion: string) => {
    onSelect(suggestion);
    onClose();
    setRoughPrompt('');
    setSuggestions([]);
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          backgroundColor: 'white',
          borderRadius: '12px',
          padding: '24px',
          maxWidth: '600px',
          width: '90%',
          maxHeight: '80vh',
          overflowY: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h2 style={{ fontSize: '18px', fontWeight: 600, color: '#1a1a1a', margin: 0 }}>
            Refine Your Prompt
          </h2>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              fontSize: '20px',
              cursor: 'pointer',
              color: '#9b9b9b',
              padding: '4px',
            }}
          >
            ×
          </button>
        </div>

        <p style={{ fontSize: '13px', color: '#6b6b6b', marginBottom: '16px' }}>
          Type a rough idea and Haiku will generate 3-5 specific, actionable Terraform prompts
          {detectedResources.length > 0 && ` using resources from your diagram (${detectedResources.join(', ')})`}.
        </p>

        <textarea
          value={roughPrompt}
          onChange={(e) => setRoughPrompt(e.target.value)}
          placeholder="e.g., web app with database"
          style={{
            width: '100%',
            minHeight: '80px',
            padding: '12px',
            borderRadius: '8px',
            border: '1px solid rgba(0,0,0,0.12)',
            fontSize: '14px',
            fontFamily: 'inherit',
            resize: 'vertical',
            marginBottom: '12px',
          }}
        />

        <button
          onClick={handleSuggest}
          disabled={isLoading || !roughPrompt.trim()}
          style={{
            width: '100%',
            padding: '10px 16px',
            backgroundColor: '#5B4EE8',
            color: 'white',
            border: 'none',
            borderRadius: '8px',
            fontSize: '14px',
            fontWeight: 500,
            cursor: isLoading || !roughPrompt.trim() ? 'not-allowed' : 'pointer',
            opacity: isLoading || !roughPrompt.trim() ? 0.6 : 1,
            marginBottom: '20px',
          }}
        >
          {isLoading ? 'Generating suggestions...' : 'Suggest Prompts'}
        </button>

        {suggestions.length > 0 && (
          <>
            <div style={{ fontSize: '12px', fontWeight: 600, color: '#9b9b9b', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
              Suggestions
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {suggestions.map((suggestion, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSelect(suggestion)}
                  style={{
                    padding: '12px 14px',
                    borderRadius: '8px',
                    border: '1px solid #E5E7EB',
                    background: 'white',
                    fontSize: '13px',
                    color: '#1a1a1a',
                    cursor: 'pointer',
                    textAlign: 'left',
                    lineHeight: '1.45',
                    transition: 'all 0.2s ease',
                  }}
                  onMouseEnter={(e) => {
                    const el = e.currentTarget as HTMLButtonElement;
                    el.style.borderColor = '#C7C3F9';
                    el.style.backgroundColor = '#F5F3EE';
                  }}
                  onMouseLeave={(e) => {
                    const el = e.currentTarget as HTMLButtonElement;
                    el.style.borderColor = '#E5E7EB';
                    el.style.backgroundColor = 'white';
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                    <span style={{
                      width: '20px',
                      height: '20px',
                      borderRadius: '50%',
                      backgroundColor: '#EEEDFE',
                      color: '#5B4EE8',
                      fontSize: '11px',
                      fontWeight: 700,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}>
                      {idx + 1}
                    </span>
                    <span>{suggestion}</span>
                  </div>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
};
