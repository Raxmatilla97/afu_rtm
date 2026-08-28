import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";

/**
 * Where the link in the reset email lands.
 *
 * Public on purpose — somebody who has forgotten their password cannot be asked to sign in
 * first. The token in the query string is the whole authorisation: it was mailed to an
 * address the account already had on file, it is single-use, and it expires within the
 * hour.
 */
export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    // Checked here rather than on the server: a mistyped confirmation is not the server's
    // business, and a round trip to be told about it is a round trip wasted.
    if (password !== confirm) {
      setError("Parollar bir xil emas.");
      return;
    }

    setBusy(true);
    try {
      await authApi.quickReset(token, password);
      setDone(true);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message || "Parolni yangilab bo'lmadi."
          : "Serverga ulanib bo'lmadi. Internet aloqasini tekshiring.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="mb-6 text-center">
          <div className="text-xl font-bold text-brand-700">Parolni tiklash</div>
          <div className="text-sm text-slate-500">RTM Murojaatlar tizimi</div>
        </div>

        {!token && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            Havola to'liq emas. Elektron pochtangizdagi havolani to'liq nusxalab oching.
          </div>
        )}

        {token && !done && (
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">
                Yangi parol
              </label>
              <input
                type="password"
                required
                autoFocus
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
              <p className="mt-1 text-xs text-slate-500">
                Kamida 6 ta belgi, ichida kamida bitta harf va bitta raqam bo'lsin.
              </p>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">
                Parolni takrorlang
              </label>
              <input
                type="password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
            {error && <div className="text-sm text-red-600">{error}</div>}
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {busy ? "Saqlanmoqda..." : "Yangi parolni saqlash"}
            </button>
          </form>
        )}

        {done && (
          <div className="space-y-4">
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
              ✅ Parol yangilandi.
            </div>
            <p className="text-sm text-slate-600">
              Endi shu parol bilan kiring — saytda «⚡ Tezkor kirish» orqali, yoki
              Telegram botida «⚡ Tezkor kirish» tugmasini bosib, ID raqamingiz va yangi
              parolingizni kiriting.
            </p>
            <Link
              to="/login"
              className="block w-full rounded-lg bg-brand-600 px-4 py-2 text-center text-sm font-medium text-white hover:bg-brand-700"
            >
              Kirish sahifasiga o'tish
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
