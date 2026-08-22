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
  employee_id_number: string;
  full_name: string;
  department_id: number | null;
  department_name: string | null;
  employee_status_code: string | null;
  is_active: boolean;
  year_of_enter: number | null;
  is_rtm_staff: boolean;
  access_revoked: boolean;
  telegram_user_id: number | null;
  telegram_username: string | null;
  phone_number: string | null;
  verified_at: string | null;
  image_local_path: string | null;
}

export interface Category {
  slug: string;
  label_uz: string;
  sort_order: number;
}

export interface RequestItem {
  id: number;
  display_number: string;
  requester_employee_id: number;
  requester_name: string | null;
  category_slug: string;
  category_label: string | null;
  description: string;
  status: string;
  source: string;
  assigned_to_employee_id: number | null;
  assigned_to_name: string | null;
  deadline_at: string | null;
  completed_at: string | null;
  completion_note: string | null;
  created_at: string;
  updated_at: string;
}

export interface RequestMessageItem {
  id: number;
  request_id: number;
  author_employee_id: number | null;
  author_user_id: number | null;
  visibility: "internal" | "to_requester";
  body: string;
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
  completed: "Bajarilgan",
  cancelled: "Bekor qilingan",
};
