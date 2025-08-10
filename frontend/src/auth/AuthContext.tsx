// src/auth/AuthContext.tsx
"use client";

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  ReactNode,
} from "react";

interface User {
  emailid: string;
  fname: string;
  lname?: string;
  role: "doctor" | "patient";
  token: string;           // access_token
  refreshToken: string;    // refresh_token
}

interface AuthContextValue {
  user: User | null;
  login(emailid: string, password: string): Promise<void>;
  signup(data: any, role: "doctor" | "patient"): Promise<void>;
  logout(): void;
  fetchWithAuth(input: RequestInfo, init?: RequestInit): Promise<Response>;
}


const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const API = process.env.NEXT_PUBLIC_API_BASE_URL!;

  // 初始化：从 localStorage 恢复 user （包括 refreshToken）
  useEffect(() => {
    const saved = localStorage.getItem("user");
    if (saved) setUser(JSON.parse(saved));
  }, []);

  // 持久化 user
  useEffect(() => {
    if (user) localStorage.setItem("user", JSON.stringify(user));
    else localStorage.removeItem("user");
  }, [user]);

  // 登录：保存 access & refresh
  const login = async (emailid: string, password: string) => {
    const res = await fetch(`${API}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ emailid, password }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.message || "Login failed");
    const { access_token, refresh_token, user: u } = body;
    setUser({
      emailid: u.emailid,
      fname: u.fname,
      lname: u.lname,
      role: u.role,
      token: access_token,
      refreshToken: refresh_token,
    });
  };

  const signup = async (data: any, role: "doctor" | "patient") => {
    const route = role === "patient" ? "/register/patient" : "/register/doctor";
    const res = await fetch(`${API}${route}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.message || "Signup failed");
    // 注册后自动登录
    await login(data.emailid, data.password);
  };

  const logout = () => setUser(null);

  // 刷新 Access Token
  const refreshToken = async () => {
    if (!user) throw new Error("No user to refresh");
    const res = await fetch(
      `${API}/token?grant_type=refresh_token`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: user.refreshToken }),
      }
    );
    const body = await res.json();
    if (!res.ok) throw new Error(body.error_description || "Refresh failed");
    setUser(u => u && ({
      ...u,
      token: body.access_token,
      refreshToken: body.refresh_token,
    }));
  };

  // 带自动刷新、重试一次的 fetch
  const fetchWithAuth = async (
    input: RequestInfo,
    init: RequestInit = {}
  ): Promise<Response> => {
    if (!user) throw new Error("Not authenticated");

    // 注入 token
    const authInit: RequestInit = {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init.headers || {}),
        Authorization: `Bearer ${user.token}`,
      },
    };

    let res = await fetch(input, authInit);

    // 如果 401，再刷新 token、重试一次
    if (res.status === 401) {
      await refreshToken();
      res = await fetch(input, {
        ...authInit,
        headers: {
          ...(authInit.headers as Record<string,string>),
          Authorization: `Bearer ${user!.token}`,
        },
      });
    }

    return res;
  };

  return (
    <AuthContext.Provider
      value={{ user, login, signup, logout, fetchWithAuth }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}