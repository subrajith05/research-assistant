import { Link } from "react-router-dom";
import SignupForm from "../components/auth/SignupForm";

export default function SignupPage() {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="bg-white rounded-2xl shadow-md p-8 w-full max-w-md">
        <h1 className="text-2xl font-bold text-gray-800 mb-1">Create an account</h1>
        <p className="text-sm text-gray-500 mb-6">Start researching smarter</p>
        <SignupForm />
        <p className="text-sm text-gray-500 text-center mt-4">
          Already have an account?{" "}
          <Link to="/login" className="text-blue-600 hover:underline font-medium">
            Login
          </Link>
        </p>
      </div>
    </div>
  );
}