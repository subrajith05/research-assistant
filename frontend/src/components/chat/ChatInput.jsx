import { useState } from "react";
import Button from "../ui/Button";

export default function ChatInput({ onSend, loading }) {
  const [query, setQuery] = useState("");

  const handleSend = () => {
    if (!query.trim() || loading) return;
    onSend(query.trim());
    setQuery("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex gap-2 items-end border-t border-gray-200 pt-4">
      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask a question about your documents..."
        rows={2}
        disabled={loading}
        className="flex-1 resize-none px-3 py-2 rounded-lg border border-gray-300 focus:border-blue-500 outline-none text-sm text-gray-800 disabled:bg-gray-100"
      />
      <Button
        label="Send"
        onClick={handleSend}
        loading={loading}
        disabled={!query.trim()}
      />
    </div>
  );
}