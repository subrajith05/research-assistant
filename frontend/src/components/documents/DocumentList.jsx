import { useState, useEffect, useRef } from "react";
import api from "../../api/axios";
import DocumentItem from "./DocumentItem";
import Button from "../ui/Button";
import Spinner from "../ui/Spinner";

export default function DocumentList() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [error, setError] = useState("");
  const fileInputRef = useRef(null);

  const fetchDocuments = async () => {
    try {
      const res = await api.get("/documents/");
      setDocuments(res.data);
    } catch {
      setError("Failed to load documents.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    setUploading(true);
    setError("");
    try {
      await api.post("/documents/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      await fetchDocuments();
    } catch (err) {
      setError(err.response?.data?.detail || "Upload failed.");
    } finally {
      setUploading(false);
      fileInputRef.current.value = "";
    }
  };

  const handleDelete = async (id) => {
    setDeletingId(id);
    setError("");
    try {
      await api.delete(`/documents/${id}`);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
    } catch {
      setError("Failed to delete document.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="flex flex-col gap-4 h-full">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-gray-700">Documents</h2>
        <Button
          label={uploading ? "Uploading..." : "Upload PDF"}
          onClick={() => fileInputRef.current.click()}
          loading={uploading}
        />
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={handleUpload}
        />
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}

      {loading ? (
        <div className="flex justify-center mt-4">
          <Spinner size="md" />
        </div>
      ) : documents.length === 0 ? (
        <p className="text-sm text-gray-400 text-center mt-4">
          No documents uploaded yet.
        </p>
      ) : (
        <div className="flex flex-col gap-2 overflow-y-auto">
          {documents.map((doc) => (
            <DocumentItem
              key={doc.id}
              document={doc}
              onDelete={handleDelete}
              deleting={deletingId === doc.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}