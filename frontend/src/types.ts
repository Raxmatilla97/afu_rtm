export interface AdminMe {
  id: number;
  email: string;
  role: string;
}

export interface EmployeeMe {
  id: number;
  full_name: string;
  employee_id_number: string;
  department_name: string | null;
  is_rtm_staff: boolean;
  is_supervisor: boolean;
  is_admin: boolean;
  /** Boshliq or Admin: may assign a request to somebody and take somebody off one. */
  can_manage_assignments: boolean;
  phone_number: string | null;
  telegram_username: string | null;
}

export interface Department {
  id: number;
  hemis_id: number;
  name: string;
  code: string | null;
  parent_department_id: number | null;
  is_active: boolean;
}

export interface Employee {
  id: number;
  hemis_id: number | null;
  employee_id_number: string;
  full_name: string;
  department_id: number | null;
  department_name: string | null;
  employee_status_code: string | null;
  is_active: boolean;
  year_of_enter: number | null;
  is_rtm_staff: boolean;
  is_supervisor: boolean;
  is_admin: boolean;
  /** Set by hand in the admin panel. Separate from access_revoked, which HEMIS owns. */
  is_blocked: boolean;
  blocked_at: string | null;
  access_revoked: boolean;
  access_revoked_at: string | null;
  telegram_user_id: number | null;
  telegram_username: string | null;
  phone_number: string | null;
  verified_at: string | null;
  image_local_path: string | null;
  /** What HEMIS said the photo is. Null with no local copy = HEMIS never offered one. */
  image_source_url: string | null;
  /** Set when an administrator uploaded the photo; the HEMIS sync then leaves it alone. */
  image_manual_at: string | null;
  /** How many requests this person has filed. Only the employee list fills it. */
  request_count: number;
  /** Quick login: whether this account has been claimed, and when. */
  has_quick_password: boolean;
  password_set_at: string | null;
  recovery_email: string | null;
  hemis_login: string | null;
  hemis_email: string | null;
  hemis_phone: string | null;
  hemis_university_id: string | null;
  oauth_verified_at: string | null;
  last_synced_at: string | null;
  created_at: string | null;
}

export interface Category {
  slug: string;
  label_uz: string;
  sort_order: number;
}

export type AttachmentKind = "photo" | "video" | "voice" | "video_note" | "audio" | "document";

export interface RequestAttachmentItem {
  id: number;
  request_id: number;
  message_id: number | null;
  kind: AttachmentKind;
  kind_label: string;
  file_path: string | null;
  original_filename: string | null;
  content_type: string | null;
  file_size: number | null;
  duration_seconds: number | null;
  /** Same-origin path for <img>/<video>/<audio>. Null when the file lives only in Telegram. */
  url: string | null;
  created_at: string;
}

export interface RequesterCard {
  id: number;
  full_name: string;
  employee_id_number: string | null;
  department_name: string | null;
  phone_number: string | null;
  telegram_username: string | null;
  image_local_path: string | null;
}

export interface AssigneeCard {
  employee_id: number;
  full_name: string;
  is_primary: boolean;
}

export interface RequestItem {
  id: number;
  display_number: string;
  requester_employee_id: number;
  requester_name: string | null;
  requester: RequesterCard | null;
  assignees: AssigneeCard[];
  category_slug: string;
  category_label: string | null;
  /** The plain reading — what Telegram shows, and the fallback when there is no markup. */
  description: string;
  /** Formatted description, when the request was written on the web. Null for bot requests. */
  description_html: string | null;
  status: string;
  source: string;
  assigned_to_employee_id: number | null;
  assigned_to_name: string | null;
  deadline_at: string | null;
  completed_at: string | null;
  completion_note: string | null;
  /** Set when a Boshliq or Admin sent the request back as wrongly filed. */
  returned_at: string | null;
  return_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface RequestMessageItem {
  id: number;
  request_id: number;
  author_employee_id: number | null;
  author_user_id: number | null;
  author_name: string | null;
  visibility: "internal" | "to_requester";
  body: string | null;
  attachments: RequestAttachmentItem[];
  created_at: string;
}

export interface HemisSyncRun {
  id: number;
  status: "running" | "success" | "failed";
  started_at: string;
  finished_at: string | null;
  departments_created: number;
  departments_updated: number;
  employees_created: number;
  employees_updated: number;
  employees_revoked: number;
  error_message: string | null;
}

export interface StaffRatingSummary {
  employee_id: number;
  full_name: string;
  completed_count: number;
  average_score: number | null;
  rating_count: number;
}

export interface StatsSummary {
  total_requests: number;
  new_count: number;
  assigned_count: number;
  in_progress_count: number;
  completed_count: number;
  cancelled_count: number;
}

export interface MonthlyCount {
  month: string;
  count: number;
}

export const STATUS_LABELS: Record<string, string> = {
  new: "Yangi",
  assigned: "Tayinlangan",
  in_progress: "Jarayonda",
  waiting: "Inventar kutilmoqda",
  completed: "Bajarilgan",
  cancelled: "Bekor qilingan",
  returned: "Qaytarib yuborilgan",
};

export interface MonthlyPoint {
  month: string;
  created: number;
  completed: number;
}

export interface CategoryCount {
  slug: string;
  label: string;
  total: number;
  completed: number;
}

export interface RatingBucket {
  score: number;
  count: number;
}

export interface ResolutionStats {
  average_hours: number | null;
  median_hours: number | null;
  fastest_hours: number | null;
  slowest_hours: number | null;
  on_time: number;
  late: number;
}

export interface StaffLoad {
  employee_id: number;
  full_name: string;
  open_count: number;
  completed_count: number;
  average_score: number | null;
}

export interface StatsOverview {
  summary: StatsSummary;
  monthly: MonthlyPoint[];
  by_category: CategoryCount[];
  ratings: RatingBucket[];
  average_rating: number | null;
  rating_count: number;
  resolution: ResolutionStats;
  staff_load: StaffLoad[];
  open_overdue: number;
  unassigned: number;
}

/** Money crosses the wire as a string: JSON has no decimal, and a float would round it. */
export type Money = string | null;

export interface InventoryCategory {
  slug: string;
  label_uz: string;
  sort_order: number;
  is_active: boolean;
  item_count: number;
}

export interface InventoryAttachment {
  id: number;
  item_id: number;
  movement_id: number | null;
  original_filename: string | null;
  content_type: string | null;
  file_size: number | null;
  url: string;
  created_at: string;
}

export interface InventoryItem {
  id: number;
  category_slug: string;
  category_label: string | null;
  name: string;
  unit: string;
  quantity: number;
  min_quantity: number;
  is_low: boolean;
  status: string;
  status_label: string;
  unit_price: Money;
  note: string | null;
  attachments: InventoryAttachment[];
  created_at: string;
  updated_at: string;
}

export interface InventoryMovement {
  id: number;
  item_id: number;
  item_name: string | null;
  delta: number;
  reason: string;
  reason_label: string;
  request_id: number | null;
  request_number: string | null;
  employee_name: string | null;
  unit_price: Money;
  total_price: Money;
  note: string | null;
  attachments: InventoryAttachment[];
  created_at: string;
}

export interface InventorySummary {
  total_items: number;
  in_stock_items: number;
  low_items: number;
  planned_items: number;
  stock_value: Money;
  spent_this_month: Money;
  consumed_this_month: number;
}

export interface SoftCategory {
  slug: string;
  label_uz: string;
  sort_order: number;
  is_active: boolean;
  asset_count: number;
}

export interface SoftAsset {
  id: number;
  category_slug: string;
  category_label: string | null;
  title: string;
  version: string | null;
  description: string | null;
  original_filename: string | null;
  content_type: string | null;
  file_size: number | null;
  download_count: number;
  /** How many times the bot has shown this file in its Soft list. */
  view_count: number;
  is_active: boolean;
  /** The bot already holds a Telegram handle, so the next hand-off costs no upload. */
  is_cached: boolean;
  download_url: string;
  last_sent_at: string | null;
  created_at: string;
}
