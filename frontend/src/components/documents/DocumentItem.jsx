import Button from "../ui/Button";

export default function DocumentItem({ document, onDelete, deleting }) {
  return (
    <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-200">
      <div className="flex flex-col min-w-0">
        <p className="text-sm font-medium text-gray-800 truncate">{document.file_name}</p>
        <p className="text-xs text-gray-400">
          {new Date(document.uploaded_at).toLocaleDateString()}
        </p>
      </div>
      <Button
        label="Delete"
        variant="danger"
        loading={deleting}
        onClick={() => onDelete(document.id)}
      />
    </div>
  );
}