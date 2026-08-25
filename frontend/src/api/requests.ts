import { api } from "@/api/client";
import type { RequestAttachmentItem, RequestItem, RequestMessageItem } from "@/types";

export interface RequestFilters {
  status?: string;
  categorySlug?: string;
  /** Only requests this employee is on. Available to Boshliq and Admin, who see everyone. */
  assigneeEmployeeId?: number;
}

export const requestsApi = {
  list: (filters: RequestFilters = {}) => {
    const params = new URLSearchParams();
    if (filters.status) params.set("status_filter", filters.status);
    if (filters.categorySlug) params.set("category_slug", filters.categorySlug);
    if (filters.assigneeEmployeeId !== undefined) {
      params.set("assignee_employee_id", String(filters.assigneeEmployeeId));
    }
    const qs = params.toString();
    return api.get<RequestItem[]>(`/api/requests${qs ? `?${qs}` : ""}`);
  },
  get: (id: number) => api.get<RequestItem>(`/api/requests/${id}`),
  create: (category_slug: string, description: string) =>
    api.post<RequestItem>("/api/requests", { category_slug, description }),
  /** The first id becomes the primary assignee; the rest work alongside them. */
  assign: (id: number, assigned_to_employee_ids: number[], deadline_at: string | null) =>
    api.post<RequestItem>(`/api/requests/${id}/assign`, {
      assigned_to_employee_ids,
      deadline_at,
    }),
  updateStatus: (id: number, status: string, note?: string) =>
    api.post<RequestItem>(`/api/requests/${id}/status`, { status, note }),
  complete: (id: number, completion_note: string) =>
    api.post<RequestItem>(`/api/requests/${id}/complete`, { completion_note }),
  messages: (id: number) => api.get<RequestMessageItem[]>(`/api/requests/${id}/messages`),
  postMessage: (
    id: number,
    body: string,
    visibility: "internal" | "to_requester" = "to_requester",
    attachment_ids: number[] = [],
  ) =>
    api.post<RequestMessageItem>(`/api/requests/${id}/messages`, {
      body,
      visibility,
      attachment_ids,
    }),
  attachments: (id: number) =>
    api.get<RequestAttachmentItem[]>(`/api/requests/${id}/attachments-list`),
  /** Uploads a file to the request. Pass the returned id to `postMessage` to attach it. */
  uploadAttachment: (id: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.postForm<RequestAttachmentItem>(`/api/requests/${id}/attachments`, form);
  },
  rate: (id: number, score: number, comment?: string) =>
    api.post(`/api/requests/${id}/rating`, { score, comment }),
};
