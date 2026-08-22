import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";
import { useAuth } from "@/context/AuthContext";

type Step = "enter_id" | "waiting" | "expired";

export function EmployeeVerifyPanel({ onBack }: { onBack: () => void }) {
  const [step, setStep] = useState<Step>("enter_id");
  const [employeeIdNumber, setEmployeeIdNumber] = useState("");
  const [deepLink, setDeepLink] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const pollRef = useRef<number | null>(null);
  const { refresh } = useAuth();
  const navigate = useNavigate();

  async function startVerification(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await authApi.telegramLinkStart(employeeIdNumber.trim());
      setDeepLink(res.deep_link);
      setToken(res.token);
      setStep("waiting");
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 404
          ? "Bunday ID raqamli faol xodim topilmadi."
          : "Xatolik yuz berdi.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (step !== "waiting" || !token) return;

    pollRef.current = window.setInterval(async () => {
      try {
        const res = await authApi.telegramLinkStatus(token);
        if (res.session_ready) {
          window.clearInterval(pollRef.current!);
          await refresh();
          navigate("/");
        } else if (res.status === "expired") {
          window.clearInterval(pollRef.current!);
          setStep("expired");
        }
      } catch {
        // transient poll error, try again next tick
      }
    }, 2000);

    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [step, token, refresh, navigate]);

  if (step === "enter_id") {
    return (
      <form onSubmit={startVerification} className="space-y-4">
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">HEMIS xodim ID raqami</label>
          <input
            required
            value={employeeIdNumber}
            onChange={(e) => setEmployeeIdNumber(e.target.value)}
            placeholder="Masalan: 4572611114"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
          />
        </div>
        {error && <div className="text-sm text-red-600">{error}</div>}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {loading ? "Tekshirilmoqda..." : "Davom etish"}
        </button>
        <button type="button" onClick={onBack} className="w-full text-sm text-slate-500 hover:text-slate-700">
          ⬅ Orqaga
        </button>
      </form>
    );
  }

  if (step === "waiting") {
    return (
      <div className="space-y-4 text-center">
        <p className="text-sm text-slate-600">
          Telegram botimizga o'ting va shaxsingizni tasdiqlang. Tasdiqlangach, bu sahifa avtomatik davom etadi.
        </p>
        <a
          href={deepLink ?? "#"}
          target="_blank"
          rel="noreferrer"
          className="inline-block w-full rounded-lg bg-brand-600 px-4 py-3 text-sm font-medium text-white hover:bg-brand-700"
        >
          Telegram botni ochish
        </a>
        <div className="flex items-center justify-center gap-2 text-xs text-slate-400">
          <span className="h-2 w-2 animate-pulse rounded-full bg-brand-500" />
          Tasdiqlanishi kutilmoqda...
        </div>
        <button
          type="button"
          onClick={() => {
            if (pollRef.current) window.clearInterval(pollRef.current);
            setStep("enter_id");
          }}
          className="w-full text-sm text-slate-500 hover:text-slate-700"
        >
          ⬅ Orqaga
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4 text-center">
      <p className="text-sm text-red-600">Havola muddati tugadi. Qaytadan urinib ko'ring.</p>
      <button
        onClick={() => setStep("enter_id")}
        className="w-full rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
      >
        Qaytadan urinish
      </button>
    </div>
  );
}
