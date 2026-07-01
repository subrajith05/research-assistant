import { useState } from "react";
import { useAuth } from "../../context/AuthContext";
import Input from "../ui/Input";
import Button from "../ui/Button";

export default function SignupForm(){
    const { signup } = useAuth();
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    const handleSubmit = async(e) => {
        e.preventDefault();
        setError("");
        setLoading(true);
        try{
            await signup(name, email, password);
        } catch(err) {
            setError(err.response?.data?.detail || "Signup failed. Please try again.");
        } finally {
            setLoading(false);
        }        
    };

    return (
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <Input
            label="Name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="John Doe"
            />

            <Input
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            />

            <Input
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            />
            {error && <p className="text-sm text-red-500">{error}</p>}
            <Button label="Create Account" type="submit" loading={loading} fullWidth />
        </form>
    );
}