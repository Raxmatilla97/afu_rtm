import { useCallback, useEffect, useState } from "react";
import { describeError } from "@/api/errors";
import { softApi } from "@/api/soft";
import { useAuth } from "@/context/AuthContext";
import type { SoftAsset, SoftCategory } from "@/types";

function humanSize(bytes: number | null): string {
  if (!bytes) return "—";
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function SoftPage() {
  const { isAdmin, session } = useAuth();
  const canWrite =
    isAdmin || (session.kind === "employee" && session.employee.can_manage_assignments);

  const [categories, setCategories] = useState<SoftCategory[]>([]);
  const [assets, setAssets] = useState<SoftAsset[]>([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [form, setForm] = useState({
    category_slug: "",
    title: "",
    version: "",
    description: "",
  });
  const [file, setFile] = useState<File | null>(null);

  const load = useCallback(async () => {
    try {
      const [cats, list] = await Promise.all([
        softApi.categories(),
        softApi.assets(filter || undefined),
      ]);
      setCategories(cats);
      setAssets(list);
      setError(null);
    } catch (e) {
      setError(describeError(e));
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await load();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">RTM Soft</h1>
        <p className="text-sm text-slate-500">
          Drayverlar va dasturlar. Bu yerga yuklangan fayllar botdagi
          «💿 Soft va drayverlar» tugmasida chiqadi.
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {canWrite && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!file || !form.title.trim() || !form.category_slug) return;
            void run(async () => {
              await softApi.upload({
                file,
                category_slug: form.category_slug,
                title: form.title.trim(),
                version: form.version.trim() || undefined,
                description: form.description.trim() || undefined,
              });
              setForm({ category_slug: form.category_slug, title: "", version: "", description: "" });
              setFile(null);
            });
          }}
          className="mb-6 grid gap-3 rounded-xl border border-slate-200 bg-white p-5 sm:grid-cols-2 lg:grid-cols-4"
        >
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">Kategoriya</span>
            <select
              required
              value={form.category_slug}
              onChange={(e) => setForm({ ...form, category_slug: e.target.value })}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Tanlang</option>
              {categories.map((c) => (
                <option key={c.slug} value={c.slug}>
                  {c.label_uz}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">Nomi</span>
            <input
              required
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="HP LaserJet 1102 drayver"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">
              Versiya / OS
            </span>
            <input
              value={form.version}
              onChange={(e) => setForm({ ...form, version: e.target.value })}
              placeholder="Win 10/11 x64"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">Fayl</span>
            <input
              type="file"
              required
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-slate-600 file:mr-2 file:rounded-lg file:border file:border-slate-300 file:bg-white file:px-2 file:py-1.5 file:text-sm"
            />
          </label>
          <label className="block sm:col-span-2 lg:col-span-3">
            <span className="mb-1 block text-xs font-medium text-slate-600">
              Izoh (ixtiyoriy)
            </span>
            <input
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          <div className="flex items-end">
            <button
              type="submit"
              disabled={busy}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {busy ? "Yuklanmoqda..." : "⬆️ Yuklash"}
            </button>
          </div>
          <p className="text-xs text-slate-400 lg:col-span-4">
            Fayl 25 MB gacha. Botda birinchi marta yuborilgach Telegram uni keshlaydi —
            keyingi so'rovlar bir zumda bajariladi.
          </p>
        </form>
      )}

      <div className="mb-4">
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
        >
          <option value="">Barcha kategoriyalar</option>
          {categories.map((c) => (
            <option key={c.slug} value={c.slug}>
              {c.label_uz} ({c.asset_count})
            </option>
          ))}
        </select>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Nomi</th>
              <th className="px-4 py-3">Kategoriya</th>
              <th className="px-4 py-3 text-right">Hajmi</th>
              <th className="px-4 py-3 text-right">Yuklab olishlar</th>
              <th className="px-4 py-3">Amallar</th>
            </tr>
          </thead>
          <tbody>
            {assets.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-400">
                  Hozircha fayl yo'q
                </td>
              </tr>
            )}
            {assets.map((asset) => (
              <tr
                key={asset.id}
                className={`border-b border-slate-100 last:border-0 hover:bg-slate-50 ${
                  asset.is_active ? "" : "opacity-50"
                }`}
              >
                <td className="px-4 py-3">
                  <div className="font-medium">
                    {asset.title}
                    {asset.version && (
                      <span className="ml-1 text-xs font-normal text-slate-400">
                        {asset.version}
                      </span>
                    )}
                    {asset.is_cached && (
                      <span
                        title="Telegram keshida — bot uni bir zumda yuboradi"
                        className="ml-2 rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] text-emerald-700"
                      >
                        ⚡ kesh
                      </span>
                    )}
                  </div>
                  {asset.description && (
                    <div className="text-xs text-slate-400">{asset.description}</div>
                  )}
                </td>
                <td className="px-4 py-3 text-slate-500">{asset.category_label}</td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-600">
                  {humanSize(asset.file_size)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-600">
                  {asset.download_count}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1.5">
                    <a
                      href={asset.download_url}
                      className="rounded-full border border-slate-300 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-100"
                    >
                      ⬇️ Yuklab olish
                    </a>
                    {canWrite && asset.is_active && (
                      <button
                        onClick={() =>
                          window.confirm(`"${asset.title}" ro'yxatdan yashirilsinmi?`) &&
                          void run(() => softApi.deactivate(asset.id))
                        }
                        disabled={busy}
                        className="rounded-full border border-red-300 px-2.5 py-1 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50"
                      >
                        🗑 Yashirish
                      </button>
                    )}
                    {canWrite && !asset.is_active && (
                      <button
                        onClick={() => void run(() => softApi.update(asset.id, { is_active: true }))}
                        disabled={busy}
                        className="rounded-full border border-slate-300 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-100 disabled:opacity-50"
                      >
                        ↩️ Qaytarish
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
