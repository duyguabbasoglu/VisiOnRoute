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

export const coachingActionSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string().nullable(),
  status: z.string(),
  status_label: z.string(),
  is_overdue: z.boolean(),
  safety_event_id: z.string().nullable(),
  event_label: z.string().nullable(),
  event_occurred_at: z.string().nullable(),
  driver_id: z.string().nullable(),
  driver_name: z.string().nullable(),
  assignee_user_id: z.string().nullable(),
  assignee_name: z.string().nullable(),
  created_by_name: z.string().nullable(),
  due_at: z.string().nullable(),
  notes: z.string().nullable(),
  outcome: z.string().nullable(),
  outcome_label: z.string().nullable(),
  outcome_notes: z.string().nullable(),
  started_at: z.string().nullable(),
  completed_at: z.string().nullable(),
  canceled_at: z.string().nullable(),
  cancel_reason: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type CoachingAction = z.infer<typeof coachingActionSchema>;

export const coachingListSchema = z.object({
  items: z.array(coachingActionSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});

export const coachingSummarySchema = z.object({
  open: z.number(),
  in_progress: z.number(),
  completed: z.number(),
  canceled: z.number(),
  overdue: z.number(),
  completed_last_30_days: z.number(),
  average_days_to_complete: z.number().nullable(),
});

export const coachingAssigneeSchema = z.object({
  user_id: z.string(),
  full_name: z.string(),
  email: z.string(),
  role_label: z.string(),
});

export const COACHING_OUTCOMES = [
  { value: "coached", label: "Sürücüyle görüşme yapıldı" },
  { value: "no_action_needed", label: "İşlem gerekmedi" },
  { value: "escalated", label: "Üst yönetime iletildi" },
  { value: "driver_unavailable", label: "Sürücüye ulaşılamadı" },
] as const;

export const RESOLUTIONS = [
  { value: "kocluk_atandi", label: "Koçluk atandı" },
  { value: "surucu_bilgilendirildi", label: "Sürücü bilgilendirildi" },
  { value: "islem_gerekmedi", label: "İşlem gerekmedi" },
  { value: "ekipman_kontrolu", label: "Ekipman/cihaz kontrolü" },
  { value: "yanlis_alarm", label: "Yanlış alarm" },
] as const;

export const driverSchema = z.object({
  id: z.string(),
  external_id: z.string(),
  full_name: z.string(),
  phone: z.string().nullable(),
  status: z.string(),
  created_at: z.string(),
});

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

export const privacyRequestSchema = z.object({
  id: z.string(),
  kind: z.enum(["export", "erasure"]),
  kind_label: z.string(),
  subject_type: z.enum(["driver", "user"]),
  subject_label: z.string(),
  subject_id: z.string(),
  subject_name: z.string().nullable(),
  status: z.enum(["pending", "processing", "completed", "failed", "canceled"]),
  status_label: z.string(),
  reason: z.string().nullable(),
  created_at: z.string(),
  completed_at: z.string().nullable(),
  download_available: z.boolean(),
  artifact_expires_at: z.string().nullable(),
  result: z.record(z.union([z.number(), z.string(), z.boolean()])),
  error_code: z.string().nullable(),
});
export type PrivacyRequest = z.infer<typeof privacyRequestSchema>;

export const retentionSchema = z.object({
  plan_days: z.number(),
  min_days: z.number(),
  categories: z.array(
    z.object({
      key: z.string(),
      label: z.string(),
      override_days: z.number().nullable(),
      effective_days: z.number(),
    }),
  ),
});
export type Retention = z.infer<typeof retentionSchema>;

export const signedLinkSchema = z.object({ url: z.string().url(), expires_in: z.number() });

export const PRIVACY_ERROR_LABELS: Record<string, string> = {
  SUBJECT_NOT_FOUND: "Kişi bulunamadı (kayıt silinmiş olabilir).",
  OWNER_CANNOT_BE_ERASED: "Organizasyon sahibinin verileri silinemez; önce sahipliği devredin.",
};

export const PRIVACY_RESULT_LABELS: Record<string, string> = {
  assignments: "Araç ataması",
  trips: "Sefer",
  safety_events: "Güvenlik olayı",
  coaching_actions: "Koçluk görevi",
  telemetry_points: "Telemetri noktası",
  media_files: "Medya dosyası",
  sessions: "Oturum",
  audit_entries: "İşlem kaydı",
  reviews: "Olay incelemesi",
  emails: "E-posta",
  telemetry_points_deleted: "Silinen telemetri noktası",
  trips_pseudonymized: "Anonimleştirilen sefer",
  safety_events_pseudonymized: "Anonimleştirilen olay",
  evidence_media_deleted: "Silinen kanıt medyası",
  coaching_actions_redacted: "Notları temizlenen koçluk görevi",
  coaching_actions_unassigned: "Sorumlusu kaldırılan koçluk görevi",
  emails_deleted: "Silinen e-posta kaydı",
  invitations_deleted: "Silinen davet",
};

export const subscriptionSchema = z.object({
  plan_key: z.string(),
  plan_name_tr: z.string(),
  status: z.string(),
  status_label: z.string(),
  vehicle_limit: z.number(),
  user_limit: z.number(),
  retention_days: z.number(),
  trial_ends_at: z.string().nullable(),
  billing_mode: z.string(),
  trial_days_left: z.number().nullable(),
  growth_blocked: z.boolean(),
  usage: z.record(z.number()),
});
export type Subscription = z.infer<typeof subscriptionSchema>;

export const usageSchema = z.object({
  period_days: z.number(),
  current: z.record(z.number()),
  metrics: z.array(
    z.object({
      metric: z.string(),
      label: z.string(),
      unit: z.string(),
      points: z.array(z.object({ day: z.string(), value: z.number() })),
    }),
  ),
});
export type Usage = z.infer<typeof usageSchema>;
