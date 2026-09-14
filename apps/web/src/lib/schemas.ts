/**
 * Zod schemas for API responses. Every response the UI relies on is
 * validated at the boundary (CLAUDE.md); types are inferred from schemas so
 * the two can never drift apart.
 */
import { z } from "zod";

export const messageSchema = z.object({ message: z.string() });

export const sessionUserSchema = z.object({
  id: z.string(),
  email: z.string(),
  full_name: z.string(),
  organization_id: z.string().nullable(),
  organization_name: z.string().nullable(),
  role: z.string().nullable(),
  role_label: z.string().nullable(),
  is_platform_admin: z.boolean(),
  email_verified: z.boolean(),
  mfa_enabled: z.boolean(),
  mfa_required: z.boolean(),
});
export type SessionUser = z.infer<typeof sessionUserSchema>;

export const authResponseSchema = z.object({
  access_token: z.string(),
  token_type: z.string(),
  expires_in: z.number(),
  user: sessionUserSchema,
});
export type AuthResponse = z.infer<typeof authResponseSchema>;

export const mfaChallengeSchema = z.object({
  mfa_required: z.literal(true),
  mfa_token: z.string(),
  expires_in: z.number(),
  message: z.string(),
});

export const loginResponseSchema = z.union([mfaChallengeSchema, authResponseSchema]);

export const invitationPreviewSchema = z.object({
  organization_name: z.string(),
  email: z.string(),
  role: z.string(),
  role_label: z.string(),
  expires_at: z.string(),
  account_exists: z.boolean(),
});

export const mfaSetupSchema = z.object({ secret: z.string(), otpauth_uri: z.string() });
export const recoveryCodesSchema = z.object({
  recovery_codes: z.array(z.string()),
  message: z.string(),
});

export const organizationSchema = z.object({
  id: z.string(),
  name: z.string(),
  slug: z.string(),
  status: z.string(),
  timezone: z.string(),
  currency: z.string(),
});
export type Organization = z.infer<typeof organizationSchema>;

export const organizationSecuritySchema = z.object({ mfa_required: z.boolean() });

export const memberSchema = z.object({
  membership_id: z.string(),
  user_id: z.string(),
  email: z.string(),
  full_name: z.string(),
  role: z.string(),
  role_label: z.string(),
  status: z.string(),
  joined_at: z.string(),
  mfa_enabled: z.boolean(),
  email_verified: z.boolean(),
});
export type Member = z.infer<typeof memberSchema>;

export const invitationSchema = z.object({
  id: z.string(),
  email: z.string(),
  role: z.string(),
  role_label: z.string(),
  status: z.string(),
  expires_at: z.string(),
  accepted_at: z.string().nullable(),
  revoked_at: z.string().nullable(),
  last_sent_at: z.string().nullable(),
  email_status: z.string().nullable(),
});
export type Invitation = z.infer<typeof invitationSchema>;

export const safetyEventSchema = z.object({
  id: z.string(),
  event_type: z.string(),
  event_label: z.string(),
  severity: z.string(),
  severity_label: z.string(),
  confidence: z.number(),
  occurred_at: z.string(),
  vehicle_id: z.string(),
  driver_id: z.string().nullable(),
  trip_id: z.string().nullable(),
  latitude: z.number().nullable(),
  longitude: z.number().nullable(),
  reason_tr: z.string(),
  review_status: z.string(),
  occurrence_count: z.number(),
  needs_review: z.boolean(),
});
export type SafetyEvent = z.infer<typeof safetyEventSchema>;

export const safetyEventListSchema = z.object({
  items: z.array(safetyEventSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});
export type SafetyEventList = z.infer<typeof safetyEventListSchema>;

export const liveVehicleSchema = z.object({
  trip_id: z.string(),
  vehicle_id: z.string(),
  driver_id: z.string().nullable(),
  latitude: z.number().nullable(),
  longitude: z.number().nullable(),
  last_point_at: z.string().nullable(),
  max_speed_kph: z.number().nullable(),
  is_stale: z.boolean(),
});
export type LiveVehicle = z.infer<typeof liveVehicleSchema>;

export const roadRiskSchema = z.object({
  id: z.string(),
  risk_type: z.string(),
  center_latitude: z.number(),
  center_longitude: z.number(),
  radius_m: z.number(),
  observed_count: z.number(),
  inferred_severity: z.string(),
  confidence: z.number(),
  source: z.string(),
  review_status: z.string(),
});
export type RoadRisk = z.infer<typeof roadRiskSchema>;
