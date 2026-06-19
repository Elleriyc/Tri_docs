"use client";

import { useRef, useState } from "react";
import { useDocumentNotifications, type DocumentNotification } from "./hooks/useDocumentNotifications";

const STATUS_CONFIG: Record<
  DocumentNotification["status"],
  { label: string; classes: string }
> = {
  UPLOADED:   { label: "Uploadé",     classes: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300" },
  QUEUED:     { label: "En file",     classes: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300" },
  PROCESSING: { label: "Traitement…", classes: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300 animate-pulse" },
  PROCESSED:  { label: "Traité",      classes: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300" },
  ERROR:      { label: "Erreur",      classes: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300" },
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ??
  "https://tris-docs-web-e6d2bjbnbuajh0ev.germanywestcentral-01.azurewebsites.net";

export default function Home() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [retryError, setRetryError] = useState<string | null>(null);

  const { notification, isConnected } = useDocumentNotifications(documentId);
  const status = notification?.status ?? null;
  const statusCfg = status ? STATUS_CONFIG[status] : null;

  async function handleUpload(e: { preventDefault(): void }) {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    setDocumentId(null);

    try {
      const createRes = await fetch(`${API_BASE}/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fileName: file.name,
          contentType: file.type || "application/octet-stream",
        }),
      });

      if (!createRes.ok) {
        throw new Error(`Erreur ${createRes.status} : ${await createRes.text()}`);
      }

      const job = (await createRes.json()) as { job_id: string; upload_url: string };
      setDocumentId(job.job_id);

      const blobRes = await fetch(job.upload_url, {
        method: "PUT",
        headers: {
          "x-ms-blob-type": "BlockBlob",
          "Content-Type": file.type || "application/octet-stream",
        },
        body: file,
      });

      if (!blobRes.ok) {
        throw new Error(`Erreur upload Blob Storage : ${blobRes.status}`);
      }
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  }

  async function handleRetry() {
    if (!documentId) return;
    setRetryError(null);
    try {
      const res = await fetch(`${API_BASE}/jobs/${documentId}/retry`, { method: "POST" });
      if (!res.ok) {
        throw new Error(`Erreur ${res.status} : ${await res.text()}`);
      }
    } catch (err) {
      setRetryError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="flex flex-col min-h-screen bg-zinc-50 font-sans dark:bg-black">
      {/* ── Header ── */}
      <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-8 py-5 dark:border-zinc-800 dark:bg-zinc-950">
        <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
          TRI_DOCS
        </h1>
        <div className="flex items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
          <span
            className={`h-2.5 w-2.5 rounded-full transition-colors ${
              isConnected ? "bg-green-500" : "bg-red-400"
            }`}
          />
          {isConnected ? "Connecté" : "Déconnecté"}
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-xl flex-col gap-6 px-4 py-12">
        {/* ── Upload section ── */}
        <section className="flex flex-col gap-6 rounded-2xl border border-zinc-200 bg-white p-8 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
          <div>
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
              Uploader un document
            </h2>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              Sélectionnez un fichier pour créer un job et l&apos;envoyer.
            </p>
          </div>

          <form onSubmit={handleUpload} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="fileInput" className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Fichier
              </label>
              <input
                id="fileInput"
                ref={fileInputRef}
                type="file"
                required
                disabled={uploading}
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setUploadError(null);
                }}
                className="block w-full text-sm text-zinc-700 dark:text-zinc-300
                  file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0
                  file:text-sm file:font-medium file:bg-zinc-100 file:text-zinc-800
                  dark:file:bg-zinc-800 dark:file:text-zinc-200
                  hover:file:bg-zinc-200 dark:hover:file:bg-zinc-700
                  disabled:opacity-50 disabled:cursor-not-allowed"
              />
            </div>

            {uploadError && (
              <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-400">
                {uploadError}
              </p>
            )}

            <button
              type="submit"
              disabled={!file || uploading}
              className="flex w-full items-center justify-center gap-2 rounded-full bg-zinc-900 py-2.5 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:bg-zinc-200"
            >
              {uploading ? <><Spinner />Upload en cours…</> : "Uploader"}
            </button>
          </form>
        </section>

        {/* ── Status section ── */}
        {documentId && (
          <section className="flex flex-col gap-5 rounded-2xl border border-zinc-200 bg-white p-8 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <div className="flex items-center justify-between gap-4">
              <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
                Statut du document
              </h2>
              {statusCfg ? (
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusCfg.classes}`}>
                  {statusCfg.label}
                </span>
              ) : (
                <span className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-semibold text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                  En attente…
                </span>
              )}
            </div>

            <p className="break-all font-mono text-xs text-zinc-400 dark:text-zinc-500">
              ID : {documentId}
            </p>

            {notification?.message && (
              <p className="text-sm text-zinc-600 dark:text-zinc-400">
                {notification.message}
              </p>
            )}

            {/* Tags */}
            {notification?.tags && notification.tags.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {notification.tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}

            {/* Retry */}
            {status === "ERROR" && (
              <div className="flex flex-col gap-2">
                <button
                  type="button"
                  onClick={handleRetry}
                  className="self-start rounded-full border border-red-400 px-5 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-50 dark:border-red-600 dark:text-red-400 dark:hover:bg-red-950/30"
                >
                  Réessayer
                </button>
                {retryError && (
                  <p className="text-sm text-red-600 dark:text-red-400">{retryError}</p>
                )}
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  );
}
