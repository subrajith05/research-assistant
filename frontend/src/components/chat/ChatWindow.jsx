import { useState, useEffect, useRef } from "react";
import { v4 as uuidv4 } from "uuid";
import api from "../../api/axios";
import MessageBubble from "./MessageBubble";
import ChatInput from "./ChatInput";
import Spinner from "../ui/Spinner";

export default function ChatWindow() {
  const [messages, setMessages] = useState([]);
  const [sessionId] = useState(() => uuidv4());
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async (query) => {
    const userMessage = { role: "user", content: query };
    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);

    try {
      const res = await api.post("/chat/", {
        session_id: sessionId,
        query,
      });
      const assistantMessage = { role: "assistant", content: res.data.answer };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      const errorMessage = {
        role: "assistant",
        content: err.response?.data?.detail || "Something went wrong. Please try again.",
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto flex flex-col gap-3 py-4 px-2">
        {messages.length === 0 ? (
          <p className="text-sm text-gray-400 text-center mt-8">
            Upload a document and ask a question to get started.
          </p>
        ) : (
          messages.map((msg, i) => <MessageBubble key={i} message={msg} />)
        )}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 px-4 py-3 rounded-2xl rounded-bl-sm">
              <Spinner size="sm" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <ChatInput onSend={handleSend} loading={loading} />
    </div>
  );
}