import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { categoriesApi } from "@/api/reference";
import { requestsApi } from "@/api/requests";
import type { Category } from "@/types";

export function NewRequestPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [categorySlug, setCategorySlug] = useState("");
  const [description, setDescription] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    categoriesApi.list().then(setCategories);
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!categorySlug || !description.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await requestsApi.create(categorySlug, description.trim());
      // Attached after creation because an attachment needs a request to belong to. If one
      // file fails the request still exists, so the user is taken to it rather than losing
      // everything they typed.
      for (const file of files) {
        await requestsApi.uploadAttachment(r.id, file);
      }
      navigate(`/requests/${r.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Yuborib bo'lmadi");
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
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">
            Materiallar <span className="font-normal text-slate-400">(ixtiyoriy)</span>
          </label>
          <input
            type="file"
            multiple
            onChange={(e) => setFiles([...files, ...Array.from(e.target.files ?? [])])}
            className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border file:border-slate-300 file:bg-white file:px-3 file:py-1.5 file:text-sm file:text-slate-700"
          />
          {files.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {files.map((file, index) => (
                <span
                  key={`${file.name}-${index}`}
                  className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-700"
                >
                  📎 {file.name}
                  <button
                    type="button"
                    onClick={() => setFiles(files.filter((_, i) => i !== index))}
                    className="text-slate-400 hover:text-red-600"
                    aria-label="Faylni olib tashlash"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
          <p className="mt-1 text-xs text-slate-400">
            Rasm, video yoki hujjat — har biri 25 MB gacha.
          </p>
        </div>

        {error && <div className="text-sm text-red-600">{error}</div>}

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
