"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { InnovateLogo } from "@/components/InnovateLogo";
import { Lock, Loader2, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";

export default function AdminLoginPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await api.adminLogin(password);
      localStorage.setItem("admin_token", result.token);
      router.push("/admin/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-brand-light-blue/40 flex flex-col">
      <header className="bg-white/60 backdrop-blur-sm border-b border-brand-blue/5 px-6 py-4">
        <div className="max-w-5xl mx-auto">
          <InnovateLogo size="md" className="text-brand-blue" />
        </div>
      </header>

      <div className="flex-1 flex items-center justify-center p-4">
        <div className="w-full max-w-sm space-y-6">
          <div className="text-center space-y-2">
            <div className="mx-auto w-12 h-12 rounded-full bg-brand-blue/10 flex items-center justify-center">
              <Lock className="h-5 w-5 text-brand-blue" />
            </div>
            <h1 className="text-2xl font-serif text-brand-blue">Manager Login</h1>
            <p className="text-sm text-brand-blue/50">Access the feedback dashboard</p>
          </div>

          <Card className="bg-white border-0 shadow-sm rounded-2xl">
            <CardContent className="pt-6">
              <form onSubmit={handleLogin} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="password" className="text-brand-blue/70">Password</Label>
                  <Input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter manager password"
                    className="h-11 rounded-xl"
                    required
                  />
                </div>
                {error && <p className="text-sm text-brand-red">{error}</p>}
                <Button
                  type="submit"
                  disabled={loading || !password}
                  className="w-full h-11 bg-brand-blue hover:bg-brand-blue/90 rounded-full gap-2"
                >
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <>Sign In <ArrowRight className="h-4 w-4" /></>}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
