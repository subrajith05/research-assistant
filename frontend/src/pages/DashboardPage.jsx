import { useAuth } from "../context/AuthContext";
import DocumentList from "../components/documents/DocumentList";
import ChatWindow from "../components/chat/ChatWindow";
import Button from "../components/ui/Button";

export default function DashboardPage() {
  const { logout } = useAuth();

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Navbar */}
      <header className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200 shadow-sm">
        <h1 className="text-lg font-bold text-gray-800">Research Assistant</h1>
        <Button label="Logout" variant="secondary" onClick={logout} />
      </header>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside className="w-72 bg-white border-r border-gray-200 p-4 flex flex-col overflow-y-auto">
          <DocumentList />
        </aside>

        {/* Chat panel */}
        <main className="flex-1 flex flex-col p-6 overflow-hidden">
          <ChatWindow />
        </main>
      </div>
    </div>
  );
}