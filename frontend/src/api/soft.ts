import { api } from "@/api/client";
import type { SoftAsset, SoftCategory } from "@/types";

export const softApi = {
  categories: () => api.get<SoftCategory[]>("/api/soft/categories"),
  assets: (categorySlug?: string) =>
    api.get<SoftAsset[]>(
      `/api/soft/assets${categorySlug ? `?category_slug=${categorySlug}` : ""}`,
    ),
  upload: (fields: {
    file: File;
    category_slug: string;
    title: string;
    version?: string;
    description?: string;
  }) => {
    const form = new FormData();
    form.append("file", fields.file);
    form.append("category_slug", fields.category_slug);
    form.append("title", fields.title);
    if (fields.version) form.append("version", fields.version);
    if (fields.description) form.append("description", fields.description);
    return api.postForm<SoftAsset>("/api/soft/assets", form);
  },
  update: (id: number, patch: Partial<{ title: string; version: string; description: string; category_slug: string; is_active: boolean }>) =>
    api.post<SoftAsset>(`/api/soft/assets/${id}`, patch),
  deactivate: (id: number) => api.post<SoftAsset>(`/api/soft/assets/${id}/delete`),
};
