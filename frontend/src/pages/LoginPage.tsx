import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";
import { useAuth } from "@/context/AuthContext";

const OAUTH_ERRORS: Record<string, string> = {
  denied: "HEMIS orqali kirishga ruxsat berilmadi.",
  expired: "Kirish havolasining muddati tugagan. Qaytadan urinib ko'ring.",
  no_code: "HEMIS javob qaytarmadi. Qaytadan urinib ko'ring.",
  token_error: "HEMIS bilan bog'lanishda xatolik yuz berdi.",
  userinfo_error: "HEMIS'dan ma'lumotlaringizni olib bo'lmadi.",
  wrong_type: "Bu tizim faqat universitet xodimlari uchun.",
  unmatched:
    "Sizni xodimlar ro'yxatidan topa olmadik. Iltimos, RTM bilan bog'laning.",
  ineligible: "Hisobingiz faol emas. Iltimos, RTM bilan bog'laning.",
  subject_conflict: "Hisobingizda nomuvofiqlik aniqlandi. RTM bilan bog'laning.",
};

export function LoginPage() {
  const [mode, setMode] = useState<"choose" | "admin">("choose");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const oauthErrorCode = searchParams.get("oauth_error");
  const oauthError = oauthErrorCode
    ? OAUTH_ERRORS[oauthErrorCode] ?? "Kirishda xatolik yuz berdi."
    : null;

  async function handleAdminLogin(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await authApi.adminLogin(email, password);
      await refresh();
      navigate("/");
    } catch (e) {
      setError(e instanceof ApiError ? "Email yoki parol noto'g'ri." : "Xatolik yuz berdi.");
    } finally {
      setLoading(false);
    }
  }

  function startHemisLogin() {
    // A full-page navigation, not fetch(): the browser must follow the redirect chain to
    // HEMIS and back, and the session cookie is set on the callback response.
    const next = encodeURIComponent("/");
    window.location.href = `/oauth/login?flow=web&next=${next}`;
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="mb-6 text-center">
          <div className="text-xl font-bold text-brand-700">RTM Murojaatlar tizimi</div>
          <div className="text-sm text-slate-500">Alfraganus University</div>
        </div>

        {oauthError && (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            {oauthError}
          </div>
        )}

        {mode === "choose" && (
          <div className="space-y-3">
            <button
              onClick={startHemisLogin}
              className="w-full rounded-lg bg-brand-600 px-4 py-3 text-sm font-medium text-white hover:bg-brand-700"
            >
              🔐 HEMIS orqali kirish
            </button>
            <p className="text-center text-xs text-slate-500">
              Universitet xodimlari HEMIS hisobi bilan kiradi
            </p>
            <button
              onClick={() => setMode("admin")}
              className="w-full rounded-lg border border-slate-300 px-4 py-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Admin sifatida kirish
            </button>
          </div>
        )}

        {mode === "admin" && (
          <form onSubmit={handleAdminLogin} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Parol</label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
            {error && <div className="text-sm text-red-600">{error}</div>}
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {loading ? "Kirilmoqda..." : "Kirish"}
            </button>
            <button
              type="button"
              onClick={() => setMode("choose")}
              className="w-full text-sm text-slate-500 hover:text-slate-700"
            >
              ⬅ Orqaga
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
