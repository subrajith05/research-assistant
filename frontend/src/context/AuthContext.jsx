import { createContext, useContext, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/axios";

const Authcontext = createContext(null);

export function AuthProvider({children}){
    const [token, setToken] = useState(localStorage.getItem("token"));
    const navigate = useNavigate();

    const signup = async (name, email, password) => {
        const res = await api.post("/auth/signup", {name, email, password});
        const t = res.data.access_token;
        localStorage.setItem("token", t);
        setToken(t);
        navigate("/dashboard");
    };

    const login = async (email, password) => {
        const res = await api.post("/auth/login", {email, password});
        const t = res.data.access_token;
        localStorage.setItem("token", t);
        setToken(t);
        navigate("/dashboard")
    };

    const logout = () => {
        localStorage.removeItem("token");
        setToken(null);
        navigate("/login");
    };

    return(
        <Authcontext.Provider value={{ token, login, signup, logout}}>
            {children}
        </Authcontext.Provider>
    );
}

export function useAuth() {
    return useContext(Authcontext);
}