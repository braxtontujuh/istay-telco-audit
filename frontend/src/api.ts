import { z } from 'zod';
import type { components } from './api-schema';

export type Session = components['schemas']['SessionView'];
export const sessionSchema: z.ZodType<Session> = z.object({
  user: z.object({id: z.number(), username: z.string(), full_name: z.string(),
    role: z.enum(['ADMIN', 'MANAGER', 'AUDITOR'])}),
  csrf_token: z.string(),
});
// Session and CSRF material live only in memory / HttpOnly cookie, never localStorage or IndexedDB.
let csrfToken = '';
let workspaceOwner: number|null=null;
export function setWorkspaceOwner(owner:number|null){workspaceOwner=owner;}
export function getWorkspaceOwner(){return workspaceOwner;}
export function setSession(session: Session | null) { csrfToken = session?.csrf_token ?? ''; }
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}
const messages: Record<string, string> = {
  LOGIN_REQUIRED: 'Please sign in to continue.', SESSION_EXPIRED: 'Your session expired. Please sign in again.',
  INVALID_CREDENTIALS: 'The username or password is incorrect.', CSRF_REJECTED: 'Please reload and sign in again.',
  SITE_ACCESS_DENIED: 'This action requires permission for every selected site.',
  ALL_TARGETS_REQUIRE_AUTHORIZED_ASSIGNEE: 'Assign every target to an active employee with site access before activation.',
  CONSTRAINT_CONFLICT: 'This code or record already exists, or its related data is inconsistent.',
  AUDIT_CONFIG_FROZEN: 'An activated audit keeps its original configuration.',
  TARGET_LIST_FROZEN: 'An activated audit keeps its original target list.',
  UNRESOLVED_CLOSURE_REQUIRES_REASON: 'Enter a reason before closing an audit with pending targets.',
  ROLE_DENIED: 'Your account does not have permission for this action.',
  ASSIGNMENT_REQUIRED: 'This audit is not currently assigned to you.',
  VALIDATION_ERROR: 'Check the required fields and value limits.',
};
export async function api(path: string, init?: RequestInit) {
  const response = await fetch(`/api/v1${path}`, {
    ...init, credentials: 'same-origin', cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken,
      ...(workspaceOwner?{'X-Workspace-User':String(workspaceOwner)}:{}), ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const code = body?.error?.code ?? 'REQUEST_FAILED';
    throw new ApiError(response.status, code, messages[code] ?? body?.error?.message ?? `Request failed (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}
