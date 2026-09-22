import { api } from "@/api/client";
import type {
  InventoryAttachment,
  InventoryCategory,
  InventoryItem,
  InventoryMovement,
  InventorySummary,
  WriteOffPage,
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
  items: (opts?: {
    q?: string;
    category_slug?: string;
    only_low?: boolean;
    include_archived?: boolean;
  }) => {
    const params = new URLSearchParams();
    if (opts?.q) params.set("q", opts.q);
    if (opts?.category_slug) params.set("category_slug", opts.category_slug);
    if (opts?.only_low) params.set("only_low", "true");
    if (opts?.include_archived) params.set("include_archived", "true");
    const qs = params.toString();
    return api.get<InventoryItem[]>(`/api/inventory/items${qs ? `?${qs}` : ""}`);
  },
  /**
   * The write-off ledger — everything struck off the register, with totals.
   *
   * Separate from `recentMovements({ reason: "write_off" })`: that one is a capped feed of
   * the last 200 movements, this one is filtered, paged and totalled over the whole set.
   */
  writeOffs: (opts?: {
    q?: string;
    category_slug?: string;
    date_from?: string;
    date_to?: string;
    limit?: number;
    offset?: number;
  }) => {
    const params = new URLSearchParams();
    if (opts?.q) params.set("q", opts.q);
    if (opts?.category_slug) params.set("category_slug", opts.category_slug);
    if (opts?.date_from) params.set("date_from", opts.date_from);
    if (opts?.date_to) params.set("date_to", opts.date_to);
    if (opts?.limit !== undefined) params.set("limit", String(opts.limit));
    if (opts?.offset) params.set("offset", String(opts.offset));
    const qs = params.toString();
    return api.get<WriteOffPage>(`/api/inventory/write-offs${qs ? `?${qs}` : ""}`);
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
