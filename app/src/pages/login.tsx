import * as React from 'react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Github, Mail } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuth } from '@/lib/hooks/use-auth';
import { toast } from 'sonner';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const { signIn } = useAuth();
  const navigate = useNavigate();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) {
      toast.error('Please enter your email');
      return;
    }
    await signIn();
    toast.success('Magic link sent to your email!');
    navigate('/library');
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-[#0a0a0a] p-4">
      <Card className="w-full max-w-md bg-[#0f0f0f] border-[#1a1a1a] shadow-2xl">
        <CardHeader className="space-y-2 text-center">
          <div className="flex justify-center mb-4">
            <div className="w-12 h-12 bg-primary rounded-lg flex items-center justify-center text-white text-2xl font-bold">
              RP
            </div>
          </div>
          <CardTitle className="text-2xl font-bold tracking-tight">Research Pilot</CardTitle>
          <CardDescription className="text-muted-foreground">
            Paper intelligence for ML engineers
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button variant="outline" className="w-full bg-transparent border-[#1a1a1a] hover:bg-secondary py-6" onClick={() => navigate('/library')}>
            <Github className="mr-2 h-5 w-5" />
            Continue with GitHub
          </Button>

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t border-[#1a1a1a]" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-[#0f0f0f] px-2 text-muted-foreground">or</span>
            </div>
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            <div className="space-y-2">
              <Input
                type="email"
                placeholder="name@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="bg-transparent border-[#1a1a1a] focus:ring-primary h-11"
              />
            </div>
            <Button type="submit" className="w-full bg-primary hover:bg-primary/90 py-6 font-semibold">
              <Mail className="mr-2 h-5 w-5" />
              Send magic link
            </Button>
          </form>
        </CardContent>
        <CardFooter className="flex flex-col space-y-4">
          <p className="text-center text-xs text-muted-foreground px-8">
            By signing in you agree to our{' '}
            <a href="#" className="underline underline-offset-4 hover:text-primary">Terms of Service</a>{' '}
            and{' '}
            <a href="#" className="underline underline-offset-4 hover:text-primary">Privacy Policy</a>.
          </p>
        </CardFooter>
      </Card>
    </div>
  );
}
