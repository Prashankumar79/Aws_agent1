/**
 * ================================================================================
 *   frontend/src/types/schema.ts  —  TYPESCRIPT TYPE DEFINITIONS
 * ================================================================================
 *
 * PURPOSE:
 *   Central repository for all TypeScript interfaces used across the frontend.
 *   Defining shapes here prevents "any" types and gives IDE autocompletion.
 *
 * WHY IT EXISTS:
 *   TypeScript's value is in the types. When every component agrees on what a
 *   "CloudProvider" or "UploadedFile" looks like, refactoring is safe and
 *   bugs are caught at compile time, not runtime.
 *
 * CONNECTIONS TO OTHER FILES:
 *   • store/workflowStore.ts    → imports UploadedFile, CloudSchema
 *   • components/*.tsx          → import these for prop types
 *   • services/api.ts           → imports JobResponse, DesignDoc, etc.
 *
 * NOTE:
 *   Many newer interfaces (ChatMessage, GeneratedFile, AIModel) are defined
 *   directly in terraformChatStore.ts because they are tightly coupled to store
 *   state. This file holds the more generic / shared shapes.
 * ================================================================================
 */

/**
 * Represents a single step in the 3-step wizard sidebar.
 * Used by WorkflowStepper to render step labels and active state.
 */
export interface WorkflowStep {
  id: number;      // 1 = Upload, 2 = Design Doc, 3 = Terraform
  name: string;    // Human-readable label (e.g. "Upload Diagram")
  active: boolean; // Whether the user is currently on this step
}

/**
 * Represents a cloud provider the user can select.
 * Currently AWS is the primary supported provider; Azure is planned.
 */
export interface CloudProvider {
  id: string;        // Short code: "aws", "azure"
  name: string;      // Display name: "AWS"
  fullName: string;  // "Amazon Web Services"
  services: string[]; // List of service names for this provider (e.g. "EC2", "S3")
  selected: boolean; // Whether the user has checked this provider
}

/**
 * Represents a file the user has uploaded.
 * size is stored as a formatted string ("2.4 MB") for display purposes.
 */
export interface UploadedFile {
  name: string;   // Original filename from the file input
  size: string;   // Human-readable size (e.g. "1.2 MB")
  status: string; // "uploading" | "ready" | "error"
}

/**
 * Represents the parsed architecture schema extracted from a diagram.
 * vision_service.py returns JSON matching this shape.
 */
export interface CloudSchema {
  provider: string;   // "aws" | "azure"
  resources: any[];   // Array of detected cloud resources with types & configs
}
