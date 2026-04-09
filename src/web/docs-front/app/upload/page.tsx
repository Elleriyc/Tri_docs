"use client";

import { useState, useRef } from "react";

type JobStatus = "idle" | "loading" | "done" | "error";
type UploadStatus = "idle" | "uploading" | "done" | "error";

interface JobResult {
  job_id: string;
  status: string;
  upload_url: string;
}

export default function UploadPage() {
  // --- Carte 1 : création du job ---
  const [jobStatus, setJobStatus] = useState<JobStatus>("idle");
  const [jobError, setJobError] = useState<string | null>(null);
  const [job, setJob] = useState<JobResult | null>(null);
  const [copied, setCopied] = useState(false);
  const [fileName, setFileName] = useState("");

  // --- Carte 2 : upload via URL SAS ---
  const [uploadUrl, setUploadUrl] = useState("");
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>("idle");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleCreateJob(e: { preventDefault(): void }) {
    e.preventDefault();
    setJobError(null);
    setJob(null);
    setCopied(false);
    setJobStatus("loading");

    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "";

    try {
      const res = await fetch(`${apiUrl}/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fileName, contentType: "application/pdf" }),
      });

      if (!res.ok) throw new Error(`Erreur ${res.status} : ${await res.text()}`);

      const data: JobResult = await res.json();
      setJob(data);
      setUploadUrl(data.upload_url);
      setJobStatus("done");
    } catch (err) {
      setJobError(err instanceof Error ? err.message : String(err));
      setJobStatus("error");
    }
  }

  async function handleCopy() {
    if (!job) return;
    await navigator.clipboard.writeText(job.upload_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function handleUpload(e: { preventDefault(): void }) {
    e.preventDefault();
    setUploadError(null);
    setUploadStatus("uploading");

    const file = fileInputRef.current?.files?.[0];
    if (!file) return;

    try {
      const res = await fetch(uploadUrl, {
        method: "PUT",
        headers: {
          "x-ms-blob-type": "BlockBlob",
          "Content-Type": file.type || "application/pdf",
        },
        body: file,
      });

      if (!res.ok) throw new Error(`Upload échoué (${res.status})`);

      setUploadStatus("done");
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : String(err));
      setUploadStatus("error");
    }
  }

  return (
    <div className="flex flex-col items-center gap-6 bg-zinc-50 dark:bg-black min-h-screen py-16 px-4">

      {/* Carte 1 — Créer un job */}
      <section className="w-full max-w-xl bg-white dark:bg-zinc-900 rounded-2xl shadow-md p-8 flex flex-col gap-6">
        <div>
          <h2 className="text-lg font-semibold text-black dark:text-white">1. Créer un job</h2>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">Génère une URL d&apos;upload SAS.</p>
        </div>

        <form onSubmit={handleCreateJob} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="fileName" className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
              Nom du fichier
            </label>
            <input
              id="fileName"
              type="text"
              value={fileName}
              onChange={(e) => setFileName(e.target.value)}
              placeholder="document.pdf"
              required
              disabled={jobStatus === "loading"}
              className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900 dark:focus:ring-zinc-400 disabled:opacity-50"
            />
          </div>

          {jobError && (
            <p className="text-sm text-red-600 dark:text-red-400">{jobError}</p>
          )}

          <button
            type="submit"
            disabled={jobStatus === "loading"}
            className="w-full rounded-full bg-zinc-900 dark:bg-zinc-50 text-white dark:text-black py-2.5 text-sm font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors"
          >
            {jobStatus === "loading" ? <><Spinner />Création…</> : "Créer le job"}
          </button>
        </form>

        {job && (
          <div className="flex flex-col gap-3 border-t border-zinc-100 dark:border-zinc-800 pt-4">
            <div>
              <span className="text-xs font-medium text-zinc-500 uppercase tracking-wide">Job ID</span>
              <p className="text-sm font-mono text-zinc-800 dark:text-zinc-200 break-all mt-0.5">{job.job_id}</p>
            </div>
            <div>
              <span className="text-xs font-medium text-zinc-500 uppercase tracking-wide">Upload URL (SAS)</span>
              <div className="flex gap-2 items-start mt-0.5">
                <textarea
                  readOnly
                  value={job.upload_url}
                  rows={2}
                  className="flex-1 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 px-3 py-2 text-xs font-mono text-zinc-800 dark:text-zinc-200 resize-none focus:outline-none"
                />
                <button
                  type="button"
                  onClick={handleCopy}
                  className="shrink-0 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-700 transition-colors"
                >
                  {copied ? "Copié ✓" : "Copier"}
                </button>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Carte 2 — Uploader le fichier */}
      <section className="w-full max-w-xl bg-white dark:bg-zinc-900 rounded-2xl shadow-md p-8 flex flex-col gap-6">
        <div>
          <h2 className="text-lg font-semibold text-black dark:text-white">2. Uploader le fichier</h2>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">Collez l&apos;URL SAS et sélectionnez le fichier.</p>
        </div>

        {uploadStatus === "done" ? (
          <div className="flex flex-col gap-3">
            <div className="rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 p-4">
              <p className="text-sm font-medium text-green-800 dark:text-green-300">Fichier uploadé avec succès.</p>
            </div>
            <button
              onClick={() => { setUploadStatus("idle"); setUploadError(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}
              className="w-full rounded-full border border-zinc-200 dark:border-zinc-700 py-2.5 text-sm font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
            >
              Nouvel upload
            </button>
          </div>
        ) : (
          <form onSubmit={handleUpload} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="uploadUrl" className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                URL d&apos;upload (SAS)
              </label>
              <textarea
                id="uploadUrl"
                value={uploadUrl}
                onChange={(e) => setUploadUrl(e.target.value)}
                placeholder="https://..."
                required
                rows={2}
                disabled={uploadStatus === "uploading"}
                className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 px-3 py-2 text-xs font-mono text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900 dark:focus:ring-zinc-400 disabled:opacity-50 resize-none"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="fileUpload" className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Fichier
              </label>
              <input
                id="fileUpload"
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                required
                disabled={uploadStatus === "uploading"}
                className="block w-full text-sm text-zinc-700 dark:text-zinc-300
                  file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0
                  file:text-sm file:font-medium file:bg-zinc-100 file:text-zinc-800
                  dark:file:bg-zinc-800 dark:file:text-zinc-200
                  hover:file:bg-zinc-200 dark:hover:file:bg-zinc-700
                  disabled:opacity-50 disabled:cursor-not-allowed"
              />
            </div>

            {uploadError && (
              <p className="text-sm text-red-600 dark:text-red-400">{uploadError}</p>
            )}

            <button
              type="submit"
              disabled={uploadStatus === "uploading"}
              className="w-full rounded-full bg-zinc-900 dark:bg-zinc-50 text-white dark:text-black py-2.5 text-sm font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors"
            >
              {uploadStatus === "uploading" ? <><Spinner />Upload en cours…</> : "Uploader"}
            </button>
          </form>
        )}
      </section>

    </div>
  );
}

function Spinner() {
  return (
    <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  );
}
