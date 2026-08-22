import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { categoriesApi } from "@/api/reference";
import { requestsApi } from "@/api/requests";
import type { Category } from "@/types";

export function NewRequestPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [categorySlug, setCategorySlug] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    categoriesApi.list().then(setCategories);
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!categorySlug || !description.trim()) return;
    setBusy(true);
    try {
      const r = await requestsApi.create(categorySlug, description.trim());
      navigate(`/requests/${r.id}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-xl">
      <h1 className="mb-6 text-2xl font-bold text-slate-900">Yangi murojaat</h1>
      <form onSubmit={handleSubmit} className="space-y-4 rounded-xl border border-slate-200 bg-white p-6">
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Murojaat turi</label>
          <select
            required
            value={categorySlug}
            onChange={(e) => setCategorySlug(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">Tanlang</option>
            {categories.map((c) => (
              <option key={c.slug} value={c.slug}>
                {c.label_uz}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Tavsif</label>
          <textarea
            required
            rows={5}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Muammoni batafsil tasvirlab bering..."
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </div>
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {busy ? "Yuborilmoqda..." : "Yuborish"}
        </button>
      </form>
    </div>
  );
}
