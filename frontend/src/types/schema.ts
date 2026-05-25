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

// 🟢 BEGINNER: TypeScript interfaces define the SHAPE of data objects.
// They don't create actual code; they just tell the compiler and IDE what properties an object should have.
// This prevents bugs by catching typos and missing fields before the app runs.

/**
 * Represents a single step in the 3-step wizard sidebar.
 * Used by WorkflowStepper to render step labels and active state.
 */
export interface WorkflowStep {
  id: number;      // 🟢 BEGINNER: 1 = Upload page, 2 = Design Doc page, 3 = Terraform page.
  name: string;    // 🟢 BEGINNER: The text label shown to the user in the sidebar.
  active: boolean; // 🟢 BEGINNER: true = the user is currently viewing this step.
}

/**
 * Represents a cloud provider the user can select.
 * Currently AWS is the primary supported provider; Azure is planned.
 */
export interface CloudProvider {
  id: string;        // 🟢 BEGINNER: Short code used in code: "aws" or "azure".
  name: string;      // 🟢 BEGINNER: Display name shown in the UI: "AWS".
  fullName: string;  // 🟢 BEGINNER: Full official name: "Amazon Web Services".
  services: string[]; // 🟢 BEGINNER: Array of service names (e.g., ["EC2", "S3", "RDS"]).
  selected: boolean; // 🟢 BEGINNER: Whether the user clicked this provider card.
}

/**
 * Represents a file the user has uploaded.
 * size is stored as a formatted string ("2.4 MB") for display purposes.
 */
export interface UploadedFile {
  name: string;   // 🟢 BEGINNER: Original filename from the user's computer.
  size: string;   // 🟢 BEGINNER: Human-readable size string like "1.2 MB".
  status: string; // 🟢 BEGINNER: Current state: "uploading", "ready", or "error".
}

/**
 * Represents the parsed architecture schema extracted from a diagram.
 * vision_service.py returns JSON matching this shape.
 */
export interface CloudSchema {
  provider: string;   // 🟢 BEGINNER: Which cloud provider was detected ("aws" or "azure").
  resources: any[];   // 🟢 BEGINNER: List of detected cloud resources (EC2, S3, etc.) with their configs.
}
