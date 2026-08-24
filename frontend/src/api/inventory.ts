import { api } from "@/api/client";
import type {
  InventoryAttachment,
  InventoryCategory,
  InventoryItem,
  InventoryMovement,
  InventorySummary,
} from "@/types";

export interface ItemDraft {
  category_slug: string;
  name: string;
  unit: string;
  min_quantity: number;
  unit_price: string | null;
  status: string;
  note: string | null;
  initial_quantity: number;
}

// POST everywhere, never PATCH: the WAF in front of this app forwards only GET/POST/HEAD,
// and a PATCH route reaches the backend as silence.
export const inventoryApi = {
  categories: () => api.get<InventoryCategory[]>("/api/inventory/categories"),
  summary: () => api.get<InventorySummary>("/api/inventory/summary"),
  items: (opts?: { q?: string; category_slug?: string; only_low?: boolean }) => {
    const params = new URLSearchParams();
    if (opts?.q) params.set("q", opts.q);
    if (opts?.category_slug) params.set("category_slug", opts.category_slug);
    if (opts?.only_low) params.set("only_low", "true");
    const qs = params.toString();
    return api.get<InventoryItem[]>(`/api/inventory/items${qs ? `?${qs}` : ""}`);
  },
  createItem: (draft: ItemDraft) => api.post<InventoryItem>("/api/inventory/items", draft),
  updateItem: (id: number, patch: Partial<ItemDraft>) =>
    api.post<InventoryItem>(`/api/inventory/items/${id}`, patch),
  movements: (id: number) =>
    api.get<InventoryMovement[]>(`/api/inventory/items/${id}/movements`),
  recentMovements: (opts?: { reason?: string; request_id?: number }) => {
    const params = new URLSearchParams();
    if (opts?.reason) params.set("reason", opts.reason);
    if (opts?.request_id) params.set("request_id", String(opts.request_id));
    const qs = params.toString();
    return api.get<InventoryMovement[]>(`/api/inventory/movements${qs ? `?${qs}` : ""}`);
  },
  addMovement: (
    id: number,
    body: { delta: number; reason: string; unit_price?: string | null; note?: string | null },
  ) => api.post<InventoryMovement>(`/api/inventory/items/${id}/movements`, body),
  uploadReceipt: (id: number, file: File, movementId?: number) => {
    const form = new FormData();
    form.append("file", file);
    if (movementId !== undefined) form.append("movement_id", String(movementId));
    return api.postForm<InventoryAttachment>(`/api/inventory/items/${id}/attachments`, form);
  },
};
