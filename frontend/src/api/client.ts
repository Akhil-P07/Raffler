import axios, { AxiosError } from "axios";
import type {
  DrawResponse,
  Entry,
  GenerateTicketsResponse,
  Raffle,
  RaffleDetail,
  RaffleInput,
  RaffleLogo,
  RegisterConfirmation,
  RegisterInfo,
  Ticket,
  Winner,
} from "./types";

// In dev, default to "/api" so Vite's proxy forwards to the backend and the
// SPA stays same-origin (CSP connect-src 'self'). In prod, VITE_API_BASE is
// the real API origin.
const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

const API_KEY_STORAGE = "raffler_api_key";

export function getApiKey(): string | null {
  return localStorage.getItem(API_KEY_STORAGE);
}

export function setApiKey(key: string): void {
  localStorage.setItem(API_KEY_STORAGE, key.trim());
}

export function clearApiKey(): void {
  localStorage.removeItem(API_KEY_STORAGE);
}

// Authenticated client: injects the org API key on every request.
const authed = axios.create({ baseURL: API_BASE });
authed.interceptors.request.use((config) => {
  const key = getApiKey();
  if (key) {
    config.headers.set("X-API-Key", key);
  }
  return config;
});

// Public client: NO API key. Used for the buyer registration flow only.
const pub = axios.create({ baseURL: API_BASE });

/** Normalize a backend error into a plain message for the UI. */
export function errorMessage(err: unknown, fallback = "Something went wrong."): string {
  if (err instanceof AxiosError) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
    if (err.response?.status === 401) return "Invalid or missing API key.";
  }
  return fallback;
}

export function isUnauthorized(err: unknown): boolean {
  return err instanceof AxiosError && err.response?.status === 401;
}

// --- Raffles --------------------------------------------------------------

export async function listRaffles(): Promise<Raffle[]> {
  return (await authed.get<Raffle[]>("/raffles")).data;
}

export async function getRaffle(id: string): Promise<RaffleDetail> {
  return (await authed.get<RaffleDetail>(`/raffles/${id}`)).data;
}

export async function createRaffle(input: RaffleInput): Promise<Raffle> {
  return (await authed.post<Raffle>("/raffles", input)).data;
}

export async function updateRaffle(
  id: string,
  body: { name?: string; status?: "active" | "closed" }
): Promise<Raffle> {
  return (await authed.patch<Raffle>(`/raffles/${id}`, body)).data;
}

export async function deleteRaffle(id: string): Promise<void> {
  await authed.delete(`/raffles/${id}`);
}

// --- Tickets --------------------------------------------------------------

export async function generateTickets(
  raffleId: string,
  count: number
): Promise<GenerateTicketsResponse> {
  return (
    await authed.post<GenerateTicketsResponse>(`/raffles/${raffleId}/tickets`, {
      count,
    })
  ).data;
}

export async function listTickets(raffleId: string): Promise<Ticket[]> {
  return (await authed.get<Ticket[]>(`/raffles/${raffleId}/tickets`)).data;
}

/**
 * Fetch a single ticket's QR PNG as an object URL. Needed because a plain
 * <img src> can't attach the X-API-Key header — these endpoints are
 * ownership-checked, so we fetch the bytes authenticated and wrap them.
 * Caller is responsible for URL.revokeObjectURL when done.
 */
export async function fetchQrObjectUrl(ticketId: string): Promise<string> {
  const res = await authed.get(`/tickets/${ticketId}/qr`, {
    responseType: "blob",
  });
  return URL.createObjectURL(res.data as Blob);
}

/** Fetch the server-rendered print sheet PNG and trigger a download. */
export async function downloadTicketSheet(
  raffleId: string,
  raffleName: string
): Promise<void> {
  const res = await authed.get(`/raffles/${raffleId}/tickets/sheet`, {
    responseType: "blob",
  });
  const url = URL.createObjectURL(res.data as Blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${raffleName.replace(/[^a-z0-9]+/gi, "-")}-print-sheet.png`;
  a.click();
  URL.revokeObjectURL(url);
}

// --- Logos ----------------------------------------------------------------

/**
 * Rasterize an SVG to a PNG Blob in the browser (canvas), so the backend only
 * ever stores PNG and we don't need a server-side SVG converter. Non-SVG files
 * pass through unchanged.
 */
async function rasterizeIfSvg(file: File): Promise<Blob> {
  const isSvg =
    file.type === "image/svg+xml" || file.name.toLowerCase().endsWith(".svg");
  if (!isSvg) return file;

  const text = await file.text();
  const url = URL.createObjectURL(new Blob([text], { type: "image/svg+xml" }));
  try {
    const img = new Image();
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error("Could not load SVG"));
      img.src = url;
    });
    const maxSide = 400;
    const natW = img.width || 300;
    const natH = img.height || 300;
    const scale = Math.min(1, maxSide / Math.max(natW, natH));
    const w = Math.max(1, Math.round(natW * scale));
    const h = Math.max(1, Math.round(natH * scale));
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Could not get a 2D canvas context");
    ctx.drawImage(img, 0, 0, w, h);
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (b) => (b ? resolve(b) : reject(new Error("Canvas export failed"))),
        "image/png"
      )
    );
  } finally {
    URL.revokeObjectURL(url);
  }
}

export async function listRaffleLogos(raffleId: string): Promise<RaffleLogo[]> {
  return (await authed.get<RaffleLogo[]>(`/raffles/${raffleId}/logos`)).data;
}

export async function uploadRaffleLogo(
  raffleId: string,
  file: File,
  name?: string
): Promise<RaffleLogo> {
  const png = await rasterizeIfSvg(file);
  // Rasterized SVGs become PNG; other files keep their original name so the
  // backend's content sniffing / any extension hint stays accurate.
  const filename = png === (file as Blob) ? file.name : "logo.png";
  const form = new FormData();
  form.append("file", png, filename);
  if (name?.trim()) form.append("name", name.trim());
  return (await authed.post<RaffleLogo>(`/raffles/${raffleId}/logos`, form)).data;
}

export async function fetchRaffleLogoUrl(
  raffleId: string,
  logoId: string
): Promise<string> {
  const res = await authed.get(`/raffles/${raffleId}/logos/${logoId}`, {
    responseType: "blob",
  });
  return URL.createObjectURL(res.data as Blob);
}

export async function deleteRaffleLogo(
  raffleId: string,
  logoId: string
): Promise<void> {
  await authed.delete(`/raffles/${raffleId}/logos/${logoId}`);
}

// --- Entries --------------------------------------------------------------

export async function listEntries(raffleId: string): Promise<Entry[]> {
  return (await authed.get<Entry[]>(`/raffles/${raffleId}/entries`)).data;
}

/** Download the entries CSV via an authenticated request (blob), then save. */
export async function downloadEntriesCsv(
  raffleId: string,
  raffleName: string
): Promise<void> {
  const res = await authed.get(`/raffles/${raffleId}/entries/export`, {
    responseType: "blob",
  });
  const url = URL.createObjectURL(res.data as Blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${raffleName.replace(/[^a-z0-9]+/gi, "-")}-entries.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// --- Draw -----------------------------------------------------------------

export async function drawRaffle(
  raffleId: string,
  prizeCount: number
): Promise<DrawResponse> {
  return (
    await authed.post<DrawResponse>(`/raffles/${raffleId}/draw`, {
      prize_count: prizeCount,
    })
  ).data;
}

export async function listWinners(raffleId: string): Promise<Winner[]> {
  return (await authed.get<Winner[]>(`/raffles/${raffleId}/winners`)).data;
}

// --- Public registration --------------------------------------------------

export async function getRegisterInfo(token: string): Promise<RegisterInfo> {
  return (await pub.get<RegisterInfo>(`/register/${token}`)).data;
}

export async function submitRegistration(
  token: string,
  name: string,
  email: string
): Promise<RegisterConfirmation> {
  return (
    await pub.post<RegisterConfirmation>(`/register/${token}`, { name, email })
  ).data;
}
